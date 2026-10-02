#include "resip/dum/DialogSetId.hxx"
#include "resip/dum/DialogUsageManager.hxx"
#include "resip/dum/InviteSessionHandler.hxx"
#include "resip/dum/MasterProfile.hxx"
#include "resip/stack/HeaderFieldValue.hxx"
#include "resip/stack/Mime.hxx"
#include "resip/stack/SdpContents.hxx"
#include "resip/stack/SipMessage.hxx"
#include "resip/stack/SipStack.hxx"
#include "resip/stack/Uri.hxx"
#include "rutil/Data.hxx"
#include "rutil/TransportType.hxx"

#include <chrono>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <unistd.h>

namespace
{

using namespace std::chrono_literals;

constexpr const char* kLoopback = "127.0.0.1";
constexpr auto kPhaseTimeout = 8s;
constexpr auto kAckDrainTime = 250ms;

const std::string kOfferSdp =
    "v=0\r\n"
    "o=- 4001 2 IN IP4 127.0.0.1\r\n"
    "s=DUM process restart probe\r\n"
    "c=IN IP4 127.0.0.1\r\n"
    "t=0 0\r\n"
    "m=audio 49170 RTP/AVP 0\r\n"
    "a=rtpmap:0 PCMU/8000\r\n";

struct Config
{
   std::string phase;
   int peerPort{0};
   int clientPort{0};
   std::string callId;
   std::string localTag;
   std::string remoteTag;
   std::string remoteTarget;
   std::vector<std::string> routeSet;
   unsigned int lastCSeq{0};
   std::string businessContextKey;
};

int parse_int(const std::string& value, const std::string& name)
{
   std::size_t parsed = 0;
   const int result = std::stoi(value, &parsed);
   if (parsed != value.size())
   {
      throw std::runtime_error("invalid integer for " + name);
   }
   return result;
}

Config parse_args(int argc, char** argv)
{
   if (argc < 2)
   {
      throw std::runtime_error("expected phase-a or phase-b");
   }

   Config config;
   config.phase = argv[1];
   for (int index = 2; index < argc; ++index)
   {
      const std::string name = argv[index];
      if (index + 1 >= argc)
      {
         throw std::runtime_error("missing value for " + name);
      }
      const std::string value = argv[++index];
      if (name == "--peer-port")
      {
         config.peerPort = parse_int(value, name);
      }
      else if (name == "--client-port")
      {
         config.clientPort = parse_int(value, name);
      }
      else if (name == "--call-id")
      {
         config.callId = value;
      }
      else if (name == "--local-tag")
      {
         config.localTag = value;
      }
      else if (name == "--remote-tag")
      {
         config.remoteTag = value;
      }
      else if (name == "--remote-target")
      {
         config.remoteTarget = value;
      }
      else if (name == "--route")
      {
         config.routeSet.push_back(value);
      }
      else if (name == "--last-cseq")
      {
         config.lastCSeq = static_cast<unsigned int>(parse_int(value, name));
      }
      else if (name == "--business-context-key")
      {
         config.businessContextKey = value;
      }
      else
      {
         throw std::runtime_error("unknown argument " + name);
      }
   }

   if (config.phase != "phase-a" && config.phase != "phase-b")
   {
      throw std::runtime_error("phase must be phase-a or phase-b");
   }
   if (config.peerPort <= 0 || config.clientPort <= 0)
   {
      throw std::runtime_error("peer and client ports are required");
   }
   if (config.phase == "phase-b" &&
       (config.callId.empty() || config.localTag.empty() || config.remoteTag.empty() ||
        config.remoteTarget.empty() || config.routeSet.empty() || config.lastCSeq == 0 ||
        config.businessContextKey.empty()))
   {
      throw std::runtime_error("phase-b requires complete state loaded from JSON");
   }
   return config;
}

class ProcessInviteHandler final : public resip::InviteSessionHandler
{
public:
   explicit ProcessInviteHandler(std::thread::id loopThread)
       : mLoopThread(loopThread)
   {
   }

   void onNewSession(resip::ClientInviteSessionHandle,
                     resip::InviteSession::OfferAnswerType,
                     const resip::SipMessage&) override
   {
   }

   void onNewSession(resip::ServerInviteSessionHandle,
                     resip::InviteSession::OfferAnswerType,
                     const resip::SipMessage&) override
   {
   }

   void onFailure(resip::ClientInviteSessionHandle,
                  const resip::SipMessage& message) override
   {
      mFailure = "status=" +
                 std::to_string(message.header(resip::h_StatusLine).statusCode());
   }

   void onEarlyMedia(resip::ClientInviteSessionHandle,
                     const resip::SipMessage&,
                     const resip::SdpContents&) override
   {
   }

   void onProvisional(resip::ClientInviteSessionHandle,
                      const resip::SipMessage&) override
   {
   }

   void onConnected(resip::ClientInviteSessionHandle,
                    const resip::SipMessage& message) override
   {
      ++mConnectedCount;
      mConnectedStatus = message.header(resip::h_StatusLine).statusCode();
      mConnectedThreadMatches = std::this_thread::get_id() == mLoopThread;
   }

   void onConnected(resip::InviteSessionHandle,
                    const resip::SipMessage&) override
   {
   }

   void onTerminated(resip::InviteSessionHandle,
                     resip::InviteSessionHandler::TerminatedReason,
                     const resip::SipMessage*) override
   {
   }

   void onForkDestroyed(resip::ClientInviteSessionHandle) override
   {
   }

   void onRedirected(resip::ClientInviteSessionHandle,
                     const resip::SipMessage&) override
   {
   }

   void onAnswer(resip::InviteSessionHandle,
                 const resip::SipMessage&,
                 const resip::SdpContents&) override
   {
   }

   void onOffer(resip::InviteSessionHandle,
                const resip::SipMessage&,
                const resip::SdpContents&) override
   {
   }

   void onOfferRequired(resip::InviteSessionHandle,
                        const resip::SipMessage&) override
   {
   }

   void onOfferRejected(resip::InviteSessionHandle,
                        const resip::SipMessage*) override
   {
   }

   void onInfo(resip::InviteSessionHandle, const resip::SipMessage&) override
   {
   }

   void onInfoSuccess(resip::InviteSessionHandle, const resip::SipMessage&) override
   {
   }

   void onInfoFailure(resip::InviteSessionHandle, const resip::SipMessage&) override
   {
   }

   void onMessage(resip::InviteSessionHandle, const resip::SipMessage&) override
   {
   }

   void onMessageSuccess(resip::InviteSessionHandle, const resip::SipMessage&) override
   {
   }

   void onMessageFailure(resip::InviteSessionHandle, const resip::SipMessage&) override
   {
   }

   void onRefer(resip::InviteSessionHandle,
                resip::ServerSubscriptionHandle,
                const resip::SipMessage&) override
   {
   }

   void onReferNoSub(resip::InviteSessionHandle, const resip::SipMessage&) override
   {
   }

   void onReferRejected(resip::InviteSessionHandle,
                        const resip::SipMessage&) override
   {
   }

   void onReferAccepted(resip::InviteSessionHandle,
                        resip::ClientSubscriptionHandle,
                        const resip::SipMessage&) override
   {
   }

   int connected_count() const
   {
      return mConnectedCount;
   }

   int connected_status() const
   {
      return mConnectedStatus;
   }

   bool connected_thread_matches() const
   {
      return mConnectedThreadMatches;
   }

   const std::string& failure() const
   {
      return mFailure;
   }

private:
   std::thread::id mLoopThread;
   int mConnectedCount{0};
   int mConnectedStatus{0};
   bool mConnectedThreadMatches{false};
   std::string mFailure;
};

void process_stack(resip::SipStack& stack, resip::DialogUsageManager& dum)
{
   stack.process(10);
   while (dum.process())
   {
   }
}

int run_phase(const Config& config)
{
   const auto loopThread = std::this_thread::get_id();
   resip::SipStack stack;
   auto profile = std::make_shared<resip::MasterProfile>();
   profile->setDefaultFrom(resip::NameAddr(
       resip::Uri(resip::Data("sip:alice@127.0.0.1"))));
   ProcessInviteHandler handler(loopThread);
   resip::DialogUsageManager dum(stack);
   stack.addTransport(resip::UDP, config.clientPort, resip::V4,
                      resip::StunDisabled, resip::Data(kLoopback));
   dum.setMasterProfile(profile);
   dum.setInviteSessionHandler(&handler);

   const std::string targetUri = config.phase == "phase-a"
                                     ? "sip:uas@127.0.0.1:" +
                                           std::to_string(config.peerPort) +
                                           ";transport=udp"
                                     : config.remoteTarget;
   const resip::NameAddr target(
       resip::Uri(resip::Data(targetUri.c_str())));
   const resip::HeaderFieldValue offerField(kOfferSdp.data(), kOfferSdp.size());
   const resip::Mime offerType("application", "sdp");
   const resip::SdpContents offer(offerField, offerType);

   std::shared_ptr<resip::SipMessage> invite;
   unsigned int expectedCSeq = 1;
   if (config.phase == "phase-a")
   {
      invite = dum.makeInviteSession(target, profile, &offer);
      expectedCSeq = invite->header(resip::h_CSeq).sequence();
   }
   else
   {
      const resip::DialogSetId dialogSetId(
          resip::Data(config.callId.c_str()), resip::Data(config.localTag.c_str()));
      invite = dum.makeInviteSession(target, dialogSetId, profile, &offer,
                                     resip::DialogUsageManager::None);
      invite->header(resip::h_To).param(resip::p_tag) =
          resip::Data(config.remoteTag.c_str());
      for (const auto& route : config.routeSet)
      {
         invite->header(resip::h_Routes).push_back(resip::NameAddr(
             resip::Uri(resip::Data(route.c_str()))));
      }
      expectedCSeq = config.lastCSeq + 1;
      invite->header(resip::h_CSeq).sequence() = expectedCSeq;

      if (invite->header(resip::h_CallID).value() !=
              resip::Data(config.callId.c_str()) ||
          invite->header(resip::h_From).param(resip::p_tag) !=
              resip::Data(config.localTag.c_str()) ||
          invite->header(resip::h_To).param(resip::p_tag) !=
              resip::Data(config.remoteTag.c_str()) ||
          invite->header(resip::h_CSeq).sequence() != expectedCSeq ||
          invite->header(resip::h_Routes).size() != config.routeSet.size())
      {
         throw std::runtime_error("restored request fields failed in-memory validation");
      }
   }

   dum.send(invite);
   const auto deadline = std::chrono::steady_clock::now() + kPhaseTimeout;
   while (std::chrono::steady_clock::now() < deadline &&
          handler.connected_count() == 0 && handler.failure().empty())
   {
      process_stack(stack, dum);
   }
   if (!handler.failure().empty())
   {
      throw std::runtime_error("DUM onFailure: " + handler.failure());
   }
   if (handler.connected_count() != 1)
   {
      throw std::runtime_error("timed out before exactly one DUM onConnected callback");
   }
   if (!handler.connected_thread_matches())
   {
      throw std::runtime_error("onConnected ran outside the child DUM loop thread");
   }

   const auto drainDeadline = std::chrono::steady_clock::now() + kAckDrainTime;
   while (std::chrono::steady_clock::now() < drainDeadline)
   {
      process_stack(stack, dum);
   }

   std::cout << "phase=" << config.phase << "\n";
   std::cout << "child_pid=" << ::getpid() << "\n";
   std::cout << "dum_loop_thread=" << loopThread << "\n";
   std::cout << "on_connected_thread_matches_loop=true\n";
   std::cout << "on_connected_count=" << handler.connected_count() << "\n";
   std::cout << "on_connected_status=" << handler.connected_status() << "\n";
   std::cout << "sent_cseq=" << expectedCSeq << "\n";
   if (config.phase == "phase-b")
   {
      std::cout << "business_context_key=" << config.businessContextKey << "\n";
      std::cout << "dialog_set_id_call_id=" << config.callId << "\n";
      std::cout << "dialog_set_id_local_tag=" << config.localTag << "\n";
   }
   return 0;
}

} // namespace

int main(int argc, char** argv)
{
   try
   {
      const auto config = parse_args(argc, argv);
      return run_phase(config);
   }
   catch (const std::exception& error)
   {
      std::cerr << "child.error=" << error.what() << "\n";
      return 2;
   }
}
