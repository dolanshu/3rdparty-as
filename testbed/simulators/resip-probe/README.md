# resip_probe —— reSIProcate E1 验证探针

最小化 reSIProcate SIP 服务器程序，用来验证 reSIProcate DUM（Dialog Usage Manager）层的 SIP 信令行为是否正确。

## 功能

同时扮演 **UAS（服务器）** 和 **UAC（客户端）**，自动跑完整 SIP 信令场景，每条消息都打印：方法/响应码、Call-ID、Via branch、Request-URI。

不做媒体处理——SDP offer/answer 里端口都是 0，探针不绑定实际 RTP 端口。

## 支持的场景

| 场景 | 说明 | 消息序列 |
|---|---|---|
| **S1** (默认) | 基本呼叫 | INVITE → 100 → 180 → 200 → ACK → BYE → 200 |
| **S4** | Caller CANCEL | INVITE → 100 → 180 → **CANCEL** → 487 → ACK |
| **S2** | 无匹配 → 404 | INVITE → 100 → **404** |
| **S3** | 策略拒绝 → 603 | INVITE → 100 → **603** |

## 编译（首次）

```bash
# 自动构建 reSIProcate（约 5 分钟，一次即可）
cd testbed/simulators/resip-probe
bash build-req.sh

# 编译 probe
rm -rf build && mkdir -p build && cd build
cmake .. -DRESIP_HOME=/tmp/resiprocate -DRESIP_BUILD=/tmp/resiprocate/_build
make -j$(nproc)
```

## 运行

```bash
# S1 基本呼叫（默认）：probe 自己发 INVITE → 收到自己的 UAS 响应 → 完整走完
./resip_probe
./resip_probe S1

# S4 Caller CANCEL：UAS 发 100+180 后等 CANCEL，UAC 立即 CANCEL
./resip_probe S4

# S2 404 / S3 603
./resip_probe S2
./resip_probe S3

# external 模式：probe 只做 UAS，监听随机端口，等外部客户端连入
./resip_probe --external
```

### E4 TLS 场景

probe 支持同时监听 UDP 和 TLS，用来验证 reSIProcate 的 TLS SIP 收发能力。

```bash
# 1. 生成临时自签证书（有效期 1 天，CN=127.0.0.1）
bash gen-cert.sh

# 2. 跑 S1 基本呼叫（消息走 TLS transport）
./resip_probe --tls S1

# 3. external 模式等外部 TLS 客户端
./resip_probe --tls --external

# 4. 指定自定义证书路径
./resip_probe --tls --cert /path/to/cert.pem --key /path/to/key.pem S1
```

运行输出会多一行 `[UAS] 监听 TLS 127.0.0.1:<随机端口>`。
self-test 模式下 UAC→UAS 走 sips: scheme + TLS 端口（进程内 loopback），
external 模式下外部客户端可以用 openssl s_client 或任何支持 TLS 的 SIP UA 连接。

**E4 已知缺口**：probe 会在 BYE 之前打印 `E4 TLS: reSIProcate 不支持证书热轮换——这是 E4 待验证缺口`。
reSIProcate `SipStack::addTransport` 在启动时加载证书到 OpenSSL context，之后没有公开 API 支持运行时 reload。
这与 [ADR-0019 §7 K8](../../../docs/architecture/adr/0019-sip-stack-selection.md) 的已知短板记录一致。

所有场景都可以 `Ctrl+C` 退出。

## 对拍输出解读

以 S1 为例，运行输出：

```
[UAC (outgoing)] SipReq: INVITE probe@127.0.0.1:... tid=xxx cseq=1 ...
    Call-ID=yAml4Q63ALq0ZNuIQwq_OA..  Via.branch=9d1a8bf3d31e2979af855066f
    RURI=sip:probe@127.0.0.1:...
[UAS onNewSession(Server)] SipReq: INVITE probe@127.0.0.1:... tid=yyy cseq=1 ...
    Call-ID=yAml4Q63ALq0ZNuIQwq_OA..  Via.branch=4dc697c4156b448caf85506d4
    RURI=sip:probe@127.0.0.1:...
[probe] UAS → 100 Trying
[probe] UAS → 180 Ringing
...
[probe] S1: UAC → BYE (end call)
[onTerminated] reason=LocalBye ...
[onTerminated] reason=RemoteBye ...
```

**关键断言**（对照 `testbed/contracts/sip-baseline/` 下的 S1/S4 基线）：

- ✅ Call-ID 合法（两边相同）
- ✅ Via branch 是 reSIProcate 格式（32 字符 hex，替代 RFC 3261 的 `z9hG4bK` magic cookie）
- ✅ 消息顺序正确（S1: INVITE→100→180→200→ACK→BYE→200；S4: INVITE→100→180→CANCEL→487→ACK）
- ✅ 响应码正确（100, 180, 200, 487）
- ✅ CANCEL 正确触发 487 Request Terminated，双方 Terminated 回调收到 reason=LocalCancel / RemoteCancel

**不校验**：Via branch 具体值、Call-ID 具体值、SDP 内容（probe 故意发假的）。

## 技术要点

| 要点 | 实现 |
|---|---|
| SIP 栈 | reSIProcate `SipStack` + `DialogUsageManager` (DUM) |
| 监听 | `addTransport(UDP, 0)` —— 内核分配随机端口 |
| UAS 100/180/200 | `ServerInviteSession::provisional(code)` + `accept(200)` |
| SDP offer/answer | 双方带假 SDP，端口 0。DUM 要求 offer/answer 交换完成才能 accept() |
| CANCEL vs BYE | `DialogUsageManager::end(DialogSetId)` 在 early 状态发 CANCEL，answered 状态发 BYE |
| 回调处理 | `InviteSessionHandler` 全部 20+ 纯虚函数实现，UAS/UAC 共用一个 handler |
| 日志 | `Log::initialize(Log::Cout, Log::None, ...)` 静默 reSIProcate 内部日志 |

## 已知限制

1. **CANCEL 必须早于 200 OK** —— UAS 在同一个函数里同步发完 provisional + accept，可能在 UAC 处理 CANCEL 之前就建立了 dialog。S4 场景让 UAS 在 onNewSession 里只发 provisional、等 offer 回调才 accept（但在 onOffer 里跳过 accept）。如果以后把 UAS accept 的时机改得更晚（比如定时器 500ms），可能不需要这个 workaround。

2. **无路由/注册** —— 探针不做 Route/Record-Route、不做 REGISTER、不做 DNS。只验证 INVITE/CANCEL/BYE 的基础对话。

3. **无 TCP** —— 只跑 UDP 和 TLS（`--tls`）。TCP transport 未启用。`recon` 库没编译所以 probe 不链接它。

## 文件结构

```
testbed/simulators/resip-probe/
├── CMakeLists.txt       # 最小构建，链接 libresip/libdum/librutil + ssl/crypto/pthread
├── resip_probe.cxx      # 主程序（单文件 ~550 行，支持 --tls E4 场景）
├── build-req.sh         # 自动克隆 + 构建 reSIProcate 到 /tmp/resiprocate
├── gen-cert.sh          # 生成临时自签证书（E4 TLS 场景用）
└── README.md            # 本文件
```

## 与 POC 基线的关系

POC（`3rtparty_AS_POC`）在 sippy 上抓取的基线（`testbed/contracts/sip-baseline/S1-S4`）是实际线上期望的 SIP 消息序列。本 probe 用 reSIProcate 跑出同样的序列，作为 E1 阶段的"reSIProcate 能做到吗？"验证。
