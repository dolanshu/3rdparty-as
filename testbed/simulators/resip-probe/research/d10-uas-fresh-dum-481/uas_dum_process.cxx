#include "resip/dum/DialogUsageManager.hxx"
#include "resip/dum/InviteSessionHandler.hxx"
#include "resip/dum/MasterProfile.hxx"
#include "resip/dum/ServerInviteSession.hxx"
#include "resip/stack/HeaderFieldValue.hxx"
#include "resip/stack/Mime.hxx"
#include "resip/stack/SdpContents.hxx"
#include "resip/stack/SipMessage.hxx"
#include "resip/stack/SipStack.hxx"
#include "resip/stack/Uri.hxx"
#include "rutil/Data.hxx"
#include "rutil/TransportType.hxx"

#include <chrono>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <unistd.h>

namespace
{

volatile std::sig_atomic_t stopRequested = 0;

void request_stop(int)
{
   stopRequested = 1;
}

struct Options
{
   std::string phase;
   int port{0};
   int runtimeMs{15000};
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

Options parse_args(int argc, char** argv)
{
   if (argc < 2)
   {
      throw std::runtime_error("expected phase-a or phase-b");
   }

   Options options;
   options.phase = argv[1];
   for (int index = 2; index < argc; ++index)
   {
      const std::string name = argv[index];
      if (index + 1 >= argc)
      {
         throw std::runtime_error("missing value for " + name);
      }
      const std::string value = argv[++index];
      if (name == "--port")
      {
         options.port = parse_int(value, name);
      }
      else if (name == "--runtime-ms")
      {
         options.runtimeMs = parse_int(value, name);
      }
      else
      {
         throw std::runtime_error("unknown argument " + name);
      }
   }

   if (options.phase != "phase-a" && options.phase != "phase-b")
   {
      throw std::runtime_error("phase must be phase-a or phase-b");
   }
   if (options.port < 1024 || options.port > 65535)
   {
      throw std::runtime_error("port must be in the range 1024..65535");
   }
   if (options.runtimeMs < 1000 || options.runtimeMs > 30000)
   {
      throw std::runtime_error("runtime-ms must be in the range 1000..30000");
   }
   return options;
}

class UasHandler final : public resip::InviteSessionHandler
{
public:
   void onNewSession(resip::ClientInviteSessionHandle,
                     resip::InviteSession::OfferAnswerType,
                     const resip::SipMessage&) override
   {
   }

   void onNewSession(resip::ServerInviteSessionHandle session,
                     resip::InviteSession::OfferAnswerType,
                     const resip::SipMessage& message) override
   {
      mServerSession = session;
      mNewSession = true;
      std::cout << "CALLBACK UAS_NEW_SESSION call_id="
                << message.header(resip::h_CallId).value() << std::endl;
      session->provisional(180, false);
   }

   void onFailure(resip::ClientInviteSessionHandle,
                  const resip::SipMessage&) override
   {
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
                    const resip::SipMessage&) override
   {
   }

   void onConnected(resip::InviteSessionHandle,
                    const resip::SipMessage& message) override
   {
      mConnected = true;
      std::cout << "CALLBACK UAS_CONNECTED status="
                << message.header(resip::h_StatusLine).statusCode() << std::endl;
   }

   void onConnectedConfirmed(resip::InviteSessionHandle,
                             const resip::SipMessage& message) override
   {
      mAckConfirmed = true;
      std::cout << "CALLBACK UAS_CONNECTED_CONFIRMED cseq="
                << message.header(resip::h_CSeq).sequence() << std::endl;
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

   void onOffer(resip::InviteSessionHandle session,
                const resip::SipMessage&,
                const resip::SdpContents&) override
   {
      static const std::string answerText =
          "v=0\r\n"
          "o=- 5001 2 IN IP4 127.0.0.1\r\n"
          "s=UAS restart negative recovery probe\r\n"
          "c=IN IP4 127.0.0.1\r\n"
          "t=0 0\r\n"
          "m=audio 49172 RTP/AVP 0\r\n"
          "a=rtpmap:0 PCMU/8000\r\n"
          "a=sendrecv\r\n";
      const resip::HeaderFieldValue answerValue(answerText.data(), answerText.size());
      const resip::Mime answerType("application", "sdp");
      const resip::SdpContents answer(answerValue, answerType);

      std::cout << "CALLBACK UAS_OFFER_RECEIVED_AND_ANSWERED" << std::endl;
      session->provideAnswer(answer);
      mServerSession->accept(200);
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

   void onInfoSuccess(resip::InviteSessionHandle,
                      const resip::SipMessage&) override
   {
   }

   void onInfoFailure(resip::InviteSessionHandle,
                      const resip::SipMessage&) override
   {
   }

   void onMessage(resip::InviteSessionHandle, const resip::SipMessage&) override
   {
   }

   void onMessageSuccess(resip::InviteSessionHandle,
                         const resip::SipMessage&) override
   {
   }

   void onMessageFailure(resip::InviteSessionHandle,
                         const resip::SipMessage&) override
   {
   }

   void onRefer(resip::InviteSessionHandle,
                resip::ServerSubscriptionHandle,
                const resip::SipMessage&) override
   {
   }

   void onReferNoSub(resip::InviteSessionHandle,
                     const resip::SipMessage&) override
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

   bool connected() const
   {
      return mConnected;
   }

   bool ack_confirmed() const
   {
      return mAckConfirmed;
   }

private:
   resip::ServerInviteSessionHandle mServerSession;
   bool mNewSession{false};
   bool mConnected{false};
   bool mAckConfirmed{false};
};

void process_once(resip::SipStack& stack, resip::DialogUsageManager& dum)
{
   stack.process(10);
   while (dum.process())
   {
   }
}

int run(const Options& options)
{
   struct sigaction action
   {
   };
   action.sa_handler = request_stop;
   sigemptyset(&action.sa_mask);
   action.sa_flags = 0;
   if (sigaction(SIGTERM, &action, nullptr) != 0 ||
       sigaction(SIGINT, &action, nullptr) != 0)
   {
      throw std::runtime_error("could not install shutdown signal handlers");
   }

   resip::SipStack stack;
   auto profile = std::make_shared<resip::MasterProfile>();
   UasHandler handler;
   resip::DialogUsageManager dum(stack);
   const std::string defaultFrom =
       "sip:uas@127.0.0.1:" + std::to_string(options.port) + ";transport=udp";
   profile->setDefaultFrom(resip::NameAddr(
       resip::Uri(resip::Data(defaultFrom.c_str()))));
   dum.setMasterProfile(profile);

   dum.setInviteSessionHandler(&handler);
   stack.addTransport(resip::UDP, options.port, resip::V4,
                      resip::StunDisabled, resip::Data("127.0.0.1"));

   std::cout << "DUM_READY phase=" << options.phase
             << " pid=" << ::getpid()
             << " listen=127.0.0.1:" << options.port
             << " restore_state_argument_count=0" << std::endl;

   const auto deadline = std::chrono::steady_clock::now() +
                         std::chrono::milliseconds(options.runtimeMs);
   while (std::chrono::steady_clock::now() < deadline && stopRequested == 0)
   {
      process_once(stack, dum);
      if (options.phase == "phase-a" && handler.ack_confirmed())
      {
         break;
      }
      if (options.phase == "phase-b" && stopRequested != 0)
      {
         break;
      }
   }

   if (options.phase == "phase-a")
   {
      if (!handler.connected() || !handler.ack_confirmed())
      {
         std::cerr << "PHASE_A_INCOMPLETE connected=" << handler.connected()
                   << " ack_confirmed=" << handler.ack_confirmed() << std::endl;
         return 3;
      }
      std::cout << "PHASE_A_CONFIRMED_AND_EXITING_CLEANLY" << std::endl;
      return 0;
   }

   if (stopRequested == 0)
   {
      std::cerr << "PHASE_B_RUNTIME_EXPIRED_WITHOUT_STOP_SIGNAL" << std::endl;
      return 4;
   }
   std::cout << "PHASE_B_STOPPED_CLEANLY_BY_SIGNAL" << std::endl;
   return 0;
}

} // namespace

int main(int argc, char** argv)
{
   try
   {
      return run(parse_args(argc, argv));
   }
   catch (const std::exception& error)
   {
      std::cerr << "uas_dum_process.error=" << error.what() << std::endl;
      return 2;
   }
}
