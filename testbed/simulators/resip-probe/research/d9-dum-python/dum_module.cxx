#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <iostream>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <utility>

#include <sys/syscall.h>
#include <unistd.h>

#include "resip/stack/Headers.hxx"
#include "resip/stack/NameAddr.hxx"
#include "resip/stack/SipMessage.hxx"
#include "resip/stack/SipStack.hxx"
#include "resip/stack/Transport.hxx"
#include "resip/stack/Uri.hxx"
#include "resip/dum/AppDialog.hxx"
#include "resip/dum/AppDialogSet.hxx"
#include "resip/dum/AppDialogSetFactory.hxx"
#include "resip/dum/DialogUsageManager.hxx"
#include "resip/dum/InviteSessionHandler.hxx"
#include "resip/dum/MasterProfile.hxx"
#include "resip/dum/ServerInviteSession.hxx"
#include "rutil/Data.hxx"
#include "rutil/Log.hxx"

using namespace resip;

namespace
{

constexpr const char* kCapsuleName = "_resip_dum.ServerState";

struct ServerState
{
   explicit ServerState(PyObject* callbackValue) : callback(callbackValue) {}

   PyObject* callback;
   std::thread worker;
   std::atomic<bool> stopRequested{false};
   std::atomic<bool> callbackRan{false};
   std::atomic<bool> callbackException{false};
   std::atomic<bool> responseIssued{false};
   std::atomic<long> eventLoopThreadId{0};
   std::atomic<long> callbackThreadId{0};
   std::atomic<int> responseStatus{0};
   int serverPort{0};

   std::mutex mutex;
   std::condition_variable readyCondition;
   bool ready{false};
   std::string startupError;
   std::string workerError;
   std::string callbackError;
   std::string callId;
   std::string callingNumber;
   std::string requestUser;
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

   std::string message = "Python callback raised an exception";
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

void recordCallbackError(ServerState* state, const std::string& message)
{
   {
      std::lock_guard<std::mutex> lock(state->mutex);
      state->callbackError = message;
   }
   state->callbackException.store(true);
   std::cerr << "PYTHON_CALLBACK_ERROR message=" << message << std::endl;
}

int callPythonPolicy(ServerState* state,
                     const std::string& callId,
                     const std::string& callingNumber,
                     const std::string& requestUser)
{
   const long callbackThreadId = currentOsThreadId();
   state->callbackThreadId.store(callbackThreadId);
   std::cout << "PYTHON_CALLBACK_ENTER thread_tid=" << callbackThreadId
             << " call_id=" << callId << " request_user=" << requestUser
             << std::endl;

   PyGILState_STATE gilState = PyGILState_Ensure();
   PyObject* callIdArg = PyUnicode_FromStringAndSize(
      callId.data(), static_cast<Py_ssize_t>(callId.size()));
   PyObject* callingNumberArg = PyUnicode_FromStringAndSize(
      callingNumber.data(), static_cast<Py_ssize_t>(callingNumber.size()));
   PyObject* requestUserArg = PyUnicode_FromStringAndSize(
      requestUser.data(), static_cast<Py_ssize_t>(requestUser.size()));

   PyObject* result = nullptr;
   if (callIdArg != nullptr && callingNumberArg != nullptr && requestUserArg != nullptr)
   {
      result = PyObject_CallFunctionObjArgs(
         state->callback, callIdArg, callingNumberArg, requestUserArg, nullptr);
   }

   Py_XDECREF(callIdArg);
   Py_XDECREF(callingNumberArg);
   Py_XDECREF(requestUserArg);

   const bool hasResult = result != nullptr;
   long statusCode = 500;
   std::string callbackError;
   if (hasResult)
   {
      statusCode = PyLong_AsLong(result);
      Py_DECREF(result);
   }

   if (PyErr_Occurred() != nullptr || !hasResult)
   {
      callbackError = takePythonError();
   }
   else if (statusCode < 100 || statusCode > 699)
   {
      callbackError = "Python callback returned a status outside 100..699";
   }

   if (!callbackError.empty())
   {
      recordCallbackError(state, callbackError);
      statusCode = 500;
   }

   PyGILState_Release(gilState);
   return static_cast<int>(statusCode);
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

class MinimalInviteSessionHandler : public InviteSessionHandler
{
public:
   explicit MinimalInviteSessionHandler(ServerState* state)
      : InviteSessionHandler(false), mState(state)
   {
   }

   void onNewSession(ServerInviteSessionHandle session,
                     InviteSession::OfferAnswerType,
                     const SipMessage& message) override
   {
      const std::string callId = message.header(h_CallId).value().c_str();
      const std::string callingNumber = message.header(h_From).uri().user().c_str();
      const std::string requestUser =
         message.header(h_RequestLine).uri().user().c_str();

      {
         std::lock_guard<std::mutex> lock(mState->mutex);
         mState->callId = callId;
         mState->callingNumber = callingNumber;
         mState->requestUser = requestUser;
      }
      mState->callbackRan.store(true);

      const int statusCode =
         callPythonPolicy(mState, callId, callingNumber, requestUser);
      mState->responseStatus.store(statusCode);
      session->reject(statusCode);
      mState->responseIssued.store(true);
      std::cout << "DUM_UAS_REJECT status=" << statusCode
                << " event_loop_tid=" << mState->eventLoopThreadId.load()
                << " callback_tid=" << mState->callbackThreadId.load()
                << std::endl;
   }

   void onNewSession(ClientInviteSessionHandle,
                     InviteSession::OfferAnswerType,
                     const SipMessage&) override
   {
   }

   void onFailure(ClientInviteSessionHandle, const SipMessage&) override {}
   void onEarlyMedia(ClientInviteSessionHandle, const SipMessage&,
                     const SdpContents&) override
   {
   }
   void onProvisional(ClientInviteSessionHandle, const SipMessage&) override {}
   void onConnected(ClientInviteSessionHandle, const SipMessage&) override {}
   void onConnected(InviteSessionHandle, const SipMessage&) override {}
   void onTerminated(InviteSessionHandle, TerminatedReason,
                    const SipMessage*) override
   {
   }
   void onForkDestroyed(ClientInviteSessionHandle) override {}
   void onRedirected(ClientInviteSessionHandle, const SipMessage&) override {}
   void onAnswer(InviteSessionHandle, const SipMessage&,
                 const SdpContents&) override
   {
   }
   void onOffer(InviteSessionHandle, const SipMessage&,
                const SdpContents&) override
   {
   }
   void onOfferRequired(InviteSessionHandle, const SipMessage&) override {}
   void onOfferRejected(InviteSessionHandle, const SipMessage*) override {}
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
};

void markReady(ServerState* state, const std::string& startupError = {})
{
   {
      std::lock_guard<std::mutex> lock(state->mutex);
      state->startupError = startupError;
      state->ready = true;
   }
   state->readyCondition.notify_all();
}

void recordWorkerError(ServerState* state, const std::string& message)
{
   {
      std::lock_guard<std::mutex> lock(state->mutex);
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

void runServer(ServerState* state, int port)
{
   state->eventLoopThreadId.store(currentOsThreadId());
   std::cout << "DUM_EVENT_LOOP_START thread_tid="
             << state->eventLoopThreadId.load() << std::endl;

   try
   {
      Log::initialize(Log::Cout, Log::None, Data("as_resip_dum_python_slice"));
      SipStack stack;
      stack.addTransport(UDP, port, V4, StunDisabled, Data("127.0.0.1"));

      MinimalInviteSessionHandler handler(state);
      DialogUsageManager dum(stack);

      auto profile = std::make_shared<MasterProfile>();
      Data contact = "sip:as-slice@127.0.0.1:" + Data(port);
      profile->setOverrideHostAndPort(Uri(contact));
      profile->setDefaultFrom(NameAddr(contact));
      dum.setMasterProfile(profile);
      dum.setInviteSessionHandler(&handler);
      dum.setAppDialogSetFactory(std::make_unique<MinimalAppDialogSetFactory>());

      state->serverPort = port;
      markReady(state);
      std::cout << "DUM_LISTENING address=127.0.0.1 port=" << port << std::endl;

      while (!state->stopRequested.load())
      {
         stack.process(50);
         while (dum.process())
         {
         }
      }
      std::cout << "DUM_EVENT_LOOP_STOP thread_tid="
                << state->eventLoopThreadId.load() << std::endl;
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
   return static_cast<ServerState*>(PyCapsule_GetPointer(capsule, kCapsuleName));
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

PyObject* startUas(PyObject*, PyObject* args)
{
   int port = 0;
   PyObject* callback = nullptr;
   if (!PyArg_ParseTuple(args, "iO:start_uas", &port, &callback))
   {
      return nullptr;
   }
   if (port < 1 || port > 65535)
   {
      PyErr_SetString(PyExc_ValueError, "port must be between 1 and 65535");
      return nullptr;
   }
   if (!PyCallable_Check(callback))
   {
      PyErr_SetString(PyExc_TypeError, "callback must be callable");
      return nullptr;
   }

   auto* state = new ServerState(callback);
   Py_INCREF(callback);
   try
   {
      state->worker = std::thread(runServer, state, port);
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
      std::unique_lock<std::mutex> lock(state->mutex);
      ready = state->readyCondition.wait_for(
         lock, std::chrono::seconds(5), [state]() { return state->ready; });
   }
   Py_END_ALLOW_THREADS

   std::string startupError;
   if (ready)
   {
      std::lock_guard<std::mutex> lock(state->mutex);
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

   std::string callbackError;
   std::string callId;
   std::string callingNumber;
   std::string requestUser;
   std::string workerError;
   {
      std::lock_guard<std::mutex> lock(state->mutex);
      callbackError = state->callbackError;
      callId = state->callId;
      callingNumber = state->callingNumber;
      requestUser = state->requestUser;
      workerError = state->workerError;
   }

   PyObject* result = PyDict_New();
   if (result == nullptr)
   {
      return nullptr;
   }
   const bool ok =
      addDictItem(result, "callback_ran", PyBool_FromLong(state->callbackRan.load())) &&
      addDictItem(result, "callback_exception",
                  PyBool_FromLong(state->callbackException.load())) &&
      addDictItem(result, "response_issued",
                  PyBool_FromLong(state->responseIssued.load())) &&
      addDictItem(result, "event_loop_thread_id",
                  PyLong_FromLong(state->eventLoopThreadId.load())) &&
      addDictItem(result, "callback_thread_id",
                  PyLong_FromLong(state->callbackThreadId.load())) &&
      addDictItem(result, "response_status",
                  PyLong_FromLong(state->responseStatus.load())) &&
      addDictItem(result, "server_port", PyLong_FromLong(state->serverPort)) &&
      addDictItem(result, "call_id",
                  PyUnicode_FromStringAndSize(
                     callId.data(), static_cast<Py_ssize_t>(callId.size()))) &&
      addDictItem(result, "calling_number",
                  PyUnicode_FromStringAndSize(
                     callingNumber.data(), static_cast<Py_ssize_t>(callingNumber.size()))) &&
      addDictItem(result, "request_user",
                  PyUnicode_FromStringAndSize(
                     requestUser.data(), static_cast<Py_ssize_t>(requestUser.size()))) &&
      addDictItem(result, "callback_error",
                  PyUnicode_FromStringAndSize(
                     callbackError.data(), static_cast<Py_ssize_t>(callbackError.size()))) &&
      addDictItem(result, "worker_error",
                  PyUnicode_FromStringAndSize(
                     workerError.data(), static_cast<Py_ssize_t>(workerError.size())));
   if (!ok)
   {
      Py_DECREF(result);
      return nullptr;
   }
   return result;
}

PyMethodDef methods[] = {
   {"start_uas", startUas, METH_VARARGS,
    "Start a DUM UAS worker on an explicit UDP port."},
   {"stop_and_join", stopUas, METH_VARARGS,
    "Stop and join the DUM worker, returning callback and thread markers."},
   {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {
   PyModuleDef_HEAD_INIT,
   "_resip_dum",
   "Throwaway reSIProcate DUM to CPython slice.",
   -1,
   methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__resip_dum()
{
   return PyModule_Create(&module);
}