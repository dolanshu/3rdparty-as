// resip_probe.cxx —— 最小化 reSIProcate SIP 服务器验证探针
// 目标：验证 reSIProcate DUM 层能正确处理 INVITE/100/180/200/ACK/BYE/CANCEL
// 与 POC 基线 S1/S4 对拍。本程序**不做媒体处理**（不带 SDP answer）。

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <memory>
#include <string>
#include <thread>

#include "resip/stack/Headers.hxx"
#include "resip/stack/HeaderFieldValue.hxx"
#include "resip/stack/NameAddr.hxx"
#include "resip/stack/SdpContents.hxx"    // ← 新增：构造假 SDP offer
#include "resip/stack/SecurityTypes.hxx"
#include "resip/stack/SipMessage.hxx"
#include "resip/stack/SipStack.hxx"
#include "resip/stack/Transport.hxx"
#include "resip/stack/Uri.hxx"
#include "resip/dum/AppDialog.hxx"
#include "resip/dum/AppDialogSet.hxx"
#include "resip/dum/AppDialogSetFactory.hxx"
#include "resip/dum/ClientInviteSession.hxx"
#include "resip/dum/DialogSet.hxx"
#include "resip/dum/DialogUsageManager.hxx"
#include "resip/dum/InviteSessionHandler.hxx"
#include "resip/dum/MasterProfile.hxx"
#include "resip/dum/ServerInviteSession.hxx"
#include "rutil/Data.hxx"
#include "rutil/Log.hxx"
#include "rutil/Logger.hxx"

using namespace resip;
using namespace std;

// ---------- 全局控制 ----------
static std::atomic<bool> g_run{true};

static void sigint_handler(int)
{
   g_run = false;
}

// ---------- 辅助 ----------

// 打印纯字符串标记
static void logStr(const char* msg)
{
   cout << "[probe] " << msg << endl;
}

// 打印 SipMessage 的关键信息（用 SipMessage::brief()，附加 Call-ID / Via branch / 状态码）
static void logMsg(const char* tag, const SipMessage& msg)
{
   cout << "[" << tag << "] " << msg.brief() << endl;

   // Call-ID：SipMessage::exists() 检查 header 是否存在
   if (msg.exists(h_CallId))
   {
      cout << "    Call-ID=" << msg.header(h_CallId).value();
   }

   // Via branch（正确 API：via.front().param(p_branch).getTransactionId()）
   if (msg.header(h_Vias).size() > 0 && msg.header(h_Vias).front().exists(p_branch))
   {
      cout << "  Via.branch=" << msg.header(h_Vias).front().param(p_branch).getTransactionId();
   }
   cout << endl;

   // Request-URI 或 Status-Line
   if (msg.isRequest())
   {
      cout << "    RURI=" << msg.header(h_RequestLine).uri() << endl;
   }
   else
   {
      cout << "    Status=" << msg.header(h_StatusLine).statusCode()
           << " " << msg.header(h_StatusLine).reason() << endl;
   }
}

// ---------- 极简 AppDialogSet ----------
// 给 DUM 一个合法的对话映射，不做任何额外事情
class ProbeAppDialogSet : public AppDialogSet
{
public:
   explicit ProbeAppDialogSet(DialogUsageManager& dum) : AppDialogSet(dum) {}
   virtual AppDialog* createAppDialog(const SipMessage& /*msg*/) override
   {
      // 直接返回默认空 AppDialog（不需要媒体）
      return new AppDialog(mDum);
   }
   virtual std::shared_ptr<UserProfile> selectUASUserProfile(const SipMessage& /*msg*/) override
   {
      return mDum.getMasterUserProfile();
   }
};

class ProbeAppDialogSetFactory : public AppDialogSetFactory
{
public:
   virtual AppDialogSet* createAppDialogSet(DialogUsageManager& dum,
                                            const SipMessage& /*msg*/) override
   {
      return new ProbeAppDialogSet(dum);
   }
};

// ---------- ProbeInviteHandler ----------
// 同时扮演 UAS（服务器）和 UAC（客户端发 INVITE 做自测）
class ProbeInviteHandler : public InviteSessionHandler
{
public:
   enum class Scenario { S1_BasicCall, S4_CallerCancel, S2_NoMatch404, S3_Policy603 };

   ProbeInviteHandler()
      : InviteSessionHandler(false /* genericOfferAnswer=false */),
        mScenario(Scenario::S1_BasicCall),
        mCanceled(false),
        mDum(nullptr)
   {
   }

   void setScenario(Scenario s) { mScenario = s; }
   void setDum(DialogUsageManager* dum) { mDum = dum; }

   ServerInviteSessionHandle mUasSession;  // 保存 UAS session，给 onOffer 调 accept() 用

   // ==== UAS 侧 ====

   virtual void onNewSession(ServerInviteSessionHandle sis,
                             InviteSession::OfferAnswerType oat,
                             const SipMessage& msg) override
   {
      logMsg("UAS onNewSession(Server)", msg);
      mUasSession = sis;   // 保存 handle，后续 onOffer/onOfferRequired 要用

      switch (mScenario)
      {
         case Scenario::S2_NoMatch404:
            logStr("S2: UAS → 404 Not Found");
            sis->reject(404);
            break;
         case Scenario::S3_Policy603:
            logStr("S3: UAS → 603 Decline");
            sis->reject(603);
            break;
         case Scenario::S1_BasicCall:
            logStr("UAS → 100 Trying");
            sis->provisional(100);
            logStr("UAS → 180 Ringing");
            sis->provisional(180);
            // 注意：accept(200) 会提供 answer 并发送 200 OK + ACK 自动处理
            // S1 的 answer 在 onOffer 里提供（因为 INVITE 带 SDP offer）
            break;
         case Scenario::S4_CallerCancel:
            // S4 场景：UAS 只发 100 + 180，**不立即发 200**
            // 给 UAC 时间在 dialog 建立前发 CANCEL
            logStr("UAS → 100 Trying");
            sis->provisional(100);
            logStr("UAS → 180 Ringing");
            sis->provisional(180);
            logStr("UAS: 等待 CANCEL（不立即 accept）");
            break;
      }
   }

   // UAS 收到 ACK → dialog connected
   virtual void onConnected(InviteSessionHandle is, const SipMessage& msg) override
   {
      logMsg("UAS onConnected (ACK received)", msg);
   }

   // 对端发来 SDP offer
   virtual void onOffer(InviteSessionHandle is, const SipMessage& msg,
                        const SdpContents& sdp) override
   {
      logMsg("UAS onOffer (provide empty answer + accept)", msg);
      if (mScenario == Scenario::S4_CallerCancel)
      {
         logStr("S4: UAS 收到 SDP offer，但不 accept（等 CANCEL）");
         return;
      }
      // S1 场景：构造最小 SDP answer（端口 0，无媒体）
      const char* emptyAnswer =
         "v=0\r\n"
         "o=probe 0 0 IN IP4 127.0.0.1\r\n"
         "s=probe\r\n"
         "c=IN IP4 0.0.0.0\r\n"
         "t=0 0\r\n";  // 无 m= 行 = 无媒体
      HeaderFieldValue hfv(emptyAnswer, strlen(emptyAnswer));
      SdpContents answer(hfv, SdpContents::getStaticType());
      // 先 provideAnswer，再 accept（DUM 要求 offer/answer 完整才能发 200）
      is->provideAnswer(answer);
      if (mUasSession.isValid())
      {
         mUasSession->accept(200);
      }
   }

   virtual void onOfferRequired(InviteSessionHandle is, const SipMessage& msg) override
   {
      logMsg("UAS onOfferRequired (probe 不做媒体，忽略)", msg);
      // 不做任何 offer/answer 交换，probe 目标只验证 SIP 信令流程
      // 注意：DUM 要求 offer/answer 交换，如果两边都没有 SDP 可能会有问题
      // 实际情况：当 UAS 的 200 OK 没有 answer 时，UAC 应该继续 ACK
      // 我们这里不主动 requestOffer，让流程走完
   }

   // ==== UAC 侧 ====

   virtual void onNewSession(ClientInviteSessionHandle cis,
                             InviteSession::OfferAnswerType oat,
                             const SipMessage& msg) override
   {
      logMsg("UAC onNewSession(Client)", msg);

      // S4 场景：刚建好 ClientInviteSession 就发 CANCEL
      // （等 UAS 回 100/180 可能已经太晚了——UAS 同步发了 200 OK）
      if (mScenario == Scenario::S4_CallerCancel && !mCanceled)
      {
         mCanceled = true;
         logStr("S4: UAC → CANCEL (via mDum->end(DialogSetId))");
         // 不用 cis->end()（ClientInviteSession::end 在某些状态发 BYE）
         // 直接调 DUM::end(DialogSetId)，它能正确发 CANCEL 或 BYE
         if (mDum) mDum->end(cis->getDialogId().getDialogSetId());
      }
   }

   // 收到 100/180 等 1xx（S4 里也来这里，但已经 canceled）
   virtual void onProvisional(ClientInviteSessionHandle cis,
                              const SipMessage& msg) override
   {
      logMsg("UAC onProvisional", msg);
   }

   // 收到 200 OK → DUM 自动发 ACK
   virtual void onConnected(ClientInviteSessionHandle cis,
                            const SipMessage& msg) override
   {
      logMsg("UAC onConnected (200 OK, ACK auto-sent)", msg);

      if (mScenario == Scenario::S1_BasicCall)
      {
         // hold 一下 → UAC 先发 BYE
         std::this_thread::sleep_for(std::chrono::milliseconds(200));

         // === E4 热轮换尝试 ===
         // 如果当前开启了 TLS，尝试运行时换证书。
         // reSIProcate SipStack::addTransport 在启动时将证书加载进 OpenSSL
         // context，之后没有公开 API 支持重新加载。此处打印尝试结果。
         static int s_hotRotateAttempted = 0;
         if (s_hotRotateAttempted++ == 0)
         {
            logStr("E4 TLS: 尝试证书热轮换...");
            // SipStack 没有 reloadCertificate() / updateTransport() 之类 API。
            // 下面这段注释掉的伪代码说明了"如果有 API 应该怎么写"：
            //   Transport* tls = g_stack->getTransport(TLS, tlsPort);
            //   tls->reloadCertificate(newCertFile, newKeyFile);  // 不存在
            logStr("E4 TLS: reSIProcate 不支持证书热轮换——这是 E4 待验证缺口");
         }

         logStr("S1: UAC → BYE (end call)");
         cis->end();
      }
   }

   virtual void onFailure(ClientInviteSessionHandle cis,
                          const SipMessage& msg) override
   {
      logMsg("UAC onFailure", msg);
   }

   // ==== 终止 ====

   virtual void onTerminated(InviteSessionHandle is,
                             InviteSessionHandler::TerminatedReason reason,
                             const SipMessage* msg) override
   {
      const char* reasonStr = "unknown";
      switch (reason)
      {
         case InviteSessionHandler::Error:        reasonStr = "Error"; break;
         case InviteSessionHandler::Timeout:      reasonStr = "Timeout"; break;
         case InviteSessionHandler::Replaced:     reasonStr = "Replaced"; break;
         case InviteSessionHandler::LocalBye:     reasonStr = "LocalBye"; break;
         case InviteSessionHandler::RemoteBye:    reasonStr = "RemoteBye"; break;
         case InviteSessionHandler::LocalCancel:  reasonStr = "LocalCancel"; break;
         case InviteSessionHandler::RemoteCancel: reasonStr = "RemoteCancel"; break;
         case InviteSessionHandler::Rejected:     reasonStr = "Rejected"; break;
         case InviteSessionHandler::Referred:     reasonStr = "Referred"; break;
      }
      cout << "[onTerminated] reason=" << reasonStr;
      if (msg)
      {
         cout << "  related=" << msg->brief();
      }
      cout << endl;
   }

   // ==== 其他纯虚函数的默认空实现 ====

   virtual void onEarlyMedia(ClientInviteSessionHandle, const SipMessage& msg,
                             const SdpContents&) override
   { logMsg("onEarlyMedia (ignored)", msg); }

   virtual void onAnswer(InviteSessionHandle is, const SipMessage& msg,
                         const SdpContents&) override
   { logMsg("onAnswer (ignored)", msg); }

   virtual void onOfferRejected(InviteSessionHandle, const SipMessage* msg) override
   {
      if (msg) logMsg("onOfferRejected", *msg);
      else cout << "[onOfferRejected]" << endl;
   }

   virtual void onForkDestroyed(ClientInviteSessionHandle) override
   { cout << "[onForkDestroyed]" << endl; }

   virtual void onRedirected(ClientInviteSessionHandle, const SipMessage& msg) override
   { logMsg("onRedirected", msg); }

   virtual void onInfo(InviteSessionHandle, const SipMessage& msg) override
   { logMsg("onInfo (ignored)", msg); }
   virtual void onInfoSuccess(InviteSessionHandle, const SipMessage& msg) override
   { logMsg("onInfoSuccess (ignored)", msg); }
   virtual void onInfoFailure(InviteSessionHandle, const SipMessage& msg) override
   { logMsg("onInfoFailure (ignored)", msg); }
   virtual void onMessage(InviteSessionHandle, const SipMessage& msg) override
   { logMsg("onMessage (ignored)", msg); }
   virtual void onMessageSuccess(InviteSessionHandle, const SipMessage& msg) override
   { logMsg("onMessageSuccess (ignored)", msg); }
   virtual void onMessageFailure(InviteSessionHandle, const SipMessage& msg) override
   { logMsg("onMessageFailure (ignored)", msg); }
   virtual void onRefer(InviteSessionHandle, ServerSubscriptionHandle,
                        const SipMessage& msg) override
   { logMsg("onRefer (ignored)", msg); }
   virtual void onReferNoSub(InviteSessionHandle, const SipMessage& msg) override
   { logMsg("onReferNoSub (ignored)", msg); }
   virtual void onReferRejected(InviteSessionHandle, const SipMessage& msg) override
   { logMsg("onReferRejected (ignored)", msg); }
   virtual void onReferAccepted(InviteSessionHandle, ClientSubscriptionHandle,
                                const SipMessage& msg) override
   { logMsg("onReferAccepted (ignored)", msg); }

private:
   Scenario mScenario;
   bool mCanceled;
   DialogUsageManager* mDum;   // 注入的 DUM 指针，用于 end(DialogSetId)
};

// ---------- 全局对象 & 自测驱动 ----------

static ProbeInviteHandler g_handler;
static DialogUsageManager* g_dum = nullptr;
static SipStack* g_stack = nullptr;

static void driveSelfTest(const std::string& scenario, int uasPort,
                          int tlsPort /* -1 = UDP only */)
{
   // 等 UAS 起来（DUM 注册完成）
   std::this_thread::sleep_for(std::chrono::milliseconds(200));

   bool useTls = (tlsPort > 0);
   Data scheme = useTls ? Data("sips") : Data("sip");
   int port = useTls ? tlsPort : uasPort;
   Data targetUri = scheme + ":probe@127.0.0.1:" + Data(port);
   cout << "\n=== SELF-TEST: UAC → " << targetUri << " (scenario="
        << scenario << ", transport=" << (useTls ? "TLS" : "UDP") << ") ===" << endl;

   try
   {
      // 构造一个最小 SDP offer（端口 0，不实际做媒体）
      // 这样 UAS 会触发 onOffer 回调而不是 onOfferRequired
      const char* minimalSdp =
         "v=0\r\n"
         "o=probe 0 0 IN IP4 127.0.0.1\r\n"
         "s=probe\r\n"
         "c=IN IP4 127.0.0.1\r\n"
         "t=0 0\r\n"
         "m=audio 0 RTP/AVP 0\r\n";
      // HeaderFieldValue + Mime 方式（Data/Mime 构造是 private 的）
      HeaderFieldValue hfv(minimalSdp, strlen(minimalSdp));
      std::shared_ptr<SdpContents> offer =
         std::make_shared<SdpContents>(hfv, SdpContents::getStaticType());

      NameAddr target{Uri(targetUri)};
      std::shared_ptr<SipMessage> invite =
         g_dum->makeInviteSession(target, offer.get(), nullptr);

      cout << "[UAC send] INVITE (with minimal SDP) →  127.0.0.1:" << port << endl;
      logMsg("UAC (outgoing)", *invite);

      // 用 DUM::send（接受 shared_ptr，会走 DUM 的发送队列）
      g_dum->send(invite);
   }
   catch (std::exception& e)
   {
      cerr << "[UAC] Exception creating/sending INVITE: " << e.what() << endl;
      g_run = false;
   }
}

// ---------- 主函数 ----------

int main(int argc, char** argv)
{
   // 解析参数
   std::string scenario = "S1";   // 默认基本呼叫
   bool externalMode = false;     // true = 只做 UAS，等外部客户端
   bool tlsEnabled = false;       // true = 同时监听 TLS
   std::string certFile = "cert.pem";
   std::string keyFile = "key.pem";
   for (int i = 1; i < argc; ++i)
   {
      std::string arg = argv[i];
      if (arg == "--external") externalMode = true;
      else if (arg == "--tls") tlsEnabled = true;
      else if (arg == "--cert" && i + 1 < argc) certFile = argv[++i];
      else if (arg == "--key" && i + 1 < argc)  keyFile  = argv[++i];
      else if (arg == "S1" || arg == "S4" || arg == "S2" || arg == "S3") scenario = arg;
   }

   cout << "=== resip_probe: reSIProcate SIP 验证探针 ===" << endl;
   cout << "scenario = " << scenario
        << "  mode = " << (externalMode ? "external-UAS-only" : "self-test")
        << "  tls = " << (tlsEnabled ? "on" : "off") << endl;

   // 设置场景
   ProbeInviteHandler::Scenario sc = ProbeInviteHandler::Scenario::S1_BasicCall;
   if (scenario == "S4") sc = ProbeInviteHandler::Scenario::S4_CallerCancel;
   else if (scenario == "S2") sc = ProbeInviteHandler::Scenario::S2_NoMatch404;
   else if (scenario == "S3") sc = ProbeInviteHandler::Scenario::S3_Policy603;
   g_handler.setScenario(sc);

   // SIGINT/SIGTERM
   std::signal(SIGINT, sigint_handler);
   std::signal(SIGTERM, sigint_handler);

   // 初始化 reSIProcate 日志：Cout 输出 + None 级别（静默内部日志）
   Log::initialize(Log::Cout /*Type*/, Log::None /*Level*/, Data("resip_probe") /*appName*/);

   // 1. 创建 SipStack
   g_stack = new SipStack();

   // 2. 添加 UDP transport（port=0 → 内核分配随机端口）
   Transport* udp = g_stack->addTransport(UDP, /*port=*/0, V4);
   int uasPort = udp->port();
   cout << "\n[UAS] 监听 UDP 127.0.0.1:" << uasPort << endl;

   // 2b. 可选：TLS transport（E4 场景）
   // TODO(E4 热轮换): reSIProcate SipStack 目前没有公开 API 支持运行时
   // 替换 TLS 证书（addTransport 在启动时加载证书到 OpenSSL context，
   // 之后无 reload 入口）。如果后续 reSIProcate 提供 SslContext 热更新
   // 或 addTransport 的 certificateFile 参数重载能力，可以在此处接入。
   // 当前 probe 目标是 **验证 TLS 能正确收发 SIP 消息**，热轮换作为
   // 已知短板（ADR-0019 §7 K8）留待后续独立验证。
   int tlsPort = -1;
   if (tlsEnabled)
   {
      if (!std::filesystem::exists(certFile) || !std::filesystem::exists(keyFile))
      {
         cerr << "[probe] 错误: TLS 需要 cert.pem 和 key.pem。先跑 ./gen-cert.sh" << endl;
         return 1;
      }
      Transport* tls = g_stack->addTransport(
         TLS, /*port=*/0, V4,
         StunDisabled,                   // StunSetting
         Data("0.0.0.0"),                // ipInterface
         Data("127.0.0.1"),              // sipDomainname
         Data::Empty,                    // privateKeyPassPhrase
         SecurityTypes::SSLv23,          // sslType
         0,                              // transportFlags
         Data(certFile.c_str()),         // certificateFilename
         Data(keyFile.c_str()));         // privateKeyFilename
      tlsPort = tls->port();
      cout << "[UAS] 监听 TLS 127.0.0.1:" << tlsPort
           << "  cert=" << certFile << "  key=" << keyFile << endl;
   }

   // 3. 创建 DialogUsageManager
   g_dum = new DialogUsageManager(*g_stack);

   // 4. MasterProfile（UAS 的 From / Contact）
   auto masterProfile = std::make_shared<MasterProfile>();
   Data contact = "sip:probe@127.0.0.1:" + Data(uasPort);
   masterProfile->setOverrideHostAndPort(Uri(contact));
   masterProfile->setDefaultFrom(NameAddr(contact));
   g_dum->setMasterProfile(masterProfile);

   // 5. InviteSessionHandler（注入 DUM 指针，handler 内部要用它 end(DialogSetId) 发 CANCEL）
   g_handler.setDum(g_dum);
   g_dum->setInviteSessionHandler(&g_handler);

   // 6. AppDialogSetFactory
   auto factory = std::make_unique<ProbeAppDialogSetFactory>();
   g_dum->setAppDialogSetFactory(std::move(factory));

   // 7. 启动自测子线程（externalMode 则跳过，等外部客户端连）
   std::thread uacThread;
   if (!externalMode)
   {
      uacThread = std::thread([&]() { driveSelfTest(scenario, uasPort, tlsPort); });
   }

   // 8. 主循环
   cout << "\n=== 进入主循环 (Ctrl+C 退出) ===" << endl;
   while (g_run.load())
   {
      g_stack->process(/*timeoutMs=*/50);
      while (g_dum->process()) { /* 处理完所有 DUM 事件 */ }
   }

   cout << "\n=== 收到退出信号，清理中 ===" << endl;
   if (uacThread.joinable()) uacThread.join();

   delete g_dum;
   delete g_stack;

   cout << "=== probe 退出 OK ===" << endl;
   return 0;
}
