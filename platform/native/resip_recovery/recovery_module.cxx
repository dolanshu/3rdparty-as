#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <atomic>
#include <cctype>
#include <fstream>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <thread>

#include "resip/dum/DialogUsageManager.hxx"
#include "resip/dum/MasterProfile.hxx"
#include "resip/stack/Helper.hxx"
#include "resip/stack/MessageFilterRule.hxx"
#include "resip/stack/NameAddr.hxx"
#include "resip/stack/SipMessage.hxx"
#include "resip/stack/SipStack.hxx"
#include "resip/stack/Transport.hxx"
#include "resip/stack/Uri.hxx"
#include "resip/stack/TransactionUser.hxx"
#include "rutil/Data.hxx"
#include "rutil/Log.hxx"

using namespace resip;

namespace
{

constexpr const char* kCapsuleName = "as_platform._resip_recovery.SessionState";

struct DialogFields
{
   std::string callId;
   std::string localTag;
   std::string remoteTag;
   std::string localUri;
   std::string remoteUri;
   std::string remoteTarget;
   std::vector<std::string> routeSet;
   unsigned int localCSeq = 0;
   unsigned int remoteCSeq = 0;
};

struct Checkpoint
{
   DialogFields uas;
   DialogFields uac;
};

struct SessionState
{
   std::thread worker;
   std::atomic<bool> stopRequested{false};
   int listenPort{0};
   std::unique_ptr<SipStack> stack;
   std::unique_ptr<DialogUsageManager> dum;
   std::unique_ptr<Checkpoint> checkpoint;
   std::unique_ptr<class RecoveryTu> recoveryTuOwner;
   class RecoveryTu* recoveryTu{nullptr};
   bool downstream200{false};
   bool upstream200Queued{false};
   std::mutex readyMutex;
   bool ready{false};
   std::string startupError;
};

unsigned int parsePositive(const std::string& value, const std::string& fieldName)
{
   if (value.empty() || value[0] == '-')
   {
      throw std::runtime_error(fieldName + " must be a positive integer");
   }
   for (char character : value)
   {
      if (!std::isdigit(static_cast<unsigned char>(character)))
      {
         throw std::runtime_error(fieldName + " must be a positive integer");
      }
   }
   const unsigned long parsed = std::stoul(value);
   if (parsed == 0)
   {
      throw std::runtime_error(fieldName + " must be a positive integer");
   }
   return static_cast<unsigned int>(parsed);
}

Checkpoint loadCheckpoint(const std::string& path)
{
   std::ifstream input(path.c_str());
   if (!input)
   {
      throw std::runtime_error("cannot read native checkpoint adapter: " + path);
   }
   std::map<std::string, std::string> fields;
   std::string line;
   while (std::getline(input, line))
   {
      const std::size_t equals = line.find('=');
      if (equals == std::string::npos || equals == 0)
      {
         throw std::runtime_error("invalid native checkpoint adapter line");
      }
      if (!fields.emplace(line.substr(0, equals), line.substr(equals + 1)).second)
      {
         throw std::runtime_error("duplicate native checkpoint adapter field");
      }
   }

   auto get = [&fields](const std::string& name) -> const std::string&
   {
      const auto found = fields.find(name);
      if (found == fields.end())
      {
         throw std::runtime_error("native checkpoint adapter missing field: " + name);
      }
      return found->second;
   };

   if (get("format") != "d10-native-checkpoint-v1")
   {
      throw std::runtime_error("unsupported native checkpoint adapter format");
   }

   Checkpoint checkpoint;
   std::set<std::string> expected{"format"};
   auto loadLeg = [&get, &expected](const std::string& prefix, DialogFields& leg)
   {
      auto field = [&get, &expected, &prefix](const std::string& suffix) -> const std::string&
      {
         const std::string name = prefix + '_' + suffix;
         expected.insert(name);
         return get(name);
      };
      leg.callId = field("call_id");
      leg.localTag = field("local_tag");
      leg.remoteTag = field("remote_tag");
      leg.localUri = field("local_uri");
      leg.remoteUri = field("remote_uri");
      leg.remoteTarget = field("remote_target");
      leg.localCSeq = parsePositive(field("local_cseq"), prefix + "_local_cseq");
      leg.remoteCSeq = parsePositive(field("remote_cseq"), prefix + "_remote_cseq");
      const unsigned int routeCount = static_cast<unsigned int>(
         std::stoul(field("route_count")));
      for (unsigned int index = 0; index < routeCount; ++index)
      {
         leg.routeSet.push_back(field("route_" + std::to_string(index)));
      }
   };
   loadLeg("uas", checkpoint.uas);
   loadLeg("uac", checkpoint.uac);
   return checkpoint;
}

MessageFilterRuleList& recoveryRules()
{
   static MessageFilterRuleList rules = []()
   {
      MessageFilterRule::MethodList methods;
      methods.push_back(BYE);
      MessageFilterRuleList result;
      result.push_back(MessageFilterRule(MessageFilterRule::SchemeList(),
                                         MessageFilterRule::Any,
                                         methods));
      return result;
   }();
   return rules;
}

class RecoveryTu final : public TransactionUser
{
public:
   RecoveryTu(SipStack& stack, const Checkpoint& checkpoint, int asPort)
      : TransactionUser(recoveryRules()),
        mStack(stack),
        mCheckpoint(checkpoint),
        mAsPort(asPort),
        mDownstream200(false),
        mUpstream200Queued(false)
   {
      mFifo.setDescription("ProductRecoveryTu");
   }

   const Data& name() const override
   {
      static const Data value("ProductRecoveryTu");
      return value;
   }

   bool isForMe(const SipMessage& message) const override
   {
      if (!message.isRequest() || message.method() != BYE || !TransactionUser::isForMe(message))
      {
         return false;
      }
      return message.header(h_CallId).value() == Data(mCheckpoint.uas.callId.c_str()) &&
             message.header(h_From).param(p_tag) == Data(mCheckpoint.uas.remoteTag.c_str()) &&
             message.header(h_To).param(p_tag) == Data(mCheckpoint.uas.localTag.c_str());
   }

   void drain()
   {
      while (mFifo.messageAvailable())
      {
         std::unique_ptr<Message> message(mFifo.getNext());
         SipMessage* sip = dynamic_cast<SipMessage*>(message.get());
         if (!sip)
         {
            continue;
         }
         if (sip->isRequest() && sip->method() == BYE)
         {
            handleUpstreamBye(*sip);
         }
         else if (sip->isResponse())
         {
            handleDownstreamResponse(*sip);
         }
      }
   }

   bool downstream200() const { return mDownstream200; }
   bool upstream200Queued() const { return mUpstream200Queued; }

   void sendUpstream200()
   {
      if (!mUpstreamBye || !mDownstream200 || mUpstream200Queued)
      {
         throw std::runtime_error("recovery TU cannot send upstream 200 in its current state");
      }
      std::unique_ptr<SipMessage> upstreamResponse(Helper::makeResponse(*mUpstreamBye, 200));
      mStack.send(std::move(upstreamResponse), this);
      mUpstream200Queued = true;
      std::cout << "RECOVERY_TU_UPSTREAM_200_QUEUED=1\n";
   }

private:
   void handleUpstreamBye(const SipMessage& request)
   {
      if (!mUpstreamBye)
      {
         mUpstreamBye.reset(static_cast<SipMessage*>(request.clone()));
         NameAddr target(Uri(Data(mCheckpoint.uac.remoteTarget.c_str())));
         target.param(p_tag) = Data(mCheckpoint.uac.remoteTag.c_str());
         NameAddr from(Uri(Data(mCheckpoint.uac.localUri.c_str())));
         from.param(p_tag) = Data(mCheckpoint.uac.localTag.c_str());
         std::string contactHost = "127.0.0.1";
         Uri localUri(Data(mCheckpoint.uas.localUri.c_str()));
         if (!localUri.host().empty())
         {
            contactHost = localUri.host().c_str();
         }
         const std::string contactUri = "sip:as@" + contactHost + ":" + std::to_string(mAsPort);
         NameAddr contact(Uri(Data(contactUri.c_str())));
         std::unique_ptr<SipMessage> forwarded(Helper::makeRequest(target, from, contact, BYE));
         forwarded->header(h_CallId).value() = Data(mCheckpoint.uac.callId.c_str());
         forwarded->header(h_CSeq).method() = BYE;
         forwarded->header(h_CSeq).sequence() = mCheckpoint.uac.localCSeq;
         forwarded->header(h_From).param(p_tag) = Data(mCheckpoint.uac.localTag.c_str());
         forwarded->header(h_To).param(p_tag) = Data(mCheckpoint.uac.remoteTag.c_str());
         for (auto route = mCheckpoint.uac.routeSet.rbegin(); route != mCheckpoint.uac.routeSet.rend();
              ++route)
         {
            NameAddr routeHeader(Uri(Data(route->c_str())));
            forwarded->header(h_Routes).push_back(routeHeader);
         }
         mStack.send(std::move(forwarded), this);
         std::cout << "RECOVERY_TU_MATCHED_BEFORE_DUM=1\n";
      }
   }

   void handleDownstreamResponse(const SipMessage& response)
   {
      if (!mUpstreamBye || response.header(h_StatusLine).statusCode() != 200)
      {
         return;
      }
      mDownstream200 = true;
      std::cout << "RECOVERY_TU_DOWNSTREAM_200_RECEIVED=1\n";
   }

   SipStack& mStack;
   const Checkpoint& mCheckpoint;
   int mAsPort;
   std::unique_ptr<SipMessage> mUpstreamBye;
   bool mDownstream200;
   bool mUpstream200Queued;
};

void markReady(SessionState* state, const std::string& startupError = {})
{
   {
      std::lock_guard<std::mutex> lock(state->readyMutex);
      state->startupError = startupError;
      state->ready = true;
   }
}

void runRecovery(SessionState* state, const std::string& adapterPath, int requestedPort)
{
   try
   {
      Log::initialize(Log::Cout, Log::None, Data("as_resip_recovery"));
      state->checkpoint = std::make_unique<Checkpoint>(loadCheckpoint(adapterPath));
      state->stack = std::make_unique<SipStack>();
      Transport* udpTransport = state->stack->addTransport(
         UDP, requestedPort > 0 ? requestedPort : 0, V4, StunDisabled, Data("127.0.0.1"));
      if (udpTransport == nullptr)
      {
         throw std::runtime_error("addTransport(UDP) returned null");
      }
      const int port = udpTransport->port();
      if (port <= 0)
      {
         throw std::runtime_error("failed to resolve bound UDP port");
      }
      state->listenPort = port;
      state->dum = std::make_unique<DialogUsageManager>(*state->stack);
      state->dum->setMasterProfile(std::make_shared<MasterProfile>());
      state->recoveryTuOwner =
         std::make_unique<RecoveryTu>(*state->stack, *state->checkpoint, port);
      state->recoveryTu = state->recoveryTuOwner.get();
      state->stack->registerTransactionUser(*state->recoveryTu, true);
      markReady(state);
      std::cout << "RECOVERY_STACK_LISTENING port=" << port << std::endl;

      while (!state->stopRequested.load())
      {
         state->stack->process(50);
         while (state->dum->process())
         {
         }
         if (state->recoveryTu != nullptr)
         {
            state->recoveryTu->drain();
            state->downstream200 = state->recoveryTu->downstream200();
            state->upstream200Queued = state->recoveryTu->upstream200Queued();
         }
      }
      state->stack->unregisterTransactionUser(*state->recoveryTu);
      state->recoveryTu = nullptr;
      state->recoveryTuOwner.reset();
   }
   catch (const std::exception& error)
   {
      markReady(state, error.what());
   }
}

SessionState* getState(PyObject* capsule)
{
   return static_cast<SessionState*>(PyCapsule_GetPointer(capsule, kCapsuleName));
}

void capsuleDestructor(PyObject* capsule)
{
   SessionState* state = getState(capsule);
   if (state == nullptr)
   {
      PyErr_Clear();
      return;
   }
   state->stopRequested.store(true);
   if (state->worker.joinable())
   {
      Py_BEGIN_ALLOW_THREADS
      state->worker.join();
      Py_END_ALLOW_THREADS
   }
   delete state;
}

PyObject* pyStart(PyObject*, PyObject* args)
{
   const char* adapterPath = nullptr;
   int listenPort = 0;
   if (!PyArg_ParseTuple(args, "s|i:start", &adapterPath, &listenPort))
   {
      return nullptr;
   }
   auto* state = new SessionState();
   state->worker = std::thread(runRecovery, state, std::string(adapterPath), listenPort);

   for (int attempt = 0; attempt < 200; ++attempt)
   {
      {
         std::lock_guard<std::mutex> lock(state->readyMutex);
         if (state->ready)
         {
            if (!state->startupError.empty())
            {
               const std::string error = state->startupError;
               state->stopRequested.store(true);
               if (state->worker.joinable())
               {
                  state->worker.join();
               }
               delete state;
               PyErr_SetString(PyExc_RuntimeError, error.c_str());
               return nullptr;
            }
            break;
         }
      }
      Py_BEGIN_ALLOW_THREADS
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
      Py_END_ALLOW_THREADS
   }

   return PyCapsule_New(state, kCapsuleName, capsuleDestructor);
}

PyObject* pyStop(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   if (!PyArg_ParseTuple(args, "O:stop", &capsule))
   {
      return nullptr;
   }
   SessionState* state = getState(capsule);
   if (state == nullptr)
   {
      return nullptr;
   }
   state->stopRequested.store(true);
   if (state->worker.joinable())
   {
      Py_BEGIN_ALLOW_THREADS
      state->worker.join();
      Py_END_ALLOW_THREADS
   }
   Py_RETURN_NONE;
}

PyObject* pyProcess(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   int timeoutMs = 50;
   if (!PyArg_ParseTuple(args, "O|i:process", &capsule, &timeoutMs))
   {
      return nullptr;
   }
   SessionState* state = getState(capsule);
   if (state == nullptr || state->stack == nullptr)
   {
      Py_RETURN_NONE;
   }
   state->stack->process(timeoutMs > 0 ? timeoutMs : 50);
   if (state->dum)
   {
      while (state->dum->process())
      {
      }
   }
   if (state->recoveryTu != nullptr)
   {
      state->recoveryTu->drain();
      state->downstream200 = state->recoveryTu->downstream200();
      state->upstream200Queued = state->recoveryTu->upstream200Queued();
   }
   Py_RETURN_NONE;
}

PyObject* pyDrain(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   if (!PyArg_ParseTuple(args, "O:drain", &capsule))
   {
      return nullptr;
   }
   SessionState* state = getState(capsule);
   if (state != nullptr && state->recoveryTu != nullptr)
   {
      state->recoveryTu->drain();
   }
   Py_RETURN_NONE;
}

PyObject* pySendUpstream200(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   if (!PyArg_ParseTuple(args, "O:send_upstream_200", &capsule))
   {
      return nullptr;
   }
   SessionState* state = getState(capsule);
   if (state == nullptr || state->recoveryTu == nullptr)
   {
      PyErr_SetString(PyExc_RuntimeError, "recovery session is not running");
      return nullptr;
   }
   try
   {
      state->recoveryTu->sendUpstream200();
      state->upstream200Queued = true;
   }
   catch (const std::exception& error)
   {
      PyErr_SetString(PyExc_RuntimeError, error.what());
      return nullptr;
   }
   Py_RETURN_NONE;
}

PyObject* pyGetListenPort(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   if (!PyArg_ParseTuple(args, "O:get_listen_port", &capsule))
   {
      return nullptr;
   }
   SessionState* state = getState(capsule);
   if (state == nullptr)
   {
      return nullptr;
   }
   return PyLong_FromLong(state->listenPort);
}

PyObject* pyGetDownstream200(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   if (!PyArg_ParseTuple(args, "O:get_downstream_200", &capsule))
   {
      return nullptr;
   }
   SessionState* state = getState(capsule);
   return PyBool_FromLong(state != nullptr && state->downstream200);
}

PyObject* pyGetUpstream200Queued(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   if (!PyArg_ParseTuple(args, "O:get_upstream_200_queued", &capsule))
   {
      return nullptr;
   }
   SessionState* state = getState(capsule);
   return PyBool_FromLong(state != nullptr && state->upstream200Queued);
}

static PyMethodDef moduleMethods[] = {
   {"start", pyStart, METH_VARARGS, "Start RecoveryTU stack from adapter file"},
   {"stop", pyStop, METH_VARARGS, "Stop RecoveryTU stack"},
   {"process", pyProcess, METH_VARARGS, "Pump SipStack/DUM"},
   {"drain", pyDrain, METH_VARARGS, "Drain RecoveryTU fifo"},
   {"send_upstream_200", pySendUpstream200, METH_VARARGS, "Send 200 to upstream BYE"},
   {"get_listen_port", pyGetListenPort, METH_VARARGS, "Bound UDP port"},
   {"get_downstream_200", pyGetDownstream200, METH_VARARGS, "Downstream 200 received"},
   {"get_upstream_200_queued", pyGetUpstream200Queued, METH_VARARGS, "Upstream 200 queued"},
   {nullptr, nullptr, 0, nullptr}};

static struct PyModuleDef moduleDef = {
   PyModuleDef_HEAD_INIT,
   "_resip_recovery",
   "Product RecoveryTU extension",
   -1,
   moduleMethods};

PyMODINIT_FUNC PyInit__resip_recovery()
{
   return PyModule_Create(&moduleDef);
}

} // namespace
