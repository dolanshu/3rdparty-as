#include "resip/dum/DialogUsageManager.hxx"
#include "resip/dum/InviteSessionHandler.hxx"
#include "resip/dum/MasterProfile.hxx"
#include "resip/dum/ServerInviteSession.hxx"
#include "resip/stack/Helper.hxx"
#include "resip/stack/HeaderFieldValue.hxx"
#include "resip/stack/Message.hxx"
#include "resip/stack/MessageFilterRule.hxx"
#include "resip/stack/Mime.hxx"
#include "resip/stack/NameAddr.hxx"
#include "resip/stack/SdpContents.hxx"
#include "resip/stack/SipStack.hxx"
#include "resip/stack/Uri.hxx"
#include "rutil/Data.hxx"

#include <arpa/inet.h>
#include <cerrno>
#include <chrono>
#include <cctype>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/socket.h>
#include <thread>
#include <unistd.h>
#include <vector>

using namespace resip;

namespace
{
constexpr int kTimeoutSeconds = 6;

struct Ports
{
   unsigned short as;
   unsigned short peer;
   unsigned short upstream;
};

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

std::string trim(std::string value)
{
   while (!value.empty() && std::isspace(static_cast<unsigned char>(value.front())))
   {
      value.erase(value.begin());
   }
   while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back())))
   {
      value.pop_back();
   }
   return value;
}

std::string lower(std::string value)
{
   for (char& character : value)
   {
      character = static_cast<char>(std::tolower(static_cast<unsigned char>(character)));
   }
   return value;
}

std::vector<std::string> headerValues(const std::string& message, const std::string& wanted)
{
   std::vector<std::string> result;
   std::istringstream input(message);
   std::string line;
   while (std::getline(input, line))
   {
      if (!line.empty() && line.back() == '\r')
      {
         line.pop_back();
      }
      if (line.empty())
      {
         break;
      }
      const std::size_t colon = line.find(':');
      if (colon != std::string::npos && lower(trim(line.substr(0, colon))) == lower(wanted))
      {
         result.push_back(trim(line.substr(colon + 1)));
      }
   }
   return result;
}

std::string headerValue(const std::string& message, const std::string& wanted)
{
   const std::vector<std::string> values = headerValues(message, wanted);
   return values.empty() ? std::string() : values.front();
}

std::string addressUri(const std::string& value)
{
   const std::size_t open = value.find('<');
   const std::size_t close = value.find('>', open == std::string::npos ? 0 : open + 1);
   if (open != std::string::npos && close != std::string::npos)
   {
      return trim(value.substr(open + 1, close - open - 1));
   }
   const std::size_t parameter = value.find(';');
   return trim(value.substr(0, parameter));
}

std::string addressTag(const std::string& value)
{
   const std::string normalized = lower(value);
   const std::size_t start = normalized.find(";tag=");
   if (start == std::string::npos)
   {
      return std::string();
   }
   const std::size_t valueStart = start + 5;
   const std::size_t end = value.find(';', valueStart);
   return value.substr(valueStart, end == std::string::npos ? std::string::npos : end - valueStart);
}

int statusCode(const std::string& message)
{
   std::istringstream input(message.substr(0, message.find("\r\n")));
   std::string version;
   int code = 0;
   input >> version >> code;
   return code;
}

std::string messageText(const SipMessage& message)
{
   std::ostringstream output;
   output << message;
   return output.str();
}

void capture(std::ofstream& output, const std::string& label, const std::string& message)
{
   output << "===== " << label << " =====\n" << message;
   if (message.empty() || message.back() != '\n')
   {
      output << "\r\n";
   }
   output.flush();
}

sockaddr_in loopback(unsigned short port)
{
   sockaddr_in address{};
   address.sin_family = AF_INET;
   address.sin_port = htons(port);
   if (inet_pton(AF_INET, "127.0.0.1", &address.sin_addr) != 1)
   {
      throw std::runtime_error("inet_pton failed for loopback");
   }
   return address;
}

int bindUdp(unsigned short port)
{
   const int descriptor = socket(AF_INET, SOCK_DGRAM, 0);
   if (descriptor < 0)
   {
      throw std::runtime_error("socket: " + std::string(std::strerror(errno)));
   }

   const int reuse = 1;
   setsockopt(descriptor, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
   const sockaddr_in address = loopback(port);
   if (bind(descriptor, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) != 0)
   {
      const std::string error = std::strerror(errno);
      close(descriptor);
      throw std::runtime_error("bind UDP port " + std::to_string(port) + ": " + error);
   }

   const int flags = fcntl(descriptor, F_GETFL, 0);
   if (flags < 0 || fcntl(descriptor, F_SETFL, flags | O_NONBLOCK) != 0)
   {
      const std::string error = std::strerror(errno);
      close(descriptor);
      throw std::runtime_error("fcntl: " + error);
   }
   return descriptor;
}

bool receiveUdp(int descriptor, std::string& message, sockaddr_in* source = nullptr)
{
   char buffer[65536];
   sockaddr_in peer{};
   socklen_t peerLength = sizeof(peer);
   const ssize_t count = recvfrom(descriptor,
                                  buffer,
                                  sizeof(buffer),
                                  MSG_DONTWAIT,
                                  reinterpret_cast<sockaddr*>(&peer),
                                  &peerLength);
   if (count < 0)
   {
      if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)
      {
         return false;
      }
      throw std::runtime_error("recvfrom: " + std::string(std::strerror(errno)));
   }
   message.assign(buffer, static_cast<std::size_t>(count));
   if (source)
   {
      *source = peer;
   }
   return true;
}

void sendUdp(int descriptor, const sockaddr_in& destination, const std::string& message)
{
   const ssize_t count = sendto(descriptor,
                                message.data(),
                                message.size(),
                                0,
                                reinterpret_cast<const sockaddr*>(&destination),
                                sizeof(destination));
   if (count != static_cast<ssize_t>(message.size()))
   {
      throw std::runtime_error("sendto: " + std::string(std::strerror(errno)));
   }
}

std::string requiredHeader(const std::string& message, const std::string& name)
{
   const std::string value = headerValue(message, name);
   if (value.empty())
   {
      throw std::runtime_error("missing SIP header: " + name);
   }
   return value;
}

unsigned int cseqNumber(const std::string& value)
{
   std::istringstream input(value);
   unsigned long number = 0;
   std::string method;
   std::string trailing;
   if (!(input >> number >> method) || (input >> trailing) || number == 0 ||
       number > static_cast<unsigned long>(UINT_MAX))
   {
      throw std::runtime_error("invalid positive CSeq: " + value);
   }
   return static_cast<unsigned int>(number);
}

unsigned int parsePositive(const std::string& value, const std::string& field)
{
   char* end = nullptr;
   errno = 0;
   const unsigned long parsed = std::strtoul(value.c_str(), &end, 10);
   if (errno != 0 || end == value.c_str() || *end != '\0' || parsed == 0 ||
       parsed > static_cast<unsigned long>(UINT_MAX))
   {
      throw std::runtime_error("invalid positive integer in " + field);
   }
   return static_cast<unsigned int>(parsed);
}

unsigned int parseCount(const std::string& value, const std::string& field)
{
   char* end = nullptr;
   errno = 0;
   const unsigned long parsed = std::strtoul(value.c_str(), &end, 10);
   if (errno != 0 || end == value.c_str() || *end != '\0' || parsed > 64)
   {
      throw std::runtime_error("invalid route count in " + field);
   }
   return static_cast<unsigned int>(parsed);
}

void writeField(std::ofstream& output, const std::string& name, const std::string& value)
{
   if (name.empty() || value.find('\n') != std::string::npos || value.find('\r') != std::string::npos)
   {
      throw std::runtime_error("invalid source field: " + name);
   }
   output << name << '=' << value << '\n';
}

void writeLegFields(std::ofstream& output, const std::string& prefix, const DialogFields& leg)
{
   writeField(output, prefix + "_call_id", leg.callId);
   writeField(output, prefix + "_local_tag", leg.localTag);
   writeField(output, prefix + "_remote_tag", leg.remoteTag);
   writeField(output, prefix + "_local_uri", leg.localUri);
   writeField(output, prefix + "_remote_uri", leg.remoteUri);
   writeField(output, prefix + "_remote_target", leg.remoteTarget);
   writeField(output, prefix + "_local_cseq", std::to_string(leg.localCSeq));
   writeField(output, prefix + "_remote_cseq", std::to_string(leg.remoteCSeq));
   writeField(output, prefix + "_route_count", std::to_string(leg.routeSet.size()));
   for (std::size_t index = 0; index < leg.routeSet.size(); ++index)
   {
      writeField(output, prefix + "_route_" + std::to_string(index), leg.routeSet[index]);
   }
}

void savePhaseASource(const std::string& path, const Checkpoint& checkpoint)
{
   std::ofstream output(path.c_str(), std::ios::trunc);
   if (!output)
   {
      throw std::runtime_error("cannot write phase-A source fields: " + path);
   }
   writeField(output, "format", "d10-phase-a-source-v1");
   writeLegFields(output, "uas", checkpoint.uas);
   writeLegFields(output, "uac", checkpoint.uac);
   output.flush();
   if (!output)
   {
      throw std::runtime_error("failed to flush phase-A source fields: " + path);
   }
}

std::map<std::string, std::string> readFields(const std::string& path)
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
   return fields;
}

Checkpoint loadCheckpoint(const std::string& path)
{
   const std::map<std::string, std::string> fields = readFields(path);
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
      const unsigned int routeCount = parseCount(field("route_count"), prefix + "_route_count");
      for (unsigned int index = 0; index < routeCount; ++index)
      {
         const std::string suffix = "route_" + std::to_string(index);
         leg.routeSet.push_back(field(suffix));
      }
   };
   loadLeg("uas", checkpoint.uas);
   loadLeg("uac", checkpoint.uac);
   if (fields.size() != expected.size())
   {
      throw std::runtime_error("native checkpoint adapter has unexpected fields");
   }
   for (const auto& field : fields)
   {
      if (expected.find(field.first) == expected.end())
      {
         throw std::runtime_error("native checkpoint adapter has unexpected field: " + field.first);
      }
   }
   return checkpoint;
}

std::string makeSdp(const std::string& sessionId)
{
   return "v=0\r\n"
          "o=- " + sessionId + " 1 IN IP4 127.0.0.1\r\n"
          "s=recovery-hook-test\r\n"
          "c=IN IP4 127.0.0.1\r\n"
          "t=0 0\r\n"
          "m=audio 0 RTP/AVP 0\r\n";
}

class PhaseAHandler final : public InviteSessionHandler
{
public:
   explicit PhaseAHandler(Checkpoint& checkpoint) : mCheckpoint(checkpoint) {}

   bool accepted = false;
   bool ackObserved = false;
   bool uacConnected = false;
   bool uacFailed = false;
   std::string uacResponse;
   std::string uacFailure;

   void onNewSession(ClientInviteSessionHandle, InviteSession::OfferAnswerType, const SipMessage&) override {}

   void onNewSession(ServerInviteSessionHandle session,
                     InviteSession::OfferAnswerType,
                     const SipMessage&) override
   {
      const std::string answerText = makeSdp("2002");
      HeaderFieldValue answerValue(answerText.c_str(), answerText.size());
      SdpContents answer(answerValue, Mime(Data("application"), Data("sdp")));
      session->provideAnswer(answer);
      session->accept(200);
      accepted = true;
      std::cout << "PHASE_A_UAS_ACCEPTED=1\n";
   }

   void onFailure(ClientInviteSessionHandle, const SipMessage& message) override
   {
      uacFailed = true;
      uacFailure = messageText(message);
   }
   void onEarlyMedia(ClientInviteSessionHandle, const SipMessage&, const SdpContents&) override {}
   void onProvisional(ClientInviteSessionHandle, const SipMessage&) override {}
   void onConnected(ClientInviteSessionHandle, const SipMessage& message) override
   {
      uacResponse = messageText(message);
      try
      {
         const unsigned int inviteCSeq = cseqNumber(requiredHeader(uacResponse, "CSeq"));
         if (inviteCSeq == static_cast<unsigned int>(UINT_MAX))
         {
            throw std::runtime_error("phase-A DUM UAC INVITE CSeq cannot be incremented");
         }

         mCheckpoint.uac.callId = requiredHeader(uacResponse, "Call-ID");
         mCheckpoint.uac.localUri = addressUri(requiredHeader(uacResponse, "From"));
         mCheckpoint.uac.localTag = addressTag(requiredHeader(uacResponse, "From"));
         mCheckpoint.uac.remoteUri = addressUri(requiredHeader(uacResponse, "To"));
         mCheckpoint.uac.remoteTag = addressTag(requiredHeader(uacResponse, "To"));
         mCheckpoint.uac.remoteTarget = addressUri(requiredHeader(uacResponse, "Contact"));
         mCheckpoint.uac.routeSet = headerValues(uacResponse, "Record-Route");
         mCheckpoint.uac.localCSeq = inviteCSeq + 1;
         mCheckpoint.uac.remoteCSeq = inviteCSeq;
         if (statusCode(uacResponse) != 200 || mCheckpoint.uac.callId.empty() ||
             mCheckpoint.uac.localTag.empty() || mCheckpoint.uac.remoteTag.empty() ||
             mCheckpoint.uac.localUri.empty() || mCheckpoint.uac.remoteUri.empty() ||
             mCheckpoint.uac.remoteTarget.empty())
         {
            throw std::runtime_error("phase-A DUM UAC 200 response lacks complete dialog fields");
         }
         uacConnected = true;
      }
      catch (const std::exception& error)
      {
         uacFailed = true;
         uacFailure = error.what();
      }
   }
   void onConnected(InviteSessionHandle, const SipMessage&) override {}

   void onConnectedConfirmed(InviteSessionHandle, const SipMessage&) override
   {
      ackObserved = true;
      std::cout << "PHASE_A_ACK_CONFIRMED=1\n";
   }

   void onAckReceived(InviteSessionHandle, const SipMessage&) override
   {
      ackObserved = true;
      std::cout << "PHASE_A_ACK_RECEIVED=1\n";
   }

   void onTerminated(InviteSessionHandle, TerminatedReason, const SipMessage*) override {}
   void onForkDestroyed(ClientInviteSessionHandle) override {}
   void onRedirected(ClientInviteSessionHandle, const SipMessage&) override {}
   void onAnswer(InviteSessionHandle, const SipMessage&, const SdpContents&) override {}
   void onOffer(InviteSessionHandle, const SipMessage&, const SdpContents&) override {}
   void onOfferRequired(InviteSessionHandle, const SipMessage&) override {}
   void onOfferRejected(InviteSessionHandle, const SipMessage*) override {}
   void onInfo(InviteSessionHandle, const SipMessage&) override {}
   void onInfoSuccess(InviteSessionHandle, const SipMessage&) override {}
   void onInfoFailure(InviteSessionHandle, const SipMessage&) override {}
   void onMessage(InviteSessionHandle, const SipMessage&) override {}
   void onMessageSuccess(InviteSessionHandle, const SipMessage&) override {}
   void onMessageFailure(InviteSessionHandle, const SipMessage&) override {}
   void onRefer(InviteSessionHandle, ServerSubscriptionHandle, const SipMessage&) override {}
   void onReferNoSub(InviteSessionHandle, const SipMessage&) override {}
   void onReferRejected(InviteSessionHandle, const SipMessage&) override {}
   void onReferAccepted(InviteSessionHandle, ClientSubscriptionHandle, const SipMessage&) override {}

private:
   Checkpoint& mCheckpoint;
};

std::string makePeerResponse(const std::string& request, unsigned short peerPort);

void establishFakePeerDialog(int peer,
                             SipStack& stack,
                             DialogUsageManager& dum,
                             PhaseAHandler& handler,
                             const Ports& ports,
                             Checkpoint& checkpoint,
                             std::ofstream& wire)
{
   const std::string targetUri = "sip:peer@127.0.0.1:" + std::to_string(ports.peer);
   NameAddr target(Uri(Data(targetUri.c_str())));
   const std::string offerText = makeSdp("3003");
   HeaderFieldValue offerValue(offerText.c_str(), offerText.size());
   SdpContents offer(offerValue, Mime(Data("application"), Data("sdp")));
   const std::shared_ptr<SipMessage> invite = dum.makeInviteSession(target, &offer, nullptr);
   if (!invite)
   {
      throw std::runtime_error("phase-A DUM UAC did not create an INVITE");
   }
   dum.send(invite);
   std::cout << "PHASE_A_DUM_UAC_INVITE_CREATED=1\n"
             << "PHASE_A_DUM_UAC_INVITE_SENT=1\n";

   bool peerReplied = false;
   bool peerSawAck = false;
   std::string peerCallId;
   std::string peerInviteCSeq;
   std::string peerFromTag;
   std::string peerToTag;
   const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(kTimeoutSeconds);
   while (std::chrono::steady_clock::now() < deadline &&
          (!handler.uacConnected || !peerSawAck) && !handler.uacFailed)
   {
      stack.process(10);
      while (dum.process())
      {
      }

      std::string received;
      sockaddr_in source{};
      while (receiveUdp(peer, received, &source))
      {
         const std::string firstLine = received.substr(0, received.find("\r\n"));
         if (firstLine.find("INVITE ") == 0)
         {
            capture(wire, "PHASE_A_DUM_UAC_PEER_RX_INVITE", received);
            if (ntohs(source.sin_port) != ports.as ||
                firstLine.find("INVITE " + targetUri + " SIP/2.0") != 0)
            {
               throw std::runtime_error("phase-A DUM UAC INVITE did not use the AS transport and peer target");
            }

            const std::string currentCallId = requiredHeader(received, "Call-ID");
            const std::string currentCSeq = requiredHeader(received, "CSeq");
            const std::string currentFromTag = addressTag(requiredHeader(received, "From"));
            if (currentCallId.empty() || currentFromTag.empty() ||
                currentCSeq != std::to_string(cseqNumber(currentCSeq)) + " INVITE")
            {
               throw std::runtime_error("phase-A DUM UAC INVITE identifiers were incomplete");
            }
            if (!peerReplied)
            {
               peerCallId = currentCallId;
               peerInviteCSeq = currentCSeq;
               peerFromTag = currentFromTag;
            }
            else if (currentCallId != peerCallId || currentCSeq != peerInviteCSeq ||
                     currentFromTag != peerFromTag)
            {
               throw std::runtime_error("phase-A DUM UAC retransmitted a different INVITE transaction");
            }

            const std::string response = makePeerResponse(received, ports.peer);
            peerToTag = addressTag(requiredHeader(response, "To"));
            capture(wire, "PHASE_A_DUM_UAC_PEER_TX_200", response);
            sendUdp(peer, source, response);
            peerReplied = true;
         }
         else if (firstLine.find("ACK ") == 0)
         {
            capture(wire, "PHASE_A_DUM_UAC_PEER_RX_ACK", received);
            if (!peerReplied || ntohs(source.sin_port) != ports.as ||
                headerValue(received, "Call-ID") != peerCallId ||
                addressTag(requiredHeader(received, "From")) != peerFromTag ||
                addressTag(requiredHeader(received, "To")) != peerToTag ||
                headerValue(received, "CSeq") !=
                   std::to_string(cseqNumber(peerInviteCSeq)) + " ACK")
            {
               throw std::runtime_error("phase-A DUM UAC ACK did not match its INVITE transaction");
            }
            peerSawAck = true;
         }
         else
         {
            throw std::runtime_error("fake peer received an unexpected phase-A DUM UAC message");
         }
      }
   }

   if (handler.uacFailed)
   {
      throw std::runtime_error("phase-A DUM UAC failed: " + handler.uacFailure);
   }
   if (!peerReplied || !handler.uacConnected || !peerSawAck ||
       checkpoint.uac.callId != peerCallId || checkpoint.uac.localTag != peerFromTag ||
       checkpoint.uac.remoteTag != peerToTag)
   {
      throw std::runtime_error("phase-A DUM UAC did not complete its 200 response and automatic ACK");
   }
   capture(wire, "PHASE_A_DUM_UAC_ON_CONNECTED_200", handler.uacResponse);
   std::cout << "PHASE_A_DUM_UAC_CONNECTED=1\n"
             << "PHASE_A_DUM_UAC_ACK_CONFIRMED=1\n"
             << "PHASE_A_DUM_UAC_PEER_SOURCE_AS_TRANSPORT=1\n";
}

int runPhaseA(const std::string& sourcePath,
              const std::string& wirePath,
              const std::string& runToken,
              const Ports& ports)
{
   std::ofstream wire(wirePath.c_str(), std::ios::trunc);
   if (!wire)
   {
      throw std::runtime_error("cannot write phase-A wire capture");
   }
   Checkpoint checkpoint;
   const int upstream = bindUdp(ports.upstream);
   const int peer = bindUdp(ports.peer);

   SipStack stack;
   stack.addTransport(UDP, ports.as, V4, StunDisabled, Data("127.0.0.1"));
   DialogUsageManager dum(stack);
   dum.setMasterProfile(std::make_shared<MasterProfile>());
   PhaseAHandler handler(checkpoint);
   dum.setInviteSessionHandler(&handler);

   const std::string callerUri = "sip:caller@127.0.0.1";
   const std::string uasUri = "sip:uas@127.0.0.1";
   const std::string from = "<" + callerUri + ">;tag=caller-a";
   const std::string callId = "d10-recovery-" + runToken + "@127.0.0.1";
   const std::string offer = makeSdp("1001");
   std::ostringstream invite;
   invite << "INVITE sip:uas@127.0.0.1:" << ports.as << " SIP/2.0\r\n"
          << "Via: SIP/2.0/UDP 127.0.0.1:" << ports.upstream << ";branch=z9hG4bK-phase-a;rport\r\n"
          << "Max-Forwards: 70\r\n"
          << "From: " << from << "\r\n"
          << "To: <" << uasUri << ">\r\n"
          << "Call-ID: " << callId << "\r\n"
          << "CSeq: 1 INVITE\r\n"
          << "Contact: <sip:caller@127.0.0.1:" << ports.upstream << ">\r\n"
          << "Content-Type: application/sdp\r\n"
          << "Content-Length: " << offer.size() << "\r\n\r\n"
          << offer;
   const std::string inviteMessage = invite.str();
   sendUdp(upstream, loopback(ports.as), inviteMessage);
   capture(wire, "PHASE_A_UPSTREAM_INVITE", inviteMessage);

   std::string finalResponse;
   const auto inviteDeadline = std::chrono::steady_clock::now() + std::chrono::seconds(kTimeoutSeconds);
   while (std::chrono::steady_clock::now() < inviteDeadline && finalResponse.empty())
   {
      stack.process(10);
      while (dum.process())
      {
      }
      std::string response;
      while (receiveUdp(upstream, response))
      {
         capture(wire, "PHASE_A_UPSTREAM_RX", response);
         if (statusCode(response) >= 200)
         {
            finalResponse = response;
         }
      }
   }
   if (statusCode(finalResponse) != 200 || !handler.accepted)
   {
      throw std::runtime_error("phase A did not receive the DUM UAS 200 response");
   }

   checkpoint.uas.callId = requiredHeader(finalResponse, "Call-ID");
   checkpoint.uas.localUri = addressUri(requiredHeader(finalResponse, "To"));
   checkpoint.uas.localTag = addressTag(requiredHeader(finalResponse, "To"));
   checkpoint.uas.remoteUri = addressUri(requiredHeader(finalResponse, "From"));
   checkpoint.uas.remoteTag = addressTag(requiredHeader(finalResponse, "From"));
   checkpoint.uas.remoteTarget = addressUri(requiredHeader(inviteMessage, "Contact"));
   checkpoint.uas.routeSet = headerValues(finalResponse, "Record-Route");
   checkpoint.uas.localCSeq = 1;
   checkpoint.uas.remoteCSeq = cseqNumber(requiredHeader(inviteMessage, "CSeq")) + 1;
   const std::string uasContact = requiredHeader(finalResponse, "Contact");

   if (checkpoint.uas.localTag.empty() || checkpoint.uas.remoteTag.empty() ||
       checkpoint.uas.remoteTarget.empty())
   {
      throw std::runtime_error("phase A response or INVITE lacks a complete UAS dialog");
   }

   std::ostringstream ack;
   ack << "ACK " << addressUri(uasContact) << " SIP/2.0\r\n"
       << "Via: SIP/2.0/UDP 127.0.0.1:" << ports.upstream << ";branch=z9hG4bK-phase-a-ack;rport\r\n"
       << "Max-Forwards: 70\r\n"
       << "From: " << requiredHeader(finalResponse, "From") << "\r\n"
       << "To: " << requiredHeader(finalResponse, "To") << "\r\n"
       << "Call-ID: " << checkpoint.uas.callId << "\r\n"
       << "CSeq: 1 ACK\r\n"
       << "Contact: <sip:caller@127.0.0.1:" << ports.upstream << ">\r\n"
       << "Content-Length: 0\r\n\r\n";
   const std::string ackMessage = ack.str();
   sendUdp(upstream, loopback(ports.as), ackMessage);
   capture(wire, "PHASE_A_UPSTREAM_ACK", ackMessage);

   const auto ackDeadline = std::chrono::steady_clock::now() + std::chrono::seconds(kTimeoutSeconds);
   while (std::chrono::steady_clock::now() < ackDeadline && !handler.ackObserved)
   {
      stack.process(10);
      while (dum.process())
      {
      }
      std::string retransmission;
      while (receiveUdp(upstream, retransmission))
      {
         capture(wire, "PHASE_A_UPSTREAM_RX_AFTER_ACK", retransmission);
      }
   }
   if (!handler.ackObserved)
   {
      throw std::runtime_error("phase A ACK was not observed by the DUM UAS session");
   }

   establishFakePeerDialog(peer, stack, dum, handler, ports, checkpoint, wire);
   savePhaseASource(sourcePath, checkpoint);
   std::cout << "PHASE_A_SOURCE_FIELDS_WRITTEN=1\n"
             << "CALL_ID=" << checkpoint.uas.callId << "\n"
             << "UAC_CALL_ID=" << checkpoint.uac.callId << "\n"
             << "PHASE_A_UAS_AND_UAC_LEGS_ESTABLISHED=1\n";
   close(upstream);
   close(peer);
   return 0;
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
   RecoveryTu(SipStack& stack, const Checkpoint& checkpoint, const Ports& ports)
      : TransactionUser(recoveryRules()),
        mStack(stack),
        mCheckpoint(checkpoint),
        mPorts(ports),
        mUpstreamBye(),
        mDownstream200(false),
        mUpstream200Queued(false),
        mUnknownByeFilterFalse(false)
   {
      mFifo.setDescription("D10RecoveryTu");
   }

   const Data& name() const override
   {
      static const Data value("D10RecoveryTu");
      return value;
   }

   bool isForMe(const SipMessage& message) const override
   {
      if (!message.isRequest() || message.method() != BYE || !TransactionUser::isForMe(message))
      {
         return false;
      }
      const bool matches = message.header(h_CallId).value() == Data(mCheckpoint.uas.callId.c_str()) &&
                           message.header(h_From).param(p_tag) == Data(mCheckpoint.uas.remoteTag.c_str()) &&
                           message.header(h_To).param(p_tag) == Data(mCheckpoint.uas.localTag.c_str());
      if (!matches)
      {
         mUnknownByeFilterFalse = true;
         std::cout << "RECOVERY_TU_NONCHECKPOINT_BYE_FILTER_FALSE=1\n";
      }
      return matches;
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
   bool unknownByeFilterFalse() const { return mUnknownByeFilterFalse; }

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
      if (request.header(h_CallId).value() != Data(mCheckpoint.uas.callId.c_str()) ||
          request.header(h_From).param(p_tag) != Data(mCheckpoint.uas.remoteTag.c_str()) ||
          request.header(h_To).param(p_tag) != Data(mCheckpoint.uas.localTag.c_str()))
      {
         throw std::runtime_error("recovery TU received a BYE that does not match the checkpointed dialog");
      }
      if (!mUpstreamBye)
      {
         mUpstreamBye.reset(static_cast<SipMessage*>(request.clone()));
         NameAddr target(Uri(Data(mCheckpoint.uac.remoteTarget.c_str())));
         target.param(p_tag) = Data(mCheckpoint.uac.remoteTag.c_str());
         NameAddr from(Uri(Data(mCheckpoint.uac.localUri.c_str())));
         from.param(p_tag) = Data(mCheckpoint.uac.localTag.c_str());
         const std::string contactUri = "sip:as@127.0.0.1:" + std::to_string(mPorts.as);
         NameAddr contact(Uri(Data(contactUri.c_str())));
         std::unique_ptr<SipMessage> forwarded(Helper::makeRequest(target, from, contact, BYE));
         forwarded->header(h_CallId).value() = Data(mCheckpoint.uac.callId.c_str());
         forwarded->header(h_CSeq).method() = BYE;
         forwarded->header(h_CSeq).sequence() = mCheckpoint.uac.localCSeq;
         forwarded->header(h_From).param(p_tag) = Data(mCheckpoint.uac.localTag.c_str());
         forwarded->header(h_To).param(p_tag) = Data(mCheckpoint.uac.remoteTag.c_str());
         mStack.send(std::move(forwarded), this);
         std::cout << "RECOVERY_TU_MATCHED_BEFORE_DUM=1\n"
                   << "RECOVERY_TU_PEER_CALL_ID=" << mCheckpoint.uac.callId << "\n";
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
   const Ports& mPorts;
   std::unique_ptr<SipMessage> mUpstreamBye;
   bool mDownstream200;
   bool mUpstream200Queued;
   mutable bool mUnknownByeFilterFalse;
};

std::string makePeerResponse(const std::string& request, unsigned short peerPort)
{
   const bool isInvite = request.find("INVITE ") == 0;
   std::string to = requiredHeader(request, "To");
   if (isInvite && addressTag(to).empty())
   {
      to += ";tag=peer-b";
   }

   std::ostringstream response;
   response << "SIP/2.0 200 OK\r\n";
   for (const std::string& via : headerValues(request, "Via"))
   {
      response << "Via: " << via << "\r\n";
   }
   response << "From: " << requiredHeader(request, "From") << "\r\n"
            << "To: " << to << "\r\n"
            << "Call-ID: " << requiredHeader(request, "Call-ID") << "\r\n"
            << "CSeq: " << requiredHeader(request, "CSeq") << "\r\n";
   if (isInvite)
   {
      const std::string answer = makeSdp("4004");
      const std::string contact = "<sip:peer@127.0.0.1:" + std::to_string(peerPort) + ">";
      response << "Contact: " << contact << "\r\n"
               << "Content-Type: application/sdp\r\n"
               << "Content-Length: " << answer.size() << "\r\n\r\n"
               << answer;
   }
   else
   {
      response << "Content-Length: 0\r\n\r\n";
   }
   return response.str();
}

std::string makeBye(const Checkpoint& checkpoint, const Ports& ports)
{
   std::ostringstream bye;
   bye << "BYE sip:uas@127.0.0.1:" << ports.as << " SIP/2.0\r\n"
       << "Via: SIP/2.0/UDP 127.0.0.1:" << ports.upstream << ";branch=z9hG4bK-phase-b-bye;rport\r\n"
       << "Max-Forwards: 70\r\n"
       << "From: <" << checkpoint.uas.remoteUri << ">;tag=" << checkpoint.uas.remoteTag << "\r\n"
       << "To: <" << checkpoint.uas.localUri << ">;tag=" << checkpoint.uas.localTag << "\r\n"
       << "Call-ID: " << checkpoint.uas.callId << "\r\n"
       << "CSeq: " << checkpoint.uas.remoteCSeq << " BYE\r\n"
       << "Contact: <" << checkpoint.uas.remoteTarget << ">\r\n"
       << "Content-Length: 0\r\n\r\n";
   return bye.str();
}

std::string makeUnknownBye(const Ports& ports, const std::string& runToken)
{
   std::ostringstream bye;
   bye << "BYE sip:uas@127.0.0.1:" << ports.as << " SIP/2.0\r\n"
       << "Via: SIP/2.0/UDP 127.0.0.1:" << ports.upstream << ";branch=z9hG4bK-phase-b-unknown;rport\r\n"
       << "Max-Forwards: 70\r\n"
       << "From: <sip:caller@127.0.0.1>;tag=unknown-caller\r\n"
       << "To: <sip:uas@127.0.0.1>;tag=unknown-uas\r\n"
       << "Call-ID: d10-unknown-" << runToken << "@127.0.0.1\r\n"
       << "CSeq: 1 BYE\r\n"
       << "Contact: <sip:caller@127.0.0.1:" << ports.upstream << ">\r\n"
       << "Content-Length: 0\r\n\r\n";
   return bye.str();
}

bool serviceFakePeer(int peer,
                     const Checkpoint& checkpoint,
                     const Ports& ports,
                     std::ofstream& wire,
                     bool& sawBye,
                     bool& sent200)
{
   std::string request;
   sockaddr_in source{};
   if (!receiveUdp(peer, request, &source))
   {
      return false;
   }
   capture(wire, "FAKE_PEER_RX", request);
   const std::string firstLine = request.substr(0, request.find("\r\n"));
   const std::string peerTo = headerValue(request, "To");
   if (firstLine.find("BYE ") != 0 ||
       firstLine.find(checkpoint.uac.remoteTarget) == std::string::npos ||
       headerValue(request, "Call-ID") != checkpoint.uac.callId ||
       addressTag(headerValue(request, "From")) != checkpoint.uac.localTag ||
       peerTo.find("<sip:") != 0 ||
       addressTag(peerTo) != checkpoint.uac.remoteTag ||
       headerValue(request, "CSeq") != std::to_string(checkpoint.uac.localCSeq) + " BYE" ||
       headerValue(request, "Via").find("127.0.0.1:" + std::to_string(ports.as)) == std::string::npos ||
       headerValue(request, "Via").find(std::to_string(ports.upstream)) != std::string::npos)
   {
      throw std::runtime_error("fake peer received a BYE that does not match the saved dialog, CSeq, or AS Via");
   }
   sawBye = true;
   std::cout << "FAKE_PEER_SAW_MATCHING_BYE=1\n";

   const std::string response = makePeerResponse(request, ports.peer);
   capture(wire, "FAKE_PEER_TX_200", response);
   sendUdp(peer, source, response);
   sent200 = true;
   std::cout << "FAKE_PEER_SENT_REAL_UDP_200=1\n";
   return true;
}

int runPhaseB(const std::string& checkpointPath,
              const std::string& wirePath,
              const std::string& midflightReadyPath,
              const std::string& midflightReleasePath,
              const std::string& runToken,
              const Ports& ports)
{
   const Checkpoint checkpoint = loadCheckpoint(checkpointPath);
   std::ofstream wire(wirePath.c_str(), std::ios::trunc);
   if (!wire)
   {
      throw std::runtime_error("cannot write phase-B wire capture");
   }
   const int peer = bindUdp(ports.peer);
   const int upstream = bindUdp(ports.upstream);

   SipStack stack;
   stack.addTransport(UDP, ports.as, V4, StunDisabled, Data("127.0.0.1"));
   DialogUsageManager dum(stack);
   dum.setMasterProfile(std::make_shared<MasterProfile>());
   RecoveryTu recovery(stack, checkpoint, ports);
   stack.registerTransactionUser(recovery, true);
   std::cout << "PHASE_B_FRESH_DUM=1\n"
             << "RECOVERY_TU_REGISTERED_FRONT=1\n"
             << "CHECKPOINT_LOADED_FROM_TYPED_ADAPTER=1\n";

   const std::string bye = makeBye(checkpoint, ports);
   sendUdp(upstream, loopback(ports.as), bye);
   capture(wire, "PHASE_B_UPSTREAM_TX_BYE", bye);

   bool peerSawBye = false;
   bool peerSent200 = false;
   bool upstreamSaw200 = false;
   bool midflightReadyWritten = false;
   const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(kTimeoutSeconds);
   while (std::chrono::steady_clock::now() < deadline && !upstreamSaw200)
   {
      stack.process(10);
      while (dum.process())
      {
      }
      recovery.drain();
      serviceFakePeer(peer, checkpoint, ports, wire, peerSawBye, peerSent200);

      if (recovery.downstream200() && !midflightReadyWritten)
      {
         std::ofstream ready(midflightReadyPath.c_str(), std::ios::trunc);
         if (!ready)
         {
            throw std::runtime_error("cannot write phase-B midflight marker");
         }
         ready << "downstream-200-received\n";
         ready.flush();
         if (!ready)
         {
            throw std::runtime_error("failed to flush phase-B midflight marker");
         }
         midflightReadyWritten = true;
         std::cout << "PHASE_B_MIDFLIGHT_READY=1\n";
      }
      if (recovery.downstream200() && !recovery.upstream200Queued() &&
          access(midflightReleasePath.c_str(), F_OK) == 0)
      {
         recovery.sendUpstream200();
      }

      std::string response;
      while (receiveUdp(upstream, response))
      {
         capture(wire, "PHASE_B_UPSTREAM_RX", response);
         const int code = statusCode(response);
         if (code == 481)
         {
            throw std::runtime_error("upstream received DUM's default 481 for the matching BYE");
         }
         if (code >= 200)
         {
            if (code != 200)
            {
               throw std::runtime_error("upstream received unexpected final response " + std::to_string(code));
            }
            upstreamSaw200 = true;
         }
      }
   }

   if (!peerSawBye || !peerSent200 || !recovery.downstream200() ||
       !recovery.upstream200Queued() || !upstreamSaw200)
   {
      throw std::runtime_error("phase B did not complete downstream-200-to-upstream-200 recovery");
   }
   std::cout << "PHASE_B_RECOVERY_PASS=1\n"
             << "UPSTREAM_FINAL_STATUS=200\n"
             << "PEER_SAW_BYE=1\n"
             << "PEER_200_RECEIVED_BY_TU=1\n";

   const std::string unknownBye = makeUnknownBye(ports, runToken);
   const std::string unknownCallId = requiredHeader(unknownBye, "Call-ID");
   sendUdp(upstream, loopback(ports.as), unknownBye);
   capture(wire, "PHASE_B_UNKNOWN_UPSTREAM_TX_BYE", unknownBye);

   bool unknownSaw481 = false;
   const auto unknownDeadline = std::chrono::steady_clock::now() + std::chrono::seconds(kTimeoutSeconds);
   while (std::chrono::steady_clock::now() < unknownDeadline && !unknownSaw481)
   {
      stack.process(10);
      while (dum.process())
      {
      }
      recovery.drain();

      std::string unexpectedDownstream;
      while (receiveUdp(peer, unexpectedDownstream))
      {
         capture(wire, "UNEXPECTED_PEER_RX_AFTER_UNKNOWN_BYE", unexpectedDownstream);
         throw std::runtime_error("unknown BYE was forwarded to the downstream peer");
      }

      std::string response;
      while (receiveUdp(upstream, response))
      {
         capture(wire, "PHASE_B_UNKNOWN_UPSTREAM_RX", response);
         if (statusCode(response) == 481)
         {
            if (headerValue(response, "Call-ID") != unknownCallId ||
                headerValue(response, "CSeq") != "1 BYE")
            {
               throw std::runtime_error("DUM 481 did not correspond to the unknown BYE");
            }
            unknownSaw481 = true;
         }
         else if (statusCode(response) >= 200)
         {
            throw std::runtime_error("unknown BYE received final status " + std::to_string(statusCode(response)));
         }
      }
   }

   if (!unknownSaw481 || !recovery.unknownByeFilterFalse())
   {
      throw std::runtime_error("unknown BYE did not fall through the recovery filter to DUM's 481");
   }

   const auto noForwardDeadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(250);
   while (std::chrono::steady_clock::now() < noForwardDeadline)
   {
      stack.process(10);
      while (dum.process())
      {
      }
      recovery.drain();
      std::string unexpectedDownstream;
      if (receiveUdp(peer, unexpectedDownstream))
      {
         capture(wire, "UNEXPECTED_PEER_RX_DURING_UNKNOWN_GUARD", unexpectedDownstream);
         throw std::runtime_error("unknown BYE produced downstream traffic after DUM 481");
      }
   }

   std::cout << "RECOVERY_TU_UNKNOWN_BYE_FILTER_FALSE=1\n"
             << "FRESH_DUM_UNKNOWN_BYE_481=1\n"
             << "UNKNOWN_BYE_NOT_FORWARDED=1\n"
             << "UNKNOWN_BYE_WORKER_ERROR=0\n";
   close(upstream);
   close(peer);
   return 0;
}

unsigned short parsePort(const char* value, const std::string& name)
{
   char* end = nullptr;
   errno = 0;
   const long port = std::strtol(value, &end, 10);
   if (errno != 0 || end == value || *end != '\0' || port < 1 || port > 65535)
   {
      throw std::runtime_error("invalid loopback port for " + name);
   }
   return static_cast<unsigned short>(port);
}

Ports parsePorts(char** argv, int offset)
{
   Ports ports{parsePort(argv[offset], "AS"),
               parsePort(argv[offset + 1], "fake peer"),
               parsePort(argv[offset + 2], "upstream")};
   const std::set<unsigned short> distinct{ports.as, ports.peer, ports.upstream};
   if (distinct.size() != 3)
   {
      throw std::runtime_error("SIP ports must be distinct");
   }
   return ports;
}
}

int main(int argc, char** argv)
{
   try
   {
      if (argc < 2)
      {
         std::cerr << "usage: " << argv[0] << " phase-a|phase-b ...\n";
         return 2;
      }
      const std::string phase(argv[1]);
      if (phase == "phase-a")
      {
         if (argc != 8)
         {
            std::cerr << "usage: " << argv[0]
                      << " phase-a SOURCE_FIELDS WIRE_LOG RUN_TOKEN AS_PORT PEER_PORT UPSTREAM_PORT\n";
            return 2;
         }
         return runPhaseA(argv[2], argv[3], argv[4], parsePorts(argv, 5));
      }
      if (phase == "phase-b")
      {
         if (argc != 10)
         {
            std::cerr << "usage: " << argv[0]
                      << " phase-b NATIVE_ADAPTER WIRE_LOG MIDFLIGHT_READY MIDFLIGHT_RELEASE RUN_TOKEN"
                         " AS_PORT PEER_PORT UPSTREAM_PORT\n";
            return 2;
         }
         return runPhaseB(argv[2], argv[3], argv[4], argv[5], argv[6], parsePorts(argv, 7));
      }
      throw std::runtime_error("unknown phase: " + phase);
   }
   catch (const std::exception& error)
   {
      std::cerr << "ERROR: " << error.what() << '\n';
      return 1;
   }
}