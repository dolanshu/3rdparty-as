#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cctype>
#include <cstring>
#include <iostream>
#include <sys/socket.h>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <map>
#include <unordered_map>
#include <utility>

#include <openssl/evp.h>
#include <openssl/ssl.h>
#include <openssl/x509.h>

#include "resip/stack/Contents.hxx"
#include "resip/stack/SecurityTypes.hxx"
#include "resip/stack/ssl/Security.hxx"
#include "resip/stack/ssl/TlsBaseTransport.hxx"
#include "resip/stack/Headers.hxx"
#include "resip/stack/MethodTypes.hxx"
#include "resip/stack/NameAddr.hxx"
#include "resip/stack/SipMessage.hxx"
#include "resip/stack/SipStack.hxx"
#include "resip/stack/Tuple.hxx"
#include "resip/stack/ConnectionBase.hxx"
#include "resip/stack/Transport.hxx"
#include "resip/stack/Uri.hxx"
#include "resip/dum/AppDialog.hxx"
#include "resip/dum/AppDialogSet.hxx"
#include "resip/dum/AppDialogSetFactory.hxx"
#include "resip/dum/DialogUsageManager.hxx"
#include "resip/dum/InviteSessionHandler.hxx"
#include "resip/dum/MasterProfile.hxx"
#include "resip/dum/ClientInviteSession.hxx"
#include "resip/dum/ServerInviteSession.hxx"
#include "rutil/Data.hxx"
#include "rutil/Log.hxx"

using namespace resip;

namespace
{

constexpr const char* kCapsuleName = "as_platform._resip_runtime.ListenerState";

struct InviteCallbackResult
{
   int statusCode{500};
   std::string routeTarget;
   bool forwardOutbound{false};
};

class MinimalInviteSessionHandler;

struct TransportConfig
{
   bool enableUdp{true};
   bool enableTcp{false};
   bool enableTls{false};
   bool tlsOnly{false};
   bool requireClientCertificate{false};
   bool requestClientCertificate{false};
   bool acceptAllInvites{false};
   bool earlyCancelHarness{false};
   std::string certificatePath;
   std::string privateKeyPath;
   std::string caPath;
   std::string bindAddress{"127.0.0.1"};
   std::string advertisedAddress{"127.0.0.1"};
};

struct ListenerState
{
   explicit ListenerState(PyObject* callbackValue) : callback(callbackValue) {}

   PyObject* callback;
   PyObject* establishedCallback{nullptr};
   PyObject* terminatedCallback{nullptr};
   std::thread worker;
   std::atomic<bool> stopRequested{false};
   std::atomic<bool> reloadCertificatesRequested{false};
   int serverPort{0};
   int tcpPort{0};
   int tlsPort{0};
   SipStack* stack{nullptr};
   TransportConfig transportConfig;

   mutable std::mutex fingerprintMutex;
   std::unordered_map<FlowKey, std::string> peerFingerprints;
   std::unordered_map<std::string, std::string> peerFingerprintsByEndpoint;

   std::mutex mutex;
   std::condition_variable readyCondition;
   bool ready{false};
   std::string startupError;
   std::string workerError;
   MinimalInviteSessionHandler* sessionHandler{nullptr};

   void storePeerFingerprint(FlowKey flowKey,
                           const std::string& endpointKey,
                           const std::string& fingerprint)
   {
      if (fingerprint.empty())
      {
         return;
      }
      std::lock_guard<std::mutex> lock(fingerprintMutex);
      peerFingerprints[flowKey] = fingerprint;
      if (!endpointKey.empty())
      {
         peerFingerprintsByEndpoint[endpointKey] = fingerprint;
      }
      static constexpr std::size_t kMaxPeerFingerprints = 2048;
      while (peerFingerprints.size() > kMaxPeerFingerprints && !peerFingerprints.empty())
      {
         peerFingerprints.erase(peerFingerprints.begin());
      }
      while (peerFingerprintsByEndpoint.size() > kMaxPeerFingerprints &&
             !peerFingerprintsByEndpoint.empty())
      {
         peerFingerprintsByEndpoint.erase(peerFingerprintsByEndpoint.begin());
      }
   }

   std::string lookupPeerFingerprint(FlowKey flowKey, const std::string& endpointKey) const
   {
      std::lock_guard<std::mutex> lock(fingerprintMutex);
      const auto found = peerFingerprints.find(flowKey);
      if (found != peerFingerprints.end())
      {
         return found->second;
      }
      const auto endpointFound = peerFingerprintsByEndpoint.find(endpointKey);
      if (endpointFound != peerFingerprintsByEndpoint.end())
      {
         return endpointFound->second;
      }
      return {};
   }
};

std::string toHexLower(const unsigned char* data, size_t length)
{
   static constexpr char hexDigits[] = "0123456789abcdef";
   std::string encoded;
   encoded.reserve(length * 2);
   for (size_t index = 0; index < length; ++index)
   {
      encoded.push_back(hexDigits[(data[index] >> 4) & 0x0f]);
      encoded.push_back(hexDigits[data[index] & 0x0f]);
   }
   return encoded;
}

std::string certificateFingerprintSha256(X509* certificate)
{
   if (certificate == nullptr)
   {
      return {};
   }
   unsigned char* der = nullptr;
   const int derLength = i2d_X509(certificate, &der);
   if (derLength <= 0 || der == nullptr)
   {
      return {};
   }
   unsigned char digest[EVP_MAX_MD_SIZE];
   unsigned int digestLength = 0;
   if (EVP_Digest(der, static_cast<size_t>(derLength), digest, &digestLength, EVP_sha256(), nullptr) != 1)
   {
      OPENSSL_free(der);
      return {};
   }
   OPENSSL_free(der);
   return "sha256:" + toHexLower(digest, digestLength);
}

int listenerStateSslCtxExIndex()
{
   static int index = SSL_CTX_get_ex_new_index(0, nullptr, nullptr, nullptr, nullptr);
   return index;
}

void storePeerFingerprintFromCertificate(ListenerState* state, SSL* ssl, X509* certificate)
{
   if (state == nullptr || ssl == nullptr || certificate == nullptr)
   {
      return;
   }
   const std::string fingerprint = certificateFingerprintSha256(certificate);
   if (fingerprint.empty())
   {
      return;
   }

   ConnectionBase* connection = static_cast<ConnectionBase*>(SSL_get_ex_data(
      ssl, BaseSecurity::getResipConnectionExDataIdx()));
   FlowKey flowKey{};
   std::string endpointKey;
   if (connection != nullptr)
   {
      flowKey = connection->getFlowKey();
      const Tuple& who = connection->who();
      endpointKey =
         std::string(Tuple::inet_ntop(who).c_str()) + ":" + std::to_string(who.getPort());
   }
   else
   {
      const int fd = SSL_get_fd(ssl);
      if (fd >= 0)
      {
         sockaddr_storage peerAddress{};
         socklen_t peerLength = sizeof(peerAddress);
         if (getpeername(fd, reinterpret_cast<sockaddr*>(&peerAddress), &peerLength) == 0)
         {
            Tuple who(*reinterpret_cast<const sockaddr*>(&peerAddress), TLS);
            endpointKey =
               std::string(Tuple::inet_ntop(who).c_str()) + ":" + std::to_string(who.getPort());
         }
      }
   }
   if (!endpointKey.empty())
   {
      state->storePeerFingerprint(flowKey, endpointKey, fingerprint);
   }
}

extern "C" int peerFingerprintVerifyCallback(int preverifyOk, X509_STORE_CTX* context)
{
   ListenerState* state = nullptr;
   if (X509_STORE_CTX_get_error_depth(context) == 0)
   {
      SSL* ssl = static_cast<SSL*>(X509_STORE_CTX_get_ex_data(
         context, SSL_get_ex_data_X509_STORE_CTX_idx()));
      if (ssl != nullptr)
      {
         SSL_CTX* sslContext = SSL_get_SSL_CTX(ssl);
         state = static_cast<ListenerState*>(SSL_CTX_get_ex_data(
            sslContext, listenerStateSslCtxExIndex()));
         X509* certificate = X509_STORE_CTX_get_current_cert(context);
         if (state != nullptr && certificate != nullptr)
         {
            storePeerFingerprintFromCertificate(state, ssl, certificate);
         }
      }
   }
   if (state != nullptr && state->transportConfig.requireClientCertificate)
   {
      return preverifyOk;
   }
   return 1;
}

std::string transportLabel(const Tuple& source)
{
   std::string label = Tuple::toData(source.getType()).c_str();
   for (char& character : label)
   {
      character = static_cast<char>(std::tolower(static_cast<unsigned char>(character)));
   }
   return label;
}

bool parseTransportConfig(PyObject* configObject, TransportConfig& config)
{
   if (configObject == nullptr || configObject == Py_None)
   {
      return true;
   }
   if (!PyDict_Check(configObject))
   {
      PyErr_SetString(PyExc_TypeError, "transport config must be a dict");
      return false;
   }

   PyObject* enableUdp = PyDict_GetItemString(configObject, "enable_udp");
   if (enableUdp != nullptr)
   {
      config.enableUdp = PyObject_IsTrue(enableUdp) == 1;
   }
   PyObject* enableTcp = PyDict_GetItemString(configObject, "enable_tcp");
   if (enableTcp != nullptr)
   {
      config.enableTcp = PyObject_IsTrue(enableTcp) == 1;
   }
   PyObject* enableTls = PyDict_GetItemString(configObject, "enable_tls");
   if (enableTls != nullptr)
   {
      config.enableTls = PyObject_IsTrue(enableTls) == 1;
   }
   PyObject* tlsOnly = PyDict_GetItemString(configObject, "tls_only");
   if (tlsOnly != nullptr)
   {
      config.tlsOnly = PyObject_IsTrue(tlsOnly) == 1;
   }
   PyObject* requireClientCertificate =
      PyDict_GetItemString(configObject, "require_client_certificate");
   if (requireClientCertificate != nullptr)
   {
      config.requireClientCertificate = PyObject_IsTrue(requireClientCertificate) == 1;
   }
   PyObject* requestClientCertificate =
      PyDict_GetItemString(configObject, "request_client_certificate");
   if (requestClientCertificate != nullptr)
   {
      config.requestClientCertificate = PyObject_IsTrue(requestClientCertificate) == 1;
   }
   PyObject* acceptAllInvites = PyDict_GetItemString(configObject, "accept_all_invites");
   if (acceptAllInvites != nullptr)
   {
      config.acceptAllInvites = PyObject_IsTrue(acceptAllInvites) == 1;
   }
   PyObject* earlyCancelHarness = PyDict_GetItemString(configObject, "early_cancel_harness");
   if (earlyCancelHarness != nullptr)
   {
      config.earlyCancelHarness = PyObject_IsTrue(earlyCancelHarness) == 1;
   }

   auto readPath = [&](const char* key, std::string& target) -> bool {
      PyObject* value = PyDict_GetItemString(configObject, key);
      if (value == nullptr || value == Py_None)
      {
         target.clear();
         return true;
      }
      if (!PyUnicode_Check(value))
      {
         PyErr_SetString(PyExc_TypeError, "transport config path values must be str");
         return false;
      }
      const char* utf8 = PyUnicode_AsUTF8(value);
      if (utf8 == nullptr)
      {
         return false;
      }
      target = utf8;
      return true;
   };

   if (!readPath("certificate_path", config.certificatePath) ||
       !readPath("private_key_path", config.privateKeyPath) ||
       !readPath("ca_path", config.caPath))
   {
      return false;
   }

   auto readAddress = [&](const char* key, std::string& target) -> bool {
      PyObject* value = PyDict_GetItemString(configObject, key);
      if (value == nullptr || value == Py_None)
      {
         return true;
      }
      if (!PyUnicode_Check(value))
      {
         PyErr_SetString(PyExc_TypeError, "transport config address values must be str");
         return false;
      }
      const char* utf8 = PyUnicode_AsUTF8(value);
      if (utf8 == nullptr)
      {
         return false;
      }
      if (utf8[0] != '\0')
      {
         target = utf8;
      }
      return true;
   };

   if (!readAddress("bind_address", config.bindAddress) ||
       !readAddress("advertised_address", config.advertisedAddress))
   {
      return false;
   }
   if (PyDict_GetItemString(configObject, "advertised_address") == nullptr &&
       config.advertisedAddress == "127.0.0.1" && config.bindAddress != "127.0.0.1")
   {
      config.advertisedAddress = config.bindAddress;
   }
   return true;
}

int mapUpstreamFailureStatus(int downstreamStatus)
{
   switch (downstreamStatus)
   {
   case 408:
   case 480:
   case 486:
   case 503:
   case 504:
      return downstreamStatus;
   default:
      break;
   }
   if (downstreamStatus >= 400 && downstreamStatus <= 699)
   {
      return 502;
   }
   return 502;
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

PyObject* buildPeerDict(const Tuple& source, ListenerState* state)
{
   const std::string address = Tuple::inet_ntop(source).c_str();
   const int port = source.getPort();
   const std::string connectionId = address + ":" + std::to_string(port);
   const std::string transport = transportLabel(source);
   std::string fingerprint;
   if (state != nullptr)
   {
      fingerprint = state->lookupPeerFingerprint(source.getFlowKey(), connectionId);
   }
   PyObject* dict = PyDict_New();
   if (dict == nullptr)
   {
      return nullptr;
   }
   PyObject* certificateId = Py_None;
   if (!fingerprint.empty())
   {
      certificateId = PyUnicode_FromString(fingerprint.c_str());
   }
   else
   {
      Py_INCREF(Py_None);
   }
   const bool ok = addDictItem(dict, "address", PyUnicode_FromString(address.c_str())) &&
                 addDictItem(dict, "port", PyLong_FromLong(port)) &&
                 addDictItem(dict, "connection_id", PyUnicode_FromString(connectionId.c_str())) &&
                 addDictItem(dict, "transport", PyUnicode_FromString(transport.c_str())) &&
                 addDictItem(dict, "certificate_id", certificateId);
   if (!ok)
   {
      Py_DECREF(dict);
      return nullptr;
   }
   return dict;
}

PyObject* buildSipSummary(const SipMessage& message)
{
   const std::string method = getMethodName(message.method()).c_str();
   const std::string requestUri = message.header(h_RequestLine).uri().toString().c_str();
   const std::string callId = message.header(h_CallId).value().c_str();
   const std::string callingNumber = message.header(h_From).uri().user().c_str();
   const std::string calledNumber = message.header(h_RequestLine).uri().user().c_str();

   std::string body;
   if (message.getContents() != nullptr)
   {
      const Data& bodyData = message.getContents()->getBodyData();
      body.assign(bodyData.data(), bodyData.size());
   }

   PyObject* dict = PyDict_New();
   if (dict == nullptr)
   {
      return nullptr;
   }
   const bool ok =
      addDictItem(dict, "method", PyUnicode_FromString(method.c_str())) &&
      addDictItem(dict, "request_uri", PyUnicode_FromString(requestUri.c_str())) &&
      addDictItem(dict, "call_id", PyUnicode_FromString(callId.c_str())) &&
      addDictItem(dict, "calling_number", PyUnicode_FromString(callingNumber.c_str())) &&
      addDictItem(dict, "called_number", PyUnicode_FromString(calledNumber.c_str())) &&
      addDictItem(dict, "body",
                  PyBytes_FromStringAndSize(body.data(), static_cast<Py_ssize_t>(body.size())));
   if (!ok)
   {
      Py_DECREF(dict);
      return nullptr;
   }
   return dict;
}

PyObject* buildEstablishedLegDict(const SipMessage& message,
                                  const std::string& peerContact,
                                  const std::string& localTagOverride = {})
{
   const std::string callId = message.header(h_CallId).value().c_str();
   std::string localTag = localTagOverride;
   if (localTag.empty() && message.header(h_To).exists(p_tag))
   {
      localTag = message.header(h_To).param(p_tag).c_str();
   }
   std::string remoteTag;
   if (message.header(h_From).exists(p_tag))
   {
      remoteTag = message.header(h_From).param(p_tag).c_str();
   }
   if (remoteTag.empty())
   {
      remoteTag = "peer-remote";
   }
   if (localTag.empty())
   {
      localTag = "as-runtime-local";
   }
   const std::string localUri = message.header(h_To).uri().toString().c_str();
   const std::string remoteUri = message.header(h_From).uri().toString().c_str();
   std::string remoteTarget = peerContact;
   if (remoteTarget.empty() && message.exists(h_Contacts))
   {
      remoteTarget = message.header(h_Contacts).front().uri().toString().c_str();
   }
   if (remoteTarget.empty())
   {
      remoteTarget = remoteUri;
   }
   const int localCseq = message.exists(h_CSeq) ? static_cast<int>(message.header(h_CSeq).sequence()) : 1;
   const int remoteCseq = 1;

   PyObject* routeList = buildRouteSetList(message);
   if (routeList == nullptr)
   {
      return nullptr;
   }
   PyObject* dict = PyDict_New();
   if (dict == nullptr)
   {
      Py_DECREF(routeList);
      return nullptr;
   }
   const bool ok =
      addDictItem(dict, "call_id", PyUnicode_FromString(callId.c_str())) &&
      addDictItem(dict, "local_tag", PyUnicode_FromString(localTag.c_str())) &&
      addDictItem(dict, "remote_tag", PyUnicode_FromString(remoteTag.c_str())) &&
      addDictItem(dict, "local_uri", PyUnicode_FromString(localUri.c_str())) &&
      addDictItem(dict, "remote_uri", PyUnicode_FromString(remoteUri.c_str())) &&
      addDictItem(dict, "remote_target", PyUnicode_FromString(remoteTarget.c_str())) &&
      addDictItem(dict, "route_set", routeList) &&
      addDictItem(dict, "local_cseq", PyLong_FromLong(localCseq)) &&
      addDictItem(dict, "remote_cseq", PyLong_FromLong(remoteCseq)) &&
      addDictItem(dict, "peer_contact", PyUnicode_FromString(remoteTarget.c_str()));
   if (!ok)
   {
      Py_DECREF(dict);
      return nullptr;
   }
   return dict;
}

PyObject* buildUacLegDict(const SipMessage& outboundInvite, const SipMessage& outboundAnswer)
{
   const std::string callId = outboundInvite.header(h_CallId).value().c_str();
   std::string localTag;
   if (outboundAnswer.header(h_From).exists(p_tag))
   {
      localTag = outboundAnswer.header(h_From).param(p_tag).c_str();
   }
   std::string remoteTag;
   if (outboundAnswer.header(h_To).exists(p_tag))
   {
      remoteTag = outboundAnswer.header(h_To).param(p_tag).c_str();
   }
   const std::string localUri = outboundInvite.header(h_From).uri().toString().c_str();
   const std::string remoteUri = outboundInvite.header(h_To).uri().toString().c_str();
   std::string remoteTarget = remoteUri;
   if (outboundAnswer.exists(h_Contacts))
   {
      remoteTarget = outboundAnswer.header(h_Contacts).front().uri().toString().c_str();
   }
   const int localCseq =
      outboundInvite.exists(h_CSeq) ? static_cast<int>(outboundInvite.header(h_CSeq).sequence()) : 1;
   const int remoteCseq = 1;

   PyObject* routeList = buildRouteSetList(outboundInvite);
   if (routeList == nullptr)
   {
      return nullptr;
   }
   PyObject* dict = PyDict_New();
   if (dict == nullptr)
   {
      Py_DECREF(routeList);
      return nullptr;
   }
   const bool ok =
      addDictItem(dict, "call_id", PyUnicode_FromString(callId.c_str())) &&
      addDictItem(dict, "local_tag", PyUnicode_FromString(localTag.c_str())) &&
      addDictItem(dict, "remote_tag", PyUnicode_FromString(remoteTag.c_str())) &&
      addDictItem(dict, "local_uri", PyUnicode_FromString(localUri.c_str())) &&
      addDictItem(dict, "remote_uri", PyUnicode_FromString(remoteUri.c_str())) &&
      addDictItem(dict, "remote_target", PyUnicode_FromString(remoteTarget.c_str())) &&
      addDictItem(dict, "route_set", routeList) &&
      addDictItem(dict, "local_cseq", PyLong_FromLong(localCseq)) &&
      addDictItem(dict, "remote_cseq", PyLong_FromLong(remoteCseq));
   if (!ok)
   {
      Py_DECREF(dict);
      return nullptr;
   }
   return dict;
}

void callPythonDialogCallback(PyObject* callback, PyObject* argument)
{
   if (callback == nullptr || argument == nullptr)
   {
      Py_XDECREF(argument);
      return;
   }
   PyGILState_STATE gilState = PyGILState_Ensure();
   PyObject* result = PyObject_CallFunctionObjArgs(callback, argument, nullptr);
   Py_XDECREF(argument);
   if (result == nullptr)
   {
      const std::string error = takePythonError();
      std::cerr << "RESIP_RUNTIME_DIALOG_CALLBACK_ERROR message=" << error << std::endl;
      PyErr_Clear();
   }
   else
   {
      Py_DECREF(result);
   }
   PyGILState_Release(gilState);
}

InviteCallbackResult callPythonOnInvite(ListenerState* state, const SipMessage& message)
{
   InviteCallbackResult callbackResult;
   PyGILState_STATE gilState = PyGILState_Ensure();

   PyObject* peerDict = buildPeerDict(message.getSource(), state);
   PyObject* sipSummary = buildSipSummary(message);
   PyObject* result = nullptr;
   if (peerDict != nullptr && sipSummary != nullptr)
   {
      result = PyObject_CallFunctionObjArgs(
         state->callback, peerDict, sipSummary, nullptr);
   }

   Py_XDECREF(peerDict);
   Py_XDECREF(sipSummary);

   const bool hasResult = result != nullptr;
   long statusCode = 500;
   if (hasResult)
   {
      if (PyLong_Check(result))
      {
         statusCode = PyLong_AsLong(result);
      }
      else if (PyDict_Check(result))
      {
         PyObject* statusObject = PyDict_GetItemString(result, "status");
         PyObject* routeObject = PyDict_GetItemString(result, "route_target");
         if (statusObject != nullptr)
         {
            statusCode = PyLong_AsLong(statusObject);
         }
         if (routeObject != nullptr && PyUnicode_Check(routeObject))
         {
            const char* routeUtf8 = PyUnicode_AsUTF8(routeObject);
            if (routeUtf8 != nullptr)
            {
               callbackResult.routeTarget = routeUtf8;
               callbackResult.forwardOutbound = !callbackResult.routeTarget.empty();
            }
         }
      }
      Py_DECREF(result);
   }

   if (PyErr_Occurred() != nullptr || !hasResult)
   {
      const std::string error = takePythonError();
      std::cerr << "RESIP_RUNTIME_CALLBACK_ERROR message=" << error << std::endl;
      statusCode = 500;
   }
   else if (statusCode < 100 || statusCode > 699)
   {
      const bool acceptContinue =
         state != nullptr && state->transportConfig.acceptAllInvites && statusCode == 0;
      const bool forwardContinue = statusCode == 0 && callbackResult.forwardOutbound;
      if (!acceptContinue && !forwardContinue)
      {
         std::cerr << "RESIP_RUNTIME_CALLBACK_ERROR invalid_status=" << statusCode << std::endl;
         statusCode = 500;
      }
   }

   callbackResult.statusCode = static_cast<int>(statusCode);
   PyGILState_Release(gilState);
   return callbackResult;
}

SdpContents minimalHarnessAnswer(const std::string& advertisedAddress)
{
   const std::string answerText =
      "v=0\r\n"
      "o=as-runtime 0 0 IN IP4 " +
      advertisedAddress +
      "\r\n"
      "s=as-runtime-harness\r\n"
      "c=IN IP4 " +
      advertisedAddress +
      "\r\n"
      "t=0 0\r\n"
      "m=audio 9 RTP/AVP 0\r\n"
      "a=rtpmap:0 PCMU/8000\r\n";
   HeaderFieldValue answerValue(answerText.data(), static_cast<unsigned int>(answerText.size()));
   return SdpContents(answerValue, SdpContents::getStaticType());
}

PyObject* buildRouteSetList(const SipMessage& message)
{
   PyObject* routeList = PyList_New(0);
   if (routeList == nullptr)
   {
      return nullptr;
   }
   if (!message.exists(h_RecordRoutes))
   {
      return routeList;
   }
   const auto& routes = message.header(h_RecordRoutes);
   for (auto route = routes.begin(); route != routes.end(); ++route)
   {
      const std::string value = route->uri().toString().c_str();
      PyObject* item = PyUnicode_FromString(value.c_str());
      if (item == nullptr || PyList_Append(routeList, item) != 0)
      {
         Py_XDECREF(item);
         Py_DECREF(routeList);
         return nullptr;
      }
      Py_DECREF(item);
   }
   return routeList;
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
   explicit MinimalInviteSessionHandler(ListenerState* state)
      : InviteSessionHandler(false), mState(state)
   {
   }

   void setDum(DialogUsageManager& dum)
   {
      mDum = &dum;
   }

   void notifyDialogEstablished(const std::string& localTag)
   {
      if (mState == nullptr || mState->establishedCallback == nullptr || mNotifiedEstablished ||
          mInviteMessage == nullptr)
      {
         return;
      }
      try
      {
         mNotifiedEstablished = true;
         mEstablishedCallId = mInviteMessage->header(h_CallId).value().c_str();
         PyGILState_STATE gilState = PyGILState_Ensure();
         PyObject* legDict = buildEstablishedLegDict(*mInviteMessage, mPeerContact, localTag);
         if (legDict != nullptr && mOutboundInviteMessage != nullptr && mOutboundAnswerMessage != nullptr)
         {
            PyObject* uacDict =
               buildUacLegDict(*mOutboundInviteMessage, *mOutboundAnswerMessage);
            if (uacDict != nullptr)
            {
               PyDict_SetItemString(legDict, "uac_leg", uacDict);
               Py_DECREF(uacDict);
            }
         }
         PyObject* callback = mState->establishedCallback;
         PyObject* result = nullptr;
         if (legDict != nullptr && callback != nullptr)
         {
            result = PyObject_CallFunctionObjArgs(callback, legDict, nullptr);
         }
         Py_XDECREF(legDict);
         if (result == nullptr)
         {
            const std::string error = takePythonError();
            std::cerr << "RESIP_RUNTIME_DIALOG_CALLBACK_ERROR message=" << error << std::endl;
            PyErr_Clear();
         }
         else
         {
            Py_DECREF(result);
         }
         PyGILState_Release(gilState);
      }
      catch (const std::exception& error)
      {
         std::cerr << "RESIP_RUNTIME_DIALOG_NOTIFY_ERROR message=" << error.what() << std::endl;
         mNotifiedEstablished = false;
      }
   }

   void acceptHarnessSession(ServerInviteSessionHandle serverSession,
                             InviteSessionHandle session)
   {
      const std::string advertised =
         mState != nullptr ? mState->transportConfig.advertisedAddress : "127.0.0.1";
      SdpContents answer = minimalHarnessAnswer(advertised);
      session->provideAnswer(answer);
      if (serverSession.isValid())
      {
         serverSession->accept(200);
         mPendingEstablishedNotify = true;
      }
   }

   void consumePendingEstablishedNotify()
   {
      if (!mPendingEstablishedNotify)
      {
         return;
      }
      mPendingEstablishedNotify = false;
      notifyDialogEstablished(mHarnessLocalTag);
   }

   void onNewSession(ServerInviteSessionHandle session,
                     InviteSession::OfferAnswerType,
                     const SipMessage& message) override
   {
      const InviteCallbackResult callback = callPythonOnInvite(mState, message);
      const int statusCode = callback.statusCode;
      if (mState->transportConfig.acceptAllInvites && statusCode == 0)
      {
         mServerSession = session;
         if (message.exists(h_Contacts))
         {
            mPeerContact = message.header(h_Contacts).front().uri().toString().c_str();
         }
         else
         {
            mPeerContact = message.header(h_From).uri().toString().c_str();
         }
         mInviteMessage = std::make_unique<SipMessage>(message);
         mHarnessLocalTag = "as-runtime-local";
         session->provisional(100);
         session->provisional(180);
         return;
      }
      if (statusCode == 0 && callback.forwardOutbound && mDum != nullptr)
      {
         try
         {
            mServerSession = session;
            mForwardActive = true;
            mInviteMessage = std::make_unique<SipMessage>(message);
            if (message.exists(h_Contacts))
            {
               mPeerContact = message.header(h_Contacts).front().uri().toString().c_str();
            }
            else
            {
               mPeerContact = message.header(h_From).uri().toString().c_str();
            }
            session->provisional(100);
            Data routeData(callback.routeTarget.c_str());
            NameAddr target{Uri(routeData)};
            const Contents* inboundOffer = message.getContents();
            std::shared_ptr<SipMessage> outbound = mDum->makeInviteSession(
               target, mDum->getMasterUserProfile(), inboundOffer);
            if (!outbound)
            {
               throw std::runtime_error("DUM did not create an outbound INVITE");
            }
            const std::string incomingCallId = message.header(h_CallId).value().c_str();
            const std::string outgoingCallId = outbound->header(h_CallId).value().c_str();
            if (outgoingCallId.empty() || outgoingCallId == incomingCallId)
            {
               throw std::runtime_error("DUM did not generate a distinct outbound Call-ID");
            }
            mInboundByOutboundCallId.emplace(outgoingCallId, session);
            mOutboundInviteMessage = std::make_unique<SipMessage>(*outbound);
            mDum->send(outbound);
            std::cout << "RESIP_RUNTIME_UAC_INVITE_SENT outgoing_call_id=" << outgoingCallId
                      << " inbound_call_id=" << incomingCallId
                      << " route_uri=" << callback.routeTarget << std::endl;
            return;
         }
         catch (const std::exception& error)
         {
            std::cerr << "RESIP_RUNTIME_FORWARD_ERROR message=" << error.what() << std::endl;
            session->reject(500);
            mForwardActive = false;
            return;
         }
      }
      if (statusCode == 0)
      {
         session->reject(500);
         return;
      }
      session->reject(statusCode);
   }

   void onNewSession(ClientInviteSessionHandle clientSession,
                     InviteSession::OfferAnswerType,
                     const SipMessage& message) override
   {
      if (!mForwardActive)
      {
         return;
      }
      mOutboundDialogSet =
         std::make_unique<DialogSetId>(clientSession->getDialogId().getDialogSetId());
      std::cout << "RESIP_RUNTIME_UAC_NEW_SESSION outgoing_call_id="
                << message.header(h_CallId).value().c_str() << std::endl;
   }

   void onFailure(ClientInviteSessionHandle, const SipMessage& message) override
   {
      if (!mForwardActive)
      {
         return;
      }
      const std::string outgoingCallId = message.header(h_CallId).value().c_str();
      const int downstreamStatus = message.header(h_StatusLine).statusCode();
      std::cout << "RESIP_RUNTIME_UAC_FAILURE outgoing_call_id=" << outgoingCallId
                << " status=" << downstreamStatus << std::endl;

      const auto inbound = mInboundByOutboundCallId.find(outgoingCallId);
      if (inbound == mInboundByOutboundCallId.end())
      {
         std::cerr << "RESIP_RUNTIME_UAC_CORRELATION_MISS outgoing_call_id="
                   << outgoingCallId << std::endl;
         return;
      }

      const int upstreamStatus = mapUpstreamFailureStatus(downstreamStatus);
      inbound->second->reject(upstreamStatus);
      mInboundByOutboundCallId.erase(inbound);
      mForwardActive = false;
      std::cout << "RESIP_RUNTIME_UAS_FAILURE_MAPPED outgoing_call_id=" << outgoingCallId
                << " downstream_status=" << downstreamStatus
                << " upstream_status=" << upstreamStatus << std::endl;
   }
   void onEarlyMedia(ClientInviteSessionHandle, const SipMessage&,
                     const SdpContents&) override
   {
   }
   void onProvisional(ClientInviteSessionHandle, const SipMessage&) override {}
   void onConnected(ClientInviteSessionHandle, const SipMessage&) override {}
   void onConnected(InviteSessionHandle, const SipMessage&) override {}
   void onTerminated(InviteSessionHandle session, TerminatedReason reason,
                    const SipMessage* message) override
   {
      if (mForwardActive && reason == RemoteCancel && message != nullptr && mDum != nullptr &&
          mInviteMessage != nullptr)
      {
         const std::string callId = message->header(h_CallId).value().c_str();
         const std::string inboundCallId = mInviteMessage->header(h_CallId).value().c_str();
         if (callId == inboundCallId && mOutboundDialogSet != nullptr)
         {
            try
            {
               mDum->end(*mOutboundDialogSet);
               std::cout << "RESIP_RUNTIME_OUTBOUND_CANCEL_FORWARD inbound_call_id="
                         << inboundCallId << std::endl;
            }
            catch (const std::exception& error)
            {
               std::cerr << "RESIP_RUNTIME_OUTBOUND_CANCEL_ERROR message=" << error.what()
                         << std::endl;
            }
         }
      }

      if (mState == nullptr || mState->terminatedCallback == nullptr || mEstablishedCallId.empty())
      {
         return;
      }
      std::string callId = mEstablishedCallId;
      if (message != nullptr)
      {
         callId = message->header(h_CallId).value().c_str();
      }
      else if (session.isValid())
      {
         callId = session->getCallId().c_str();
      }
      PyObject* callIdObject = PyUnicode_FromString(callId.c_str());
      callPythonDialogCallback(mState->terminatedCallback, callIdObject);
      mEstablishedCallId.clear();
      mNotifiedEstablished = false;
   }
   void onForkDestroyed(ClientInviteSessionHandle) override {}
   void onRedirected(ClientInviteSessionHandle, const SipMessage&) override {}
   void onAnswer(InviteSessionHandle, const SipMessage& message,
                 const SdpContents& answer) override
   {
      if (!mForwardActive)
      {
         return;
      }
      const std::string outgoingCallId = message.header(h_CallId).value().c_str();
      const int status = message.header(h_StatusLine).statusCode();
      if (status != 200)
      {
         return;
      }
      const auto inbound = mInboundByOutboundCallId.find(outgoingCallId);
      if (inbound == mInboundByOutboundCallId.end())
      {
         return;
      }
      try
      {
         inbound->second->provideAnswer(answer);
         inbound->second->accept(200);
         mHarnessLocalTag = inbound->second->getDialogId().getLocalTag().c_str();
         mOutboundAnswerMessage = std::make_unique<SipMessage>(message);
         mPendingEstablishedNotify = true;
         mForwardActive = false;
         mInboundByOutboundCallId.erase(inbound);
         std::cout << "RESIP_RUNTIME_UAS_ANSWER_RELAYED outgoing_call_id=" << outgoingCallId
                   << std::endl;
      }
      catch (const std::exception& error)
      {
         std::cerr << "RESIP_RUNTIME_ANSWER_RELAY_ERROR message=" << error.what() << std::endl;
      }
   }
   void onOffer(InviteSessionHandle session, const SipMessage&,
                const SdpContents&) override
   {
      if (!mState->transportConfig.acceptAllInvites || !mServerSession.isValid())
      {
         return;
      }
      if (mState->transportConfig.earlyCancelHarness)
      {
         return;
      }
      acceptHarnessSession(mServerSession, session);
   }
   void onOfferRequired(InviteSessionHandle session, const SipMessage&) override
   {
      if (!mState->transportConfig.acceptAllInvites || !mServerSession.isValid())
      {
         return;
      }
      if (mState->transportConfig.earlyCancelHarness)
      {
         return;
      }
      acceptHarnessSession(mServerSession, session);
   }
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
   ListenerState* mState;
   DialogUsageManager* mDum{nullptr};
   ServerInviteSessionHandle mServerSession;
   std::unique_ptr<SipMessage> mInviteMessage;
   std::string mHarnessLocalTag;
   std::string mPeerContact;
   std::string mEstablishedCallId;
   bool mNotifiedEstablished{false};
   bool mPendingEstablishedNotify{false};
   bool mForwardActive{false};
   std::unique_ptr<DialogSetId> mOutboundDialogSet;
   std::map<std::string, ServerInviteSessionHandle> mInboundByOutboundCallId;
   std::unique_ptr<SipMessage> mOutboundInviteMessage;
   std::unique_ptr<SipMessage> mOutboundAnswerMessage;
};

void markReady(ListenerState* state, const std::string& startupError = {})
{
   {
      std::lock_guard<std::mutex> lock(state->mutex);
      state->startupError = startupError;
      state->ready = true;
   }
   state->readyCondition.notify_all();
}

void recordWorkerError(ListenerState* state, const std::string& message)
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
   std::cerr << "RESIP_RUNTIME_WORKER_ERROR message=" << message << std::endl;
}

void runListener(ListenerState* state)
{
   try
   {
      Log::initialize(Log::Cout, Log::None, Data("as_platform_resip_runtime"));
      const TransportConfig& config = state->transportConfig;

      std::unique_ptr<SipStack> stackPtr;
      if (config.enableTls)
      {
         SipStackOptions options;
         Security* security = new Security();
         if (!config.caPath.empty())
         {
            security->addCAFile(Data(config.caPath.c_str()));
         }
         options.mSecurity = security;
         stackPtr = std::make_unique<SipStack>(options);
      }
      else
      {
         stackPtr = std::make_unique<SipStack>();
      }

      SipStack& stack = *stackPtr;
      state->stack = &stack;

      const Data bindAddress(config.bindAddress.c_str());
      const Data advertisedAddress(config.advertisedAddress.c_str());

      int udpPort = 0;
      if (config.enableUdp)
      {
         Transport* udpTransport =
            stack.addTransport(UDP, 0, V4, StunDisabled, bindAddress);
         if (udpTransport == nullptr)
         {
            throw std::runtime_error("addTransport(UDP) returned null");
         }
         udpPort = udpTransport->port();
         if (udpPort <= 0)
         {
            throw std::runtime_error("failed to resolve bound UDP port");
         }
      }

      int tcpPort = 0;
      if (config.enableTcp)
      {
         Transport* tcpTransport = stack.addTransport(TCP, 0, V4, StunDisabled, bindAddress);
         if (tcpTransport == nullptr)
         {
            throw std::runtime_error("addTransport(TCP) returned null");
         }
         tcpPort = tcpTransport->port();
         if (tcpPort <= 0)
         {
            throw std::runtime_error("failed to resolve bound TCP port");
         }
      }

      int tlsPort = 0;
      if (config.enableTls)
      {
         SecurityTypes::TlsClientVerificationMode verificationMode = SecurityTypes::None;
         if (config.requireClientCertificate)
         {
            verificationMode = SecurityTypes::Mandatory;
         }
         else if (config.requestClientCertificate)
         {
            verificationMode = SecurityTypes::Optional;
         }
         Transport* tlsTransport = stack.addTransport(
            TLS,
            0,
            V4,
            StunDisabled,
            bindAddress,
            advertisedAddress,
            Data::Empty,
            SecurityTypes::SSLv23,
            0,
            Data(config.certificatePath.c_str()),
            Data(config.privateKeyPath.c_str()),
            verificationMode);
         if (tlsTransport == nullptr)
         {
            throw std::runtime_error("addTransport(TLS) returned null");
         }
         tlsPort = tlsTransport->port();
         if (tlsPort <= 0)
         {
            throw std::runtime_error("failed to resolve bound TLS port");
         }
         TlsBaseTransport* tlsBase = dynamic_cast<TlsBaseTransport*>(tlsTransport);
         if (tlsBase == nullptr)
         {
            throw std::runtime_error("TLS transport is not TlsBaseTransport");
         }
         SSL_CTX* sslContext = tlsBase->getCtx();
         if (sslContext == nullptr)
         {
            throw std::runtime_error("TLS transport returned null SSL_CTX");
         }
         SSL_CTX_set_ex_data(sslContext, listenerStateSslCtxExIndex(), state);
         SSL_CTX_set_verify(
            sslContext, SSL_CTX_get_verify_mode(sslContext), peerFingerprintVerifyCallback);
      }

      if (!config.enableUdp && !config.enableTcp && !config.enableTls)
      {
         throw std::runtime_error("at least one of UDP, TCP, or TLS transport must be enabled");
      }

      MinimalInviteSessionHandler handler(state);
      state->sessionHandler = &handler;
      DialogUsageManager dum(stack);
      handler.setDum(dum);

      auto profile = std::make_shared<MasterProfile>();
      profile->clearSupportedSchemes();
      profile->addSupportedScheme("sip");
      const bool useTlsContact = config.enableTls && tlsPort > 0 &&
                                 (config.tlsOnly || !config.enableUdp);
      const bool useTcpContact =
         !useTlsContact && config.enableTcp && tcpPort > 0 && !config.enableUdp;
      if (useTlsContact)
      {
         profile->addSupportedScheme("sips");
      }
      const int contactPort = useTlsContact ? tlsPort : (useTcpContact ? tcpPort : udpPort);
      const Data contactScheme = useTlsContact ? Data("sips") : Data("sip");
      Data contact =
         contactScheme + ":as-runtime@" + advertisedAddress + ":" + Data(contactPort);
      if (useTcpContact)
      {
         contact += ";transport=tcp";
      }
      profile->setOverrideHostAndPort(Uri(contact));
      profile->setDefaultFrom(NameAddr(contact));
      dum.setMasterProfile(profile);
      dum.setInviteSessionHandler(&handler);
      dum.setAppDialogSetFactory(std::make_unique<MinimalAppDialogSetFactory>());

      state->tlsPort = tlsPort;
      state->tcpPort = tcpPort;
      if (useTlsContact)
      {
         state->serverPort = tlsPort;
      }
      else if (udpPort > 0)
      {
         state->serverPort = udpPort;
      }
      else
      {
         state->serverPort = tcpPort;
      }
      markReady(state);
      if (udpPort > 0)
      {
         std::cout << "RESIP_RUNTIME_LISTENING address=" << config.bindAddress
                   << " advertised=" << config.advertisedAddress << " udp_port=" << udpPort
                   << std::endl;
      }
      if (tcpPort > 0)
      {
         std::cout << "RESIP_RUNTIME_LISTENING address=" << config.bindAddress
                   << " advertised=" << config.advertisedAddress << " tcp_port=" << tcpPort
                   << std::endl;
      }
      if (tlsPort > 0)
      {
         std::cout << "RESIP_RUNTIME_LISTENING address=" << config.bindAddress
                   << " advertised=" << config.advertisedAddress << " tls_port=" << tlsPort
                   << std::endl;
      }

      while (!state->stopRequested.load())
      {
         if (state->reloadCertificatesRequested.exchange(false))
         {
            stack.reloadCertificates();
            std::cout << "RESIP_RUNTIME_RELOAD_CERTIFICATES invoked" << std::endl;
         }
         stack.process(50);
         while (dum.process())
         {
         }
         if (state->sessionHandler != nullptr)
         {
            state->sessionHandler->consumePendingEstablishedNotify();
         }
      }
      state->stack = nullptr;
   }
   catch (const std::exception& error)
   {
      state->stack = nullptr;
      recordWorkerError(state, error.what());
   }
   catch (...)
   {
      state->stack = nullptr;
      recordWorkerError(state, "unknown C++ exception in resip runtime worker");
   }
}

void stopAndJoin(ListenerState* state)
{
   state->stopRequested.store(true);
   if (state->worker.joinable())
   {
      Py_BEGIN_ALLOW_THREADS
      state->worker.join();
      Py_END_ALLOW_THREADS
   }
}

ListenerState* getState(PyObject* capsule)
{
   return static_cast<ListenerState*>(PyCapsule_GetPointer(capsule, kCapsuleName));
}

void capsuleDestructor(PyObject* capsule)
{
   ListenerState* state = getState(capsule);
   if (state == nullptr)
   {
      PyErr_Clear();
      return;
   }
   stopAndJoin(state);
   Py_XDECREF(state->callback);
   Py_XDECREF(state->establishedCallback);
   Py_XDECREF(state->terminatedCallback);
   delete state;
}

PyObject* startListener(PyObject*, PyObject* args)
{
   PyObject* callback = nullptr;
   PyObject* configObject = nullptr;
   PyObject* establishedCallback = nullptr;
   PyObject* terminatedCallback = nullptr;
   if (!PyArg_ParseTuple(args, "O|OOO:start", &callback, &configObject, &establishedCallback,
                         &terminatedCallback))
   {
      return nullptr;
   }
   if (!PyCallable_Check(callback))
   {
      PyErr_SetString(PyExc_TypeError, "callback must be callable");
      return nullptr;
   }
   if (establishedCallback != nullptr && establishedCallback != Py_None &&
       !PyCallable_Check(establishedCallback))
   {
      PyErr_SetString(PyExc_TypeError, "on_dialog_established must be callable or None");
      return nullptr;
   }
   if (terminatedCallback != nullptr && terminatedCallback != Py_None &&
       !PyCallable_Check(terminatedCallback))
   {
      PyErr_SetString(PyExc_TypeError, "on_dialog_terminated must be callable or None");
      return nullptr;
   }

   auto* state = new ListenerState(callback);
   if (!parseTransportConfig(configObject, state->transportConfig))
   {
      delete state;
      return nullptr;
   }
   if (state->transportConfig.enableTls &&
       (state->transportConfig.certificatePath.empty() ||
        state->transportConfig.privateKeyPath.empty()))
   {
      delete state;
      PyErr_SetString(PyExc_ValueError, "enable_tls requires certificate_path and private_key_path");
      return nullptr;
   }
   Py_INCREF(callback);
   if (establishedCallback != nullptr && establishedCallback != Py_None)
   {
      Py_INCREF(establishedCallback);
      state->establishedCallback = establishedCallback;
   }
   if (terminatedCallback != nullptr && terminatedCallback != Py_None)
   {
      Py_INCREF(terminatedCallback);
      state->terminatedCallback = terminatedCallback;
   }
   try
   {
      state->worker = std::thread(runListener, state);
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
   int serverPort = 0;
   if (ready)
   {
      std::lock_guard<std::mutex> lock(state->mutex);
      startupError = state->startupError;
      serverPort = state->serverPort;
   }
   if (!ready || !startupError.empty() || serverPort <= 0)
   {
      stopAndJoin(state);
      Py_DECREF(callback);
      delete state;
      const std::string message =
         ready ? startupError : "resip runtime listener startup timed out";
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

PyObject* stopListener(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   if (!PyArg_ParseTuple(args, "O:stop", &capsule))
   {
      return nullptr;
   }
   ListenerState* state = getState(capsule);
   if (state == nullptr)
   {
      return nullptr;
   }

   stopAndJoin(state);
   Py_XDECREF(state->callback);
   state->callback = nullptr;
   Py_XDECREF(state->establishedCallback);
   state->establishedCallback = nullptr;
   Py_XDECREF(state->terminatedCallback);
   state->terminatedCallback = nullptr;

   std::string workerError;
   const int serverPort = state->serverPort;
   {
      std::lock_guard<std::mutex> lock(state->mutex);
      workerError = state->workerError;
   }

   PyObject* result = PyDict_New();
   if (result == nullptr)
   {
      return nullptr;
   }
   const bool ok = addDictItem(result, "server_port", PyLong_FromLong(serverPort)) &&
                   addDictItem(
                      result, "worker_error",
                      PyUnicode_FromStringAndSize(
                         workerError.data(), static_cast<Py_ssize_t>(workerError.size())));
   if (!ok)
   {
      Py_DECREF(result);
      return nullptr;
   }
   return result;
}

PyObject* reloadCertificates(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   if (!PyArg_ParseTuple(args, "O:reload_certificates", &capsule))
   {
      return nullptr;
   }
   ListenerState* state = getState(capsule);
   if (state == nullptr)
   {
      return nullptr;
   }
   state->reloadCertificatesRequested.store(true);
   Py_RETURN_NONE;
}

PyObject* getPort(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   if (!PyArg_ParseTuple(args, "O:get_port", &capsule))
   {
      return nullptr;
   }
   ListenerState* state = getState(capsule);
   if (state == nullptr)
   {
      return nullptr;
   }
   return PyLong_FromLong(state->serverPort);
}

PyObject* getTlsPort(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   if (!PyArg_ParseTuple(args, "O:get_tls_port", &capsule))
   {
      return nullptr;
   }
   ListenerState* state = getState(capsule);
   if (state == nullptr)
   {
      return nullptr;
   }
   return PyLong_FromLong(state->tlsPort);
}

PyObject* getTcpPort(PyObject*, PyObject* args)
{
   PyObject* capsule = nullptr;
   if (!PyArg_ParseTuple(args, "O:get_tcp_port", &capsule))
   {
      return nullptr;
   }
   ListenerState* state = getState(capsule);
   if (state == nullptr)
   {
      return nullptr;
   }
   return PyLong_FromLong(state->tcpPort);
}

PyMethodDef methods[] = {
   {"start", startListener, METH_VARARGS,
    "Start DUM listener on 127.0.0.1:0; callback(peer_dict, sip_summary) -> status."},
   {"stop", stopListener, METH_VARARGS, "Stop and join the listener worker."},
   {"get_port", getPort, METH_VARARGS, "Return the primary bound port for a listener capsule."},
   {"get_tls_port", getTlsPort, METH_VARARGS, "Return the bound TLS port (0 when disabled)."},
   {"get_tcp_port", getTcpPort, METH_VARARGS, "Return the bound TCP port (0 when disabled)."},
   {"reload_certificates", reloadCertificates, METH_VARARGS,
    "Request SipStack::reloadCertificates on the listener worker thread."},
   {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {
   PyModuleDef_HEAD_INIT,
   "_resip_runtime",
   "reSIProcate DUM ingress listener for as_platform (M2 P2c).",
   -1,
   methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__resip_runtime()
{
   return PyModule_Create(&module);
}
