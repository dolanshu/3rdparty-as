#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "resip/dum/AppDialogSet.hxx"
#include "resip/dum/ClientInviteSession.hxx"
#include "resip/dum/DialogSetId.hxx"
#include "resip/dum/DialogUsageManager.hxx"
#include "resip/dum/InviteSessionHandler.hxx"
#include "resip/dum/MasterProfile.hxx"
#include "resip/stack/HeaderFieldValue.hxx"
#include "resip/stack/Headers.hxx"
#include "resip/stack/Mime.hxx"
#include "resip/stack/NameAddr.hxx"
#include "resip/stack/SdpContents.hxx"
#include "resip/stack/SipMessage.hxx"
#include "resip/stack/SipStack.hxx"
#include "resip/stack/Transport.hxx"
#include "resip/stack/Uri.hxx"
#include "rutil/BaseException.hxx"
#include "rutil/Data.hxx"
#include "rutil/Log.hxx"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <climits>
#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <sys/syscall.h>
#include <thread>
#include <unistd.h>
#include <utility>
#include <vector>

namespace
{

using namespace resip;
using namespace std::chrono_literals;

constexpr const char* kOfferSdp =
   "v=0\r\n"
   "o=- 7101 1 IN IP4 127.0.0.1\r\n"
   "s=Two-leg process restart recovery\r\n"
   "c=IN IP4 127.0.0.1\r\n"
   "t=0 0\r\n"
   "m=audio 49170 RTP/AVP 0\r\n"
   "a=rtpmap:0 PCMU/8000\r\n";

constexpr auto kLegTimeout = 8s;
constexpr auto kAckDrain = 200ms;

struct LegSpec
{
   std::string name;
   std::string targetUri;
   std::string callId;
   std::string localTag;
   std::string remoteTag;
   std::vector<std::string> routeSet;
   unsigned int lastCSeq{0};
};

class LogicalCallAppDialogSet;

struct LegRuntime
{
   LegSpec spec;
   LogicalCallAppDialogSet* appDialogSet{nullptr};
   std::string callId;
   std::string localTag;
   std::string remoteTag;
   std::string remoteTarget;
   std::vector<std::string> routeSet;
   unsigned int requestCSeq{0};
   ClientInviteSessionHandle handle;
   unsigned long long handleId{0};
   bool answerSeen{false};
   bool connected{false};
   bool associationVerified{false};
};

long currentOsThreadId()
{
   return static_cast<long>(::syscall(SYS_gettid));
}

std::string dataString(const Data& value)
{
   return std::string(value.c_str());
}

std::string uriString(const Uri& value)
{
   return dataString(value.toString());
}

bool equalAsciiInsensitive(const std::string& left, const std::string& right)
{
   if (left.size() != right.size())
   {
      return false;
   }
   for (std::size_t index = 0; index < left.size(); ++index)
   {
      const auto leftChar = static_cast<unsigned char>(left[index]);
      const auto rightChar = static_cast<unsigned char>(right[index]);
      if (std::tolower(leftChar) != std::tolower(rightChar))
      {
         return false;
      }
   }
   return true;
}

class LogicalCallAppDialogSet final : public AppDialogSet
{
public:
   LogicalCallAppDialogSet(DialogUsageManager& dum,
                           std::string logicalToken,
                           std::string legName)
      : AppDialogSet(dum),
        mLogicalToken(std::move(logicalToken)),
        mLegName(std::move(legName))
   {
   }

   const std::string& logicalToken() const
   {
      return mLogicalToken;
   }

   const std::string& legName() const
   {
      return mLegName;
   }

private:
   std::string mLogicalToken;
   std::string mLegName;
};

class TwoLegInviteHandler final : public InviteSessionHandler
{
public:
   TwoLegInviteHandler(std::vector<LegRuntime>& legs,
                       const std::string& phase,
                       const std::string& logicalToken,
                       PyObject* policyCallback,
                       long loopThreadId)
      : InviteSessionHandler(false),
        mLegs(legs),
        mPhase(phase),
        mLogicalToken(logicalToken),
        mPolicyCallback(policyCallback),
        mLoopThreadId(loopThreadId)
   {
   }

   void onNewSession(ClientInviteSessionHandle,
                     InviteSession::OfferAnswerType,
                     const SipMessage&) override
   {
   }

   void onNewSession(ServerInviteSessionHandle,
                     InviteSession::OfferAnswerType,
                     const SipMessage&) override
   {
      fail("unexpected inbound server invite session");
   }

   void onFailure(ClientInviteSessionHandle,
                  const SipMessage& message) override
   {
      const int status = message.header(h_StatusLine).statusCode();
      fail("DUM received final failure status " + std::to_string(status) +
           " for Call-ID " + dataString(message.header(h_CallID).value()));
   }

   void onEarlyMedia(ClientInviteSessionHandle,
                     const SipMessage&,
                     const SdpContents&) override
   {
   }

   void onProvisional(ClientInviteSessionHandle,
                      const SipMessage&) override
   {
   }

   void onConnected(ClientInviteSessionHandle session,
                    const SipMessage& message) override
   {
      std::cout << "DUM_ON_CONNECTED_ENTER phase=" << mPhase
                << " call_id=" << dataString(message.header(h_CallID).value())
                << " event_loop_tid=" << currentOsThreadId() << std::endl;
      try
      {
         recordConnected(session, message);
      }
      catch (const BaseException& error)
      {
         fail("onConnected callback threw reSIProcate BaseException: " +
              std::string(error.what()));
      }
      catch (const std::exception& error)
      {
         fail("onConnected callback threw std::exception: " +
              std::string(error.what()));
      }
      catch (...)
      {
         fail("onConnected callback threw an unknown exception");
      }
   }

   void onConnected(InviteSessionHandle,
                    const SipMessage&) override
   {
      fail("unexpected UAS connected callback in UAC recovery experiment");
   }

   void onTerminated(InviteSessionHandle,
                     InviteSessionHandler::TerminatedReason,
                     const SipMessage*) override
   {
   }

   void onForkDestroyed(ClientInviteSessionHandle) override
   {
      fail("unexpected fork destruction in two-peer recovery experiment");
   }

   void onRedirected(ClientInviteSessionHandle,
                     const SipMessage&) override
   {
      fail("unexpected redirect in two-peer recovery experiment");
   }

   void onAnswer(InviteSessionHandle session,
                 const SipMessage& message,
                 const SdpContents&) override
   {
      recordAnswer(session, message);
   }

   void onOffer(InviteSessionHandle,
                const SipMessage&,
                const SdpContents&) override
   {
   }

   void onOfferRequired(InviteSessionHandle,
                        const SipMessage&) override
   {
   }

   void onOfferRejected(InviteSessionHandle,
                        const SipMessage*) override
   {
      fail("DUM rejected SDP negotiation for a restored UAC dialog");
   }

   void onInfo(InviteSessionHandle, const SipMessage&) override {}
   void onInfoSuccess(InviteSessionHandle, const SipMessage&) override {}
   void onInfoFailure(InviteSessionHandle, const SipMessage&) override {}
   void onMessage(InviteSessionHandle, const SipMessage&) override {}
   void onMessageSuccess(InviteSessionHandle, const SipMessage&) override {}
   void onMessageFailure(InviteSessionHandle, const SipMessage&) override {}

   void onRefer(InviteSessionHandle,
                ServerSubscriptionHandle,
                const SipMessage&) override
   {
   }

   void onReferNoSub(InviteSessionHandle, const SipMessage&) override {}
   void onReferRejected(InviteSessionHandle, const SipMessage&) override {}

   void onReferAccepted(InviteSessionHandle,
                        ClientSubscriptionHandle,
                        const SipMessage&) override
   {
   }

   const std::string& failure() const
   {
      return mFailure;
   }

private:
   void fail(const std::string& message)
   {
      if (mFailure.empty())
      {
         mFailure = message;
      }
      std::cerr << "DUM_CALLBACK_FAILURE " << message << std::endl;
   }

   LegRuntime* findLeg(const std::string& name)
   {
      const auto found = std::find_if(
         mLegs.begin(), mLegs.end(), [&name](const LegRuntime& leg) {
            return leg.spec.name == name;
         });
      return found == mLegs.end() ? nullptr : &*found;
   }

   template<class SessionHandle>
   LegRuntime* resolveHandle(SessionHandle session,
                             const SipMessage& message,
                             const std::string& event)
   {
      if (std::this_thread::get_id() != mLoopThread)
      {
         fail(event + " callback ran outside the DUM event-loop thread");
         return nullptr;
      }
      if (!session.isValid())
      {
         fail(event + " callback received an invalid DUM session handle");
         return nullptr;
      }

      AppDialogSetHandle appDialogSetHandle = session->getAppDialogSet();
      if (!appDialogSetHandle.isValid())
      {
         fail(event + " session handle has no attached AppDialogSet");
         return nullptr;
      }
      auto* appDialogSet = dynamic_cast<LogicalCallAppDialogSet*>(
         appDialogSetHandle.get());
      if (appDialogSet == nullptr)
      {
         fail(event + " session handle is attached to the wrong AppDialogSet type");
         return nullptr;
      }

      LegRuntime* leg = findLeg(appDialogSet->legName());
      if (leg == nullptr || leg->appDialogSet != appDialogSet)
      {
         fail(event + " session handle resolved to an unexpected app leg");
         return nullptr;
      }
      if (appDialogSet->logicalToken() != mLogicalToken ||
          dataString(message.header(h_CallID).value()) != leg->callId ||
          dataString(session->getCallId()) != leg->callId ||
          dataString(message.header(h_From).param(p_tag)) != leg->localTag ||
          dataString(session->getDialogId().getDialogSetId().getCallId()) !=
             leg->callId ||
          dataString(session->getDialogId().getDialogSetId().getLocalTag()) !=
             leg->localTag)
      {
         fail(event + " handle identity or logical-token association mismatch");
         return nullptr;
      }

      const std::string responseRemoteTag =
         dataString(message.header(h_To).param(p_tag));
      if (responseRemoteTag.empty() ||
          (!leg->remoteTag.empty() && responseRemoteTag != leg->remoteTag) ||
          (!dataString(session->getDialogId().getRemoteTag()).empty() &&
           dataString(session->getDialogId().getRemoteTag()) != responseRemoteTag))
      {
         fail(event + " remote To-tag or DUM dialog identity mismatch");
         return nullptr;
      }
      if (leg->remoteTag.empty())
      {
         leg->remoteTag = responseRemoteTag;
      }

      leg->associationVerified = true;
      return leg;
   }

   bool callPolicy(const std::string& event,
                   const LegRuntime& leg,
                   int status)
   {
      const long callbackThreadId = currentOsThreadId();
      if (callbackThreadId != mLoopThreadId)
      {
         fail("Python policy callback would cross the DUM event-loop thread");
         return false;
      }
      const std::string statusText = std::to_string(status);
      const std::string threadText = std::to_string(callbackThreadId);
      PyObject* values[] = {
         PyUnicode_FromString(event.c_str()),
         PyUnicode_FromString(mLogicalToken.c_str()),
         PyUnicode_FromString(leg.spec.name.c_str()),
         PyUnicode_FromString(leg.callId.c_str()),
         PyUnicode_FromString(statusText.c_str()),
         PyUnicode_FromString(threadText.c_str()),
      };
      for (PyObject* value : values)
      {
         if (value == nullptr)
         {
            for (PyObject* allocated : values)
            {
               Py_XDECREF(allocated);
            }
            PyErr_Print();
            fail("could not allocate scalar Python policy inputs");
            return false;
         }
      }

      PyObject* result = PyObject_CallFunctionObjArgs(
         mPolicyCallback, values[0], values[1], values[2], values[3],
         values[4], values[5], nullptr);
      for (PyObject* value : values)
      {
         Py_DECREF(value);
      }
      if (result == nullptr)
      {
         PyErr_Print();
         fail("Python scalar policy callback raised an exception");
         return false;
      }
      if (!PyBool_Check(result))
      {
         Py_DECREF(result);
         fail("Python policy callback must return bool");
         return false;
      }
      const bool accepted = result == Py_True;
      Py_DECREF(result);
      if (!accepted)
      {
         fail("Python scalar policy callback rejected " + event + " for " +
              leg.spec.name);
      }
      return accepted;
   }

   void recordAnswer(InviteSessionHandle session, const SipMessage& message)
   {
      LegRuntime* leg = resolveHandle(session, message, "onAnswer");
      if (leg == nullptr)
      {
         return;
      }
      const int status = message.header(h_StatusLine).statusCode();
      const unsigned int cseq = message.header(h_CSeq).sequence();
      if (status != 200 || cseq != leg->requestCSeq ||
          message.header(h_CSeq).method() != INVITE ||
          message.getContents() == nullptr)
      {
         fail("onAnswer did not match the expected 200/INVITE CSeq with SDP");
         return;
      }
      if (leg->answerSeen)
      {
         fail("duplicate SDP answer callback for " + leg->spec.name);
         return;
      }
      leg->answerSeen = true;
      ++mAnswerCount;
      std::cout << "DUM_FINAL_ANSWER phase=" << mPhase
                << " leg=" << leg->spec.name
                << " call_id=" << leg->callId
                << " cseq=" << cseq
                << " status=" << status
                << " event_loop_tid=" << currentOsThreadId() << std::endl;
      callPolicy("answer", *leg, status);
   }

   void capturePhaseAState(LegRuntime& leg, const SipMessage& message)
   {
      const auto& contacts = message.header(h_Contacts);
      if (contacts.size() != 1)
      {
         fail("Phase-A 200 must contain exactly one Contact for " + leg.spec.name);
         return;
      }
      auto contact = contacts.begin();
      leg.remoteTarget = uriString(contact->uri());
      if (!equalAsciiInsensitive(leg.remoteTarget, leg.spec.targetUri))
      {
         fail("Phase-A Contact differs from the peer target for " + leg.spec.name);
      }

      std::vector<std::string> responseRoutes;
      for (const auto& route : message.header(h_RecordRoutes))
      {
         responseRoutes.push_back(uriString(route.uri()));
      }
      std::reverse(responseRoutes.begin(), responseRoutes.end());
      if (responseRoutes.empty() ||
          responseRoutes.size() != leg.spec.routeSet.size())
      {
         fail("Phase-A 200 Record-Route set differs in size for " + leg.spec.name);
         return;
      }
      for (std::size_t index = 0; index < responseRoutes.size(); ++index)
      {
         if (!equalAsciiInsensitive(responseRoutes[index],
                                    leg.spec.routeSet[index]))
         {
            fail("Phase-A 200 Record-Route differs for " + leg.spec.name);
         }
      }
      leg.routeSet = std::move(responseRoutes);
   }

   void recordConnected(ClientInviteSessionHandle session,
                        const SipMessage& message)
   {
      LegRuntime* leg = resolveHandle(session, message, "onConnected");
      if (leg == nullptr)
      {
         return;
      }
      const int status = message.header(h_StatusLine).statusCode();
      const unsigned int cseq = message.header(h_CSeq).sequence();
      if (status != 200 || cseq != leg->requestCSeq ||
          message.header(h_CSeq).method() != INVITE)
      {
         fail("onConnected did not match the expected 200/INVITE CSeq");
         return;
      }
      if (leg->connected)
      {
         fail("duplicate connected callback for " + leg->spec.name);
         return;
      }
      if (mPhase == "phase-a")
      {
         capturePhaseAState(*leg, message);
      }

      leg->handle = session;
      leg->handleId = static_cast<unsigned long long>(session.getId());
      leg->connected = true;
      ++mConnectedCount;
      std::cout << "DUM_HANDLE_ASSOCIATION phase=" << mPhase
                << " leg=" << leg->spec.name
                << " handle_id=" << leg->handleId
                << " token=" << mLogicalToken
                << " attached=true event_loop_tid=" << currentOsThreadId()
                << std::endl;
      callPolicy("connected", *leg, status);
   }

   std::vector<LegRuntime>& mLegs;
   const std::string& mPhase;
   const std::string& mLogicalToken;
   PyObject* mPolicyCallback;
   long mLoopThreadId;
   std::thread::id mLoopThread{std::this_thread::get_id()};
   std::string mFailure;
   int mAnswerCount{0};
   int mConnectedCount{0};

public:
   int answerCount() const
   {
      return mAnswerCount;
   }

   int connectedCount() const
   {
      return mConnectedCount;
   }
};

bool readPyString(PyObject* value,
                  const char* field,
                  std::string& destination)
{
   if (!PyUnicode_Check(value))
   {
      PyErr_Format(PyExc_TypeError, "%s must be a string", field);
      return false;
   }
   Py_ssize_t size = 0;
   const char* text = PyUnicode_AsUTF8AndSize(value, &size);
   if (text == nullptr)
   {
      return false;
   }
   destination.assign(text, static_cast<std::size_t>(size));
   return true;
}

bool readDictString(PyObject* dict,
                    const char* field,
                    std::string& destination)
{
   PyObject* value = PyDict_GetItemString(dict, field);
   if (value == nullptr)
   {
      PyErr_Format(PyExc_KeyError, "missing leg field '%s'", field);
      return false;
   }
   return readPyString(value, field, destination);
}

bool readDictUnsigned(PyObject* dict,
                      const char* field,
                      unsigned int& destination)
{
   PyObject* value = PyDict_GetItemString(dict, field);
   if (value == nullptr || !PyLong_Check(value))
   {
      PyErr_Format(PyExc_TypeError, "leg field '%s' must be an integer", field);
      return false;
   }
   const long number = PyLong_AsLong(value);
   if (PyErr_Occurred())
   {
      return false;
   }
   if (number < 0 || static_cast<unsigned long>(number) >
                         static_cast<unsigned long>(UINT_MAX))
   {
      PyErr_Format(PyExc_ValueError, "leg field '%s' is out of range", field);
      return false;
   }
   destination = static_cast<unsigned int>(number);
   return true;
}

bool readRouteSet(PyObject* dict,
                  const char* field,
                  std::vector<std::string>& routeSet)
{
   PyObject* value = PyDict_GetItemString(dict, field);
   if (value == nullptr || !PyList_Check(value))
   {
      PyErr_Format(PyExc_TypeError, "leg field '%s' must be a list of strings", field);
      return false;
   }
   const Py_ssize_t count = PyList_Size(value);
   routeSet.clear();
   routeSet.reserve(static_cast<std::size_t>(count));
   for (Py_ssize_t index = 0; index < count; ++index)
   {
      std::string route;
      if (!readPyString(PyList_GetItem(value, index), field, route))
      {
         return false;
      }
      routeSet.push_back(std::move(route));
   }
   return true;
}

bool parseLegSpecs(const std::string& phase,
                   PyObject* pythonLegs,
                   std::vector<LegRuntime>& legs)
{
   if (!PyList_Check(pythonLegs) || PyList_Size(pythonLegs) != 2)
   {
      PyErr_SetString(PyExc_ValueError, "exactly two leg dictionaries are required");
      return false;
   }
   legs.reserve(2);
   for (Py_ssize_t index = 0; index < 2; ++index)
   {
      PyObject* pythonLeg = PyList_GetItem(pythonLegs, index);
      if (!PyDict_Check(pythonLeg))
      {
         PyErr_SetString(PyExc_TypeError, "each leg must be a dictionary");
         return false;
      }
      LegRuntime runtime;
      if (!readDictString(pythonLeg, "name", runtime.spec.name) ||
          !readRouteSet(pythonLeg, "route_set", runtime.spec.routeSet))
      {
         return false;
      }
      if (phase == "phase-a")
      {
         if (!readDictString(pythonLeg, "target_uri", runtime.spec.targetUri))
         {
            return false;
         }
      }
      else
      {
         if (!readDictString(pythonLeg, "call_id", runtime.spec.callId) ||
             !readDictString(pythonLeg, "local_tag", runtime.spec.localTag) ||
             !readDictString(pythonLeg, "remote_to_tag", runtime.spec.remoteTag) ||
             !readDictString(pythonLeg, "remote_target_contact",
                             runtime.spec.targetUri) ||
             !readDictUnsigned(pythonLeg, "last_cseq", runtime.spec.lastCSeq))
         {
            return false;
         }
         runtime.callId = runtime.spec.callId;
         runtime.localTag = runtime.spec.localTag;
         runtime.remoteTag = runtime.spec.remoteTag;
         runtime.remoteTarget = runtime.spec.targetUri;
         runtime.routeSet = runtime.spec.routeSet;
         runtime.requestCSeq = runtime.spec.lastCSeq + 1;
         if (runtime.spec.callId.empty() || runtime.spec.localTag.empty() ||
             runtime.spec.remoteTag.empty() || runtime.spec.targetUri.empty() ||
             runtime.spec.routeSet.empty() || runtime.spec.lastCSeq == 0 ||
             runtime.requestCSeq <= runtime.spec.lastCSeq)
         {
            PyErr_SetString(PyExc_ValueError, "restored leg state is incomplete");
            return false;
         }
      }
      if (runtime.spec.name.empty() || runtime.spec.routeSet.empty())
      {
         PyErr_SetString(PyExc_ValueError,
                         "each leg requires a name and non-empty route set");
         return false;
      }
      if (std::any_of(legs.begin(), legs.end(), [&runtime](const LegRuntime& prior) {
             return prior.spec.name == runtime.spec.name;
          }))
      {
         PyErr_SetString(PyExc_ValueError, "leg names must be distinct");
         return false;
      }
      legs.push_back(std::move(runtime));
   }
   return true;
}

void processOnce(SipStack& stack, DialogUsageManager& dum)
{
   stack.process(10);
   while (dum.process())
   {
   }
}

void waitForLeg(SipStack& stack,
                DialogUsageManager& dum,
                TwoLegInviteHandler& handler,
                LegRuntime& leg)
{
   const auto deadline = std::chrono::steady_clock::now() + kLegTimeout;
   while (std::chrono::steady_clock::now() < deadline &&
          (!leg.answerSeen || !leg.connected) && handler.failure().empty())
   {
      processOnce(stack, dum);
   }
   if (!handler.failure().empty())
   {
      throw std::runtime_error(handler.failure());
   }
   if (!leg.answerSeen || !leg.connected)
   {
      throw std::runtime_error("timed out waiting for final response and ACK generation on " +
                               leg.spec.name);
   }
}

void waitForBoth(SipStack& stack,
                 DialogUsageManager& dum,
                 TwoLegInviteHandler& handler,
                 std::vector<LegRuntime>& legs)
{
   const auto deadline = std::chrono::steady_clock::now() + kLegTimeout;
   const auto allComplete = [&legs]() {
      return std::all_of(legs.begin(), legs.end(), [](const LegRuntime& leg) {
         return leg.answerSeen && leg.connected;
      });
   };
   while (std::chrono::steady_clock::now() < deadline && !allComplete() &&
          handler.failure().empty())
   {
      processOnce(stack, dum);
   }
   if (!handler.failure().empty())
   {
      throw std::runtime_error(handler.failure());
   }
   if (!allComplete())
   {
      throw std::runtime_error("timed out waiting for both phase-A final responses");
   }
}

void drainAckWork(SipStack& stack, DialogUsageManager& dum)
{
   const auto deadline = std::chrono::steady_clock::now() + kAckDrain;
   while (std::chrono::steady_clock::now() < deadline)
   {
      processOnce(stack, dum);
   }
}

void sendInviteForLeg(DialogUsageManager& dum,
                      const std::shared_ptr<UserProfile>& profile,
                      const SdpContents& offer,
                      const std::string& phase,
                      const std::string& logicalToken,
                      LegRuntime& leg)
{
   leg.appDialogSet = new LogicalCallAppDialogSet(
      dum, logicalToken, leg.spec.name);
   const NameAddr target(Uri(Data(leg.spec.targetUri.c_str())));
   std::shared_ptr<SipMessage> invite;
   if (phase == "phase-a")
   {
      invite = dum.makeInviteSession(target, profile, &offer, leg.appDialogSet);
      if (!invite)
      {
         throw std::runtime_error("DUM failed to create initial INVITE for " +
                                  leg.spec.name);
      }
      leg.callId = dataString(invite->header(h_CallID).value());
      leg.localTag = dataString(invite->header(h_From).param(p_tag));
      leg.requestCSeq = invite->header(h_CSeq).sequence();
      if (leg.callId.empty() || leg.localTag.empty() || leg.requestCSeq == 0 ||
          invite->header(h_To).exists(p_tag))
      {
         throw std::runtime_error("initial DUM INVITE identity was incomplete");
      }
   }
   else
   {
      const DialogSetId dialogSetId(Data(leg.spec.callId.c_str()),
                                    Data(leg.spec.localTag.c_str()));
      invite = dum.makeInviteSession(
         target, dialogSetId, profile, &offer, DialogUsageManager::None,
         nullptr, leg.appDialogSet);
      if (!invite)
      {
         throw std::runtime_error("DUM failed to create restored INVITE for " +
                                  leg.spec.name);
      }
      invite->header(h_To).param(p_tag) = Data(leg.spec.remoteTag.c_str());
      for (const auto& route : leg.spec.routeSet)
      {
         invite->header(h_Routes).push_back(
            NameAddr(Uri(Data(route.c_str()))));
      }
      invite->header(h_CSeq).sequence() = leg.requestCSeq;
      if (dataString(invite->header(h_CallID).value()) != leg.spec.callId ||
          dataString(invite->header(h_From).param(p_tag)) != leg.spec.localTag ||
          dataString(invite->header(h_To).param(p_tag)) != leg.spec.remoteTag ||
          invite->header(h_CSeq).sequence() != leg.spec.lastCSeq + 1 ||
          invite->header(h_Routes).size() != leg.spec.routeSet.size())
      {
         throw std::runtime_error("restored in-dialog INVITE failed in-memory validation");
      }
   }

   if (std::any_of(leg.spec.routeSet.begin(), leg.spec.routeSet.end(),
                   [](const std::string& route) { return route.empty(); }))
   {
      throw std::runtime_error("empty route-set entry for " + leg.spec.name);
   }
   if (phase == "phase-a")
   {
      const std::string priorCallId = leg.callId;
      for (const auto& other : leg.spec.routeSet)
      {
         if (other.empty())
         {
            throw std::runtime_error("empty phase-A expected route");
         }
      }
      if (priorCallId.empty())
      {
         throw std::runtime_error("phase-A generated an empty Call-ID");
      }
   }
   else
   {
      leg.callId = leg.spec.callId;
      leg.localTag = leg.spec.localTag;
   }

   std::cout << "DUM_SEND phase=" << phase
             << " leg=" << leg.spec.name
             << " call_id=" << leg.callId
             << " local_tag=" << leg.localTag
             << " cseq=" << leg.requestCSeq
             << " route_count=" << invite->header(h_Routes).size()
             << " target=" << leg.spec.targetUri << std::endl;
   dum.send(invite);
}

bool validateRetainedHandles(std::vector<LegRuntime>& legs,
                             const std::string& logicalToken,
                             const std::string& phase)
{
   std::set<unsigned long long> handleIds;
   std::set<std::string> tokens;
   for (auto& leg : legs)
   {
      if (!leg.handle.isValid())
      {
         throw std::runtime_error("connected DUM handle is no longer valid for " +
                                  leg.spec.name);
      }
      AppDialogSetHandle appDialogSetHandle = leg.handle->getAppDialogSet();
      auto* appDialogSet = appDialogSetHandle.isValid()
                              ? dynamic_cast<LogicalCallAppDialogSet*>(
                                   appDialogSetHandle.get())
                              : nullptr;
      if (appDialogSet == nullptr || appDialogSet != leg.appDialogSet ||
          appDialogSet->logicalToken() != logicalToken ||
          appDialogSet->legName() != leg.spec.name ||
          !leg.associationVerified)
      {
         throw std::runtime_error("retained handle lost its restored logical token for " +
                                  leg.spec.name);
      }
      handleIds.insert(leg.handleId);
      tokens.insert(appDialogSet->logicalToken());
      std::cout << "DUM_RETAINED_HANDLE phase=" << phase
                << " leg=" << leg.spec.name
                << " handle_id=" << leg.handleId
                << " token=" << appDialogSet->logicalToken()
                << " attached=true" << std::endl;
   }
   if (handleIds.size() != 2 || tokens.size() != 1 ||
       *tokens.begin() != logicalToken)
   {
      throw std::runtime_error("two live DUM handles did not share one logical call token");
   }
   std::cout << "DUM_HANDLE_SUMMARY phase=" << phase
             << " handle_count=" << handleIds.size()
             << " logical_token_count=" << tokens.size()
             << " same_restored_logical_token=true" << std::endl;
   return true;
}

bool setPyString(PyObject* dict,
                 const char* key,
                 const std::string& value)
{
   PyObject* pythonValue = PyUnicode_FromStringAndSize(
      value.data(), static_cast<Py_ssize_t>(value.size()));
   if (pythonValue == nullptr)
   {
      return false;
   }
   const int status = PyDict_SetItemString(dict, key, pythonValue);
   Py_DECREF(pythonValue);
   return status == 0;
}

bool setPyLong(PyObject* dict, const char* key, unsigned long long value)
{
   PyObject* pythonValue = PyLong_FromUnsignedLongLong(value);
   if (pythonValue == nullptr)
   {
      return false;
   }
   const int status = PyDict_SetItemString(dict, key, pythonValue);
   Py_DECREF(pythonValue);
   return status == 0;
}

bool setPyBool(PyObject* dict, const char* key, bool value)
{
   const int status = PyDict_SetItemString(dict, key, value ? Py_True : Py_False);
   return status == 0;
}

PyObject* makeResult(const std::vector<LegRuntime>& legs,
                     const std::string& logicalToken,
                     const std::string& phase,
                     long loopThreadId,
                     int answerCount,
                     int connectedCount)
{
   PyObject* result = PyDict_New();
   PyObject* pythonLegs = PyList_New(0);
   if (result == nullptr || pythonLegs == nullptr)
   {
      Py_XDECREF(result);
      Py_XDECREF(pythonLegs);
      return nullptr;
   }
   bool okay = setPyString(result, "phase", phase) &&
               setPyString(result, "logical_call_token", logicalToken) &&
               setPyLong(result, "pid", static_cast<unsigned long long>(::getpid())) &&
               setPyLong(result, "loop_thread_id",
                         static_cast<unsigned long long>(loopThreadId)) &&
               setPyLong(result, "answer_count",
                         static_cast<unsigned long long>(answerCount)) &&
               setPyLong(result, "connected_count",
                         static_cast<unsigned long long>(connectedCount));
   for (const auto& leg : legs)
   {
      PyObject* pythonLeg = PyDict_New();
      PyObject* routes = PyList_New(0);
      if (pythonLeg == nullptr || routes == nullptr)
      {
         Py_XDECREF(pythonLeg);
         Py_XDECREF(routes);
         okay = false;
         break;
      }
      for (const auto& route : leg.routeSet)
      {
         PyObject* pythonRoute = PyUnicode_FromStringAndSize(
            route.data(), static_cast<Py_ssize_t>(route.size()));
         if (pythonRoute == nullptr || PyList_Append(routes, pythonRoute) != 0)
         {
            Py_XDECREF(pythonRoute);
            okay = false;
            break;
         }
         Py_DECREF(pythonRoute);
      }
      okay = okay &&
             setPyString(pythonLeg, "name", leg.spec.name) &&
             setPyString(pythonLeg, "call_id", leg.callId) &&
             setPyString(pythonLeg, "local_tag", leg.localTag) &&
             setPyString(pythonLeg, "remote_to_tag", leg.remoteTag) &&
             setPyString(pythonLeg, "remote_target_contact", leg.remoteTarget) &&
             setPyString(pythonLeg, "business_context_key", logicalToken) &&
             setPyLong(pythonLeg, "last_cseq", leg.requestCSeq) &&
             setPyLong(pythonLeg, "handle_id", leg.handleId) &&
             setPyBool(pythonLeg, "handle_attached_to_logical_token",
                       leg.associationVerified) &&
             PyDict_SetItemString(pythonLeg, "route_set", routes) == 0;
      Py_DECREF(routes);
      if (!okay || PyList_Append(pythonLegs, pythonLeg) != 0)
      {
         Py_DECREF(pythonLeg);
         okay = false;
         break;
      }
      Py_DECREF(pythonLeg);
   }
   if (okay)
   {
      okay = PyDict_SetItemString(result, "legs", pythonLegs) == 0;
   }
   Py_DECREF(pythonLegs);
   if (!okay)
   {
      Py_DECREF(result);
      return nullptr;
   }
   return result;
}

PyObject* runNative(const std::string& phase,
                    int clientPort,
                    const std::string& logicalToken,
                    std::vector<LegRuntime>& legs,
                    PyObject* policyCallback)
{
   const long loopThreadId = currentOsThreadId();
   const std::thread::id loopThread = std::this_thread::get_id();
   if (logicalToken.empty())
   {
      throw std::runtime_error("logical call token must not be empty");
   }
   if (clientPort < 1024 || clientPort > 65535)
   {
      throw std::runtime_error("client UDP port is out of range");
   }

   Log::initialize(Log::Cout, Log::None, Data("as_two_leg_restart_recovery"));
   SipStack stack;
   stack.addTransport(UDP, clientPort, V4, StunDisabled, Data("127.0.0.1"));
   auto profile = std::make_shared<MasterProfile>();
   profile->setDefaultFrom(
      NameAddr(Uri(Data("sip:as-recovery@127.0.0.1"))));
   TwoLegInviteHandler handler(legs, phase, logicalToken, policyCallback,
                               loopThreadId);
   DialogUsageManager dum(stack);
   dum.setMasterProfile(profile);
   dum.setInviteSessionHandler(&handler);

   const std::string offerText(kOfferSdp);
   const HeaderFieldValue offerField(offerText.data(), offerText.size());
   const Mime offerType("application", "sdp");
   const SdpContents offer(offerField, offerType);
   std::cout << "DUM_EVENT_LOOP_START phase=" << phase
             << " pid=" << ::getpid()
             << " thread_tid=" << loopThreadId << std::endl;

   if (phase == "phase-a")
   {
      for (auto& leg : legs)
      {
         sendInviteForLeg(dum, profile, offer, phase, logicalToken, leg);
      }
      if (legs[0].callId == legs[1].callId ||
          legs[0].localTag == legs[1].localTag)
      {
         throw std::runtime_error("phase-A legs did not receive distinct SIP identities");
      }
      waitForBoth(stack, dum, handler, legs);
      drainAckWork(stack, dum);
   }
   else
   {
      for (auto& leg : legs)
      {
         sendInviteForLeg(dum, profile, offer, phase, logicalToken, leg);
         waitForLeg(stack, dum, handler, leg);
         drainAckWork(stack, dum);
      }
   }

   if (handler.answerCount() != 2 || handler.connectedCount() != 2)
   {
      throw std::runtime_error("DUM did not receive both SDP answers and connected callbacks");
   }
   validateRetainedHandles(legs, logicalToken, phase);
   std::cout << "DUM_EVENT_LOOP_STOP phase=" << phase
             << " thread_tid=" << currentOsThreadId()
             << " callbacks_on_loop_thread="
             << (std::this_thread::get_id() == loopThread ? "true" : "false")
             << std::endl;
   return makeResult(legs, logicalToken, phase, loopThreadId,
                     handler.answerCount(), handler.connectedCount());
}

PyObject* runPhase(PyObject*, PyObject* args)
{
   const char* phaseText = nullptr;
   int clientPort = 0;
   const char* logicalTokenText = nullptr;
   PyObject* pythonLegs = nullptr;
   PyObject* policyCallback = nullptr;
   if (!PyArg_ParseTuple(args, "sisOO:run_phase", &phaseText, &clientPort,
                         &logicalTokenText, &pythonLegs, &policyCallback))
   {
      return nullptr;
   }
   if (!PyCallable_Check(policyCallback))
   {
      PyErr_SetString(PyExc_TypeError, "policy callback must be callable");
      return nullptr;
   }

   const std::string phase(phaseText);
   const std::string logicalToken(logicalTokenText);
   if (phase != "phase-a" && phase != "phase-b")
   {
      PyErr_SetString(PyExc_ValueError, "phase must be 'phase-a' or 'phase-b'");
      return nullptr;
   }

   std::vector<LegRuntime> legs;
   if (!parseLegSpecs(phase, pythonLegs, legs))
   {
      return nullptr;
   }
   try
   {
      return runNative(phase, clientPort, logicalToken, legs, policyCallback);
   }
   catch (const std::exception& error)
   {
      PyErr_SetString(PyExc_RuntimeError, error.what());
      return nullptr;
   }
   catch (...)
   {
      PyErr_SetString(PyExc_RuntimeError, "unknown C++ exception in run_phase");
      return nullptr;
   }
}

PyMethodDef Methods[] = {
   {"run_phase", runPhase, METH_VARARGS,
    "Run two real DUM UAC legs on the calling event-loop thread."},
   {nullptr, nullptr, 0, nullptr},
};

PyModuleDef Module = {
   PyModuleDef_HEAD_INIT,
   "_as_resip_two_leg",
   nullptr,
   -1,
   Methods,
};

} // namespace

PyMODINIT_FUNC PyInit__as_resip_two_leg()
{
   return PyModule_Create(&Module);
}