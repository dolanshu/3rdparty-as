#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <new>
#include <string>
#include <thread>
#include <utility>

#include <sys/syscall.h>
#include <unistd.h>

#include "resip/stack/Contents.hxx"
#include "resip/stack/Headers.hxx"
#include "resip/stack/NameAddr.hxx"
#include "resip/stack/SipMessage.hxx"
#include "resip/stack/SipStack.hxx"
#include "resip/stack/Transport.hxx"
#include "resip/stack/Uri.hxx"
#include "resip/dum/AppDialog.hxx"
#include "resip/dum/AppDialogSet.hxx"
#include "resip/dum/AppDialogSetFactory.hxx"
#include "resip/dum/ClientInviteSession.hxx"
#include "resip/dum/DialogUsageManager.hxx"
#include "resip/dum/InviteSessionHandler.hxx"
#include "resip/dum/MasterProfile.hxx"
#include "resip/dum/ServerInviteSession.hxx"
#include "rutil/Data.hxx"
#include "rutil/Log.hxx"

using namespace resip;

namespace
{

constexpr const char* kCapsuleName = "_resip_dum_two_leg.ServerState";

struct ServerState
{
   explicit ServerState(PyObject* pythonCallback) : callback(pythonCallback) {}

   PyObject* callback;
   std::thread worker;
   std::atomic<bool> stopRequested{false};
   std::mutex readyMutex;
   std::condition_variable readyCondition;
   bool ready{false};
   std::string startupError;
   std::string workerError;
   std::string callbackError;
   std::string incomingCallId;
   std::string outgoingCallId;
   std::string callingNumber;
   std::string calledNumber;
   std::string routeUri;
   long eventLoopThreadId{0};
   long callbackThreadId{0};
   int serverPort{0};
   int downstreamPort{0};
   int outboundFinalStatus{0};
   int upstreamStatus{0};
   bool callbackRan{false};
   bool outboundInviteSent{false};
   bool failureMapped{false};
   bool upstreamRejectSent{false};
};

long currentOsThreadId()
{
   return static_cast<long>(::syscall(SYS_gettid));
}

std::string takePythonError()
{
   PyObject* type = nullptr;
   PyObject* value = nullptr;
   PyObject* traceback = nullptr;
   PyErr_Fetch(&type, &value, &traceback);
   PyErr_NormalizeException(&type, &value, &traceback);

   std::string message = "Python route callback failed";
   PyObject* text = PyObject_Str(value != nullptr ? value : type);
   if (text != nullptr)
   {
      const char* utf8 = PyUnicode_AsUTF8(text);
      if (utf8 != nullptr)
      {
         message = utf8;
      }
      else
      {
         PyErr_Clear();
      }
      Py_DECREF(text);
   }
   else
   {
      PyErr_Clear();
   }

   Py_XDECREF(type);
   Py_XDECREF(value);
   Py_XDECREF(traceback);
   PyErr_Clear();
   return message;
}

void markReady(ServerState* state, const std::string& startupError = {})
{
   {
      std::lock_guard<std::mutex> lock(state->readyMutex);
      state->startupError = startupError;
      state->ready = true;
   }
   state->readyCondition.notify_all();
}

void recordWorkerError(ServerState* state, const std::string& message)
{
   {
      std::lock_guard<std::mutex> lock(state->readyMutex);
      if (!state->ready)
      {
         state->startupError = message;
         state->ready = true;
      }
      else
      {
         state->workerError = message;
      }
   }
   state->readyCondition.notify_all();
   std::cerr << "DUM_WORKER_ERROR message=" << message << std::endl;
}

void recordCallbackError(ServerState* state, const std::string& message)
{
   state->callbackError = message;
   std::cerr << "PYTHON_CALLBACK_ERROR message=" << message << std::endl;
}

bool callPythonRoute(ServerState* state,
                     const std::string& callId,
                     const std::string& callingNumber,
                     const std::string& calledNumber,
                     std::string& routeUri)
{
   state->callbackThreadId = currentOsThreadId();
   std::cout << "PYTHON_CALLBACK_ENTER thread_tid=" << state->callbackThreadId
             << " incoming_call_id=" << callId << std::endl;

   PyGILState_STATE gilState = PyGILState_Ensure();
   PyObject* callIdArg = PyUnicode_FromStringAndSize(
      callId.data(), static_cast<Py_ssize_t>(callId.size()));
   PyObject* callingNumberArg = PyUnicode_FromStringAndSize(
      callingNumber.data(), static_cast<Py_ssize_t>(callingNumber.size()));
   PyObject* calledNumberArg = PyUnicode_FromStringAndSize(
      calledNumber.data(), static_cast<Py_ssize_t>(calledNumber.size()));

   PyObject* result = nullptr;
   std::string callbackError;
   if (callIdArg != nullptr && callingNumberArg != nullptr &&
       calledNumberArg != nullptr)
   {
      result = PyObject_CallFunctionObjArgs(
         state->callback, callIdArg, callingNumberArg, calledNumberArg, nullptr);
   }
   else
   {
      callbackError = takePythonError();
   }

   if (result == nullptr && callbackError.empty())
   {
      callbackError = takePythonError();
   }
   else if (result != nullptr && !PyUnicode_Check(result))
   {
      callbackError = "Python route callback must return a SIP URI string";
   }
   else if (result != nullptr)
   {
      Py_ssize_t routeLength = 0;
      const char* routeText = PyUnicode_AsUTF8AndSize(result, &routeLength);
      if (routeText == nullptr)
      {
         callbackError = takePythonError();
      }
      else
      {
         routeUri.assign(routeText, static_cast<std::size_t>(routeLength));
      }
   }

   Py_XDECREF(result);
   Py_XDECREF(callIdArg);
   Py_XDECREF(callingNumberArg);
   Py_XDECREF(calledNumberArg);

   if (callbackError.empty() && routeUri.empty())
   {
      callbackError = "Python route callback returned an empty URI";
   }
   if (!callbackError.empty())
   {
      recordCallbackError(state, callbackError);
   }
   PyGILState_Release(gilState);
   return callbackError.empty();
}

class MinimalAppDialogSet : public AppDialogSet
{
public:
   explicit MinimalAppDialogSet(DialogUsageManager& dum) : AppDialogSet(dum) {}

   AppDialog* createAppDialog(const SipMessage&) override
   {
      return new AppDialog(mDum);
   }

   std::shared_ptr<UserProfile> selectUASUserProfile(const SipMessage&) override
   {
      return mDum.getMasterUserProfile();
   }
};

class MinimalAppDialogSetFactory : public AppDialogSetFactory
{
public:
   AppDialogSet* createAppDialogSet(DialogUsageManager& dum,
                                    const SipMessage&) override
   {
      return new MinimalAppDialogSet(dum);
   }
};

class TwoLegInviteSessionHandler : public InviteSessionHandler
{
public:
   explicit TwoLegInviteSessionHandler(ServerState* state)
      : InviteSessionHandler(false), mState(state)
   {
   }

   void setDum(DialogUsageManager& dum)
   {
      mDum = &dum;
   }

   void onNewSession(ServerInviteSessionHandle session,
                     InviteSession::OfferAnswerType,
                     const SipMessage& message) override
   {
      mState->incomingCallId = message.header(h_CallId).value().c_str();
      mState->callingNumber = message.header(h_From).uri().user().c_str();
      mState->calledNumber = message.header(h_RequestLine).uri().user().c_str();
      mState->callbackRan = true;
      std::cout << "DUM_UAS_NEW_SESSION incoming_call_id="
                << mState->incomingCallId << " calling=" << mState->callingNumber
                << " called=" << mState->calledNumber
                << " event_loop_tid=" << mState->eventLoopThreadId << std::endl;

      try
      {
         session->provisional(100);

         std::string route;
         if (!callPythonRoute(mState, mState->incomingCallId,
                              mState->callingNumber, mState->calledNumber, route))
         {
            session->reject(500);
            mState->upstreamStatus = 500;
            mState->upstreamRejectSent = true;
            return;
         }
         mState->routeUri = route;

         Data routeData(route.c_str());
         NameAddr target{Uri(routeData)};
         std::shared_ptr<SipMessage> outbound = mDum->makeInviteSession(
            target, mDum->getMasterUserProfile(),
            static_cast<const Contents*>(nullptr));
         const std::string outgoingCallId =
            outbound->header(h_CallId).value().c_str();

         if (outgoingCallId.empty() || outgoingCallId == mState->incomingCallId)
         {
            throw std::runtime_error(
               "DUM did not generate a distinct outbound Call-ID");
         }
         if (mInboundByOutboundCallId.find(outgoingCallId) !=
             mInboundByOutboundCallId.end())
         {
            throw std::runtime_error("duplicate generated outbound Call-ID");
         }

         mInboundByOutboundCallId.emplace(outgoingCallId, session);
         mState->outgoingCallId = outgoingCallId;
         std::cout << "DUM_UAC_INVITE_CREATED outgoing_call_id=" << outgoingCallId
                   << " inbound_call_id=" << mState->incomingCallId
                   << " route_uri=" << mState->routeUri << std::endl;
         mDum->send(outbound);
         mState->outboundInviteSent = true;
         std::cout << "DUM_UAC_INVITE_SENT outgoing_call_id=" << outgoingCallId
                   << std::endl;
      }
      catch (const std::exception& error)
      {
         mState->workerError = error.what();
         std::cerr << "DUM_UAS_ROUTE_ERROR message=" << error.what() << std::endl;
         session->reject(500);
         mState->upstreamStatus = 500;
         mState->upstreamRejectSent = true;
      }
      catch (...)
      {
         mState->workerError = "unknown exception while creating outbound INVITE";
         session->reject(500);
         mState->upstreamStatus = 500;
         mState->upstreamRejectSent = true;
      }
   }

   void onNewSession(ClientInviteSessionHandle,
                     InviteSession::OfferAnswerType,
                     const SipMessage& message) override
   {
      std::cout << "DUM_UAC_NEW_SESSION outgoing_call_id="
                << message.header(h_CallId).value().c_str() << std::endl;
   }

   void onFailure(ClientInviteSessionHandle, const SipMessage& message) override
   {
      const std::string outgoingCallId =
         message.header(h_CallId).value().c_str();
      const int downstreamStatus = message.header(h_StatusLine).statusCode();
      mState->outboundFinalStatus = downstreamStatus;
      std::cout << "DUM_UAC_FAILURE outgoing_call_id=" << outgoingCallId
                << " status=" << downstreamStatus << std::endl;

      const auto inbound = mInboundByOutboundCallId.find(outgoingCallId);
      if (inbound == mInboundByOutboundCallId.end())
      {
         mState->workerError =
            "UAC failure Call-ID did not match a saved inbound UAS handle";
         std::cerr << "DUM_UAC_CORRELATION_MISS outgoing_call_id="
                   << outgoingCallId << std::endl;
         return;
      }

      const int upstreamStatus = downstreamStatus == 486 ? 486 : 502;
      inbound->second->reject(upstreamStatus);
      mState->failureMapped = downstreamStatus == 486;
      mState->upstreamRejectSent = true;
      mState->upstreamStatus = upstreamStatus;
      std::cout << "DUM_UAS_FAILURE_MAPPED outgoing_call_id=" << outgoingCallId
                << " incoming_call_id=" << mState->incomingCallId
                << " downstream_status=" << downstreamStatus
                << " upstream_status=" << upstreamStatus << std::endl;
      mInboundByOutboundCallId.erase(inbound);
   }

   void onProvisional(ClientInviteSessionHandle, const SipMessage&) override {}
   void onConnected(ClientInviteSessionHandle, const SipMessage&) override {}
   void onConnected(InviteSessionHandle, const SipMessage&) override {}
   void onTerminated(InviteSessionHandle, TerminatedReason, const SipMessage*) override {}
   void onEarlyMedia(ClientInviteSessionHandle, const SipMessage&,
                     const SdpContents&) override
   {
   }
   void onAnswer(InviteSessionHandle, const SipMessage&, const SdpContents&) override {}
   void onOffer(InviteSessionHandle, const SipMessage&, const SdpContents&) override {}
   void onOfferRequired(InviteSessionHandle, const SipMessage&) override {}
   void onOfferRejected(InviteSessionHandle, const SipMessage*) override {}
   void onForkDestroyed(ClientInviteSessionHandle) override {}
   void onRedirected(ClientInviteSessionHandle, const SipMessage&) override {}
   void onInfo(InviteSessionHandle, const SipMessage&) override {}
   void onInfoSuccess(InviteSessionHandle, const SipMessage&) override {}
   void onInfoFailure(InviteSessionHandle, const SipMessage&) override {}
   void onMessage(InviteSessionHandle, const SipMessage&) override {}
   void onMessageSuccess(InviteSessionHandle, const SipMessage&) override {}
   void onMessageFailure(InviteSessionHandle, const SipMessage&) override {}
   void onRefer(InviteSessionHandle, ServerSubscriptionHandle,
                const SipMessage&) override
   {
   }
   void onReferNoSub(InviteSessionHandle, const SipMessage&) override {}
   void onReferRejected(InviteSessionHandle, const SipMessage&) override {}
   void onReferAccepted(InviteSessionHandle, ClientSubscriptionHandle,
                        const SipMessage&) override
   {
   }

private:
   ServerState* mState;
   DialogUsageManager* mDum{nullptr};
   std::map<std::string, ServerInviteSessionHandle> mInboundByOutboundCallId;
};

void runServer(ServerState* state, int serverPort, int downstreamPort)
{
   state->eventLoopThreadId = currentOsThreadId();
   std::cout << "DUM_EVENT_LOOP_START thread_tid=" << state->eventLoopThreadId
             << std::endl;

   try
   {
      Log::initialize(Log::Cout, Log::None, Data("as_resip_dum_two_leg_spike"));
      SipStack stack;
      stack.addTransport(UDP, serverPort, V4, StunDisabled, Data("127.0.0.1"));

      TwoLegInviteSessionHandler handler(state);
      DialogUsageManager dum(stack);
      handler.setDum(dum);

      auto profile = std::make_shared<MasterProfile>();
      Data contact = "sip:as-two-leg@127.0.0.1:" + Data(serverPort);
      profile->setOverrideHostAndPort(Uri(contact));
      profile->setDefaultFrom(NameAddr(contact));
      dum.setMasterProfile(profile);
      dum.setInviteSessionHandler(&handler);
      dum.setAppDialogSetFactory(std::make_unique<MinimalAppDialogSetFactory>());

      state->serverPort = serverPort;
      state->downstreamPort = downstreamPort;
      markReady(state);
      std::cout << "DUM_LISTENING address=127.0.0.1 port=" << serverPort
                << " downstream_port=" << downstreamPort << std::endl;

      while (!state->stopRequested.load())
      {
         stack.process(50);
         while (dum.process())
         {
         }
      }
      std::cout << "DUM_EVENT_LOOP_STOP thread_tid="
                << state->eventLoopThreadId << std::endl;
   }
   catch (const std::exception& error)
   {
      recordWorkerError(state, error.what());
   }
   catch (...)
   {
      recordWorkerError(state, "unknown C++ exception in DUM worker");
   }
}

void stopAndJoin(ServerState* state)
{
   state->stopRequested.store(true);
   if (state->worker.joinable())
   {
      Py_BEGIN_ALLOW_THREADS
      state->worker.join();
      Py_END_ALLOW_THREADS
   }
}

ServerState* getState(PyObject* capsule)
{
   return static_cast<ServerState*>(
      PyCapsule_GetPointer(capsule, kCapsuleName));
}

void capsuleDestructor(PyObject* capsule)
{
   ServerState* state = getState(capsule);
   if (state == nullptr)
   {
      PyErr_Clear();
      return;
   }
   stopAndJoin(state);
   Py_XDECREF(state->callback);
   delete state;
}

bool addDictItem(PyObject* dict, const char* key, PyObject* value)
{
   if (value == nullptr)
   {
      return false;
   }
   const int result = PyDict_SetItemString(dict, key, value);
   Py_DECREF(value);
   return result == 0;
}

bool addString(PyObject* dict, const char* key, const std::string& value)
{
   return addDictItem(
      dict, key,
      PyUnicode_FromStringAndSize(value.data(),
                                  static_cast<Py_ssize_t>(value.size())));
}

bool addLong(PyObject* dict, const char* key, long value)
{
   return addDictItem(dict, key, PyLong_FromLong(value));
}

bool addBool(PyObject* dict, const char* key, bool value)
{
   return addDictItem(dict, key, PyBool_FromLong(value));
}

PyObject* startUas(PyObject*, PyObject* args)
{
   int serverPort = 0;
   int downstreamPort = 0;
   PyObject* callback = nullptr;
   if (!PyArg_ParseTuple(args, "iiO:start_uas", &serverPort, &downstreamPort,
                         &callback))
   {
      return nullptr;
   }
   if (serverPort < 1 || serverPort > 65535 || downstreamPort < 1 ||
       downstreamPort > 65535 || serverPort == downstreamPort)
   {
      PyErr_SetString(PyExc_ValueError,
                      "server and downstream ports must be distinct valid ports");
      return nullptr;
   }
   if (!PyCallable_Check(callback))
   {
      PyErr_SetString(PyExc_TypeError, "callback must be callable");
      return nullptr;
   }

   ServerState* state = new (std::nothrow) ServerState(callback);
   if (state == nullptr)
   {
      return PyErr_NoMemory();
   }
   Py_INCREF(callback);
   try
   {
      state->worker = std::thread(runServer, state, serverPort, downstreamPort);
   }
   catch (const std::exception& error)
   {
      Py_DECREF(callback);
      delete state;
      PyErr_SetString(PyExc_RuntimeError, error.what());
      return nullptr;
   }

   bool ready = false;
   Py_BEGIN_ALLOW_THREADS
   {
      std::unique_lock<std::mutex> lock(state->readyMutex);
      ready = state->readyCondition.wait_for(
         lock, std::chrono::seconds(5), [state]() { return state->ready; });
   }
   Py_END_ALLOW_THREADS

   std::string startupError;
   if (ready)
   {
      std::lock_guard<std::mutex> lock(state->readyMutex);
      startupError = state->startupError;
   }
   if (!ready || !startupError.empty())
   {
      stopAndJoin(state);
      Py_DECREF(callback);
      delete state;
      const std::string message = ready ? startupError : "DUM startup timed out";
      PyErr_SetString(PyExc_RuntimeError, message.c_str());
      return nullptr;
   }

   PyObject* capsule = PyCapsule_New(state, kCapsuleName, capsuleDestructor);
   if (capsule == nullptr)
   {
      stopAndJoin(state);
      Py_DECREF(callback);
      delete state;
   }
   return capsule;
}

PyObject* stopUas(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   if (!PyArg_ParseTuple(args, "O:stop_and_join", &capsule))
   {
      return nullptr;
   }
   ServerState* state = getState(capsule);
   if (state == nullptr)
   {
      return nullptr;
   }

   stopAndJoin(state);
   Py_XDECREF(state->callback);
   state->callback = nullptr;

   PyObject* result = PyDict_New();
   if (result == nullptr)
   {
      return nullptr;
   }
   const bool ok =
      addBool(result, "callback_ran", state->callbackRan) &&
      addBool(result, "outbound_invite_sent", state->outboundInviteSent) &&
      addBool(result, "failure_mapped", state->failureMapped) &&
      addBool(result, "upstream_reject_sent", state->upstreamRejectSent) &&
      addLong(result, "event_loop_thread_id", state->eventLoopThreadId) &&
      addLong(result, "callback_thread_id", state->callbackThreadId) &&
      addLong(result, "server_port", state->serverPort) &&
      addLong(result, "downstream_port", state->downstreamPort) &&
      addLong(result, "outbound_final_status", state->outboundFinalStatus) &&
      addLong(result, "upstream_status", state->upstreamStatus) &&
      addString(result, "incoming_call_id", state->incomingCallId) &&
      addString(result, "outgoing_call_id", state->outgoingCallId) &&
      addString(result, "calling_number", state->callingNumber) &&
      addString(result, "called_number", state->calledNumber) &&
      addString(result, "route_uri", state->routeUri) &&
      addString(result, "callback_error", state->callbackError) &&
      addString(result, "worker_error", state->workerError);
   if (!ok)
   {
      Py_DECREF(result);
      return nullptr;
   }
   return result;
}

PyMethodDef methods[] = {
   {"start_uas", startUas, METH_VARARGS,
    "Start the throwaway DUM UAS on an explicit loopback UDP port."},
   {"stop_and_join", stopUas, METH_VARARGS,
    "Stop the DUM worker and return scalar evidence markers."},
   {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {
   PyModuleDef_HEAD_INIT,
   "_resip_dum",
   "Throwaway two-leg reSIProcate DUM to CPython feasibility spike.",
   -1,
   methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__resip_dum()
{
   return PyModule_Create(&module);
}