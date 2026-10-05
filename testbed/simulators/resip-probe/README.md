# resip_probe —— reSIProcate E1 验证探针

最小化 reSIProcate SIP 服务器程序，用来验证 reSIProcate DUM（Dialog Usage Manager）层的 SIP 信令行为是否正确。

## 功能

同时扮演 **UAS（服务器）** 和 **UAC（客户端）**，自动跑完整 SIP 信令场景，每条消息都打印：方法/响应码、Call-ID、Via branch、Request-URI。

不做媒体处理——SDP offer/answer 里端口都是 0，探针不绑定实际 RTP 端口。

## 支持的场景

| 场景 | 说明 | 消息序列 |
|---|---|---|
| **S1** (默认) | 基本呼叫 | INVITE → 100 → 180 → 200 → ACK → BYE → 200 |
| **S4** | Caller CANCEL | INVITE → 100 → 180 → **CANCEL** → 487 → ACK（协议期望；本 probe 未独立抓到线上的 ACK 包） |
| **S2** | 无匹配 → 404 | INVITE → 100 → **404** |
| **S3** | 策略拒绝 → 603 | INVITE → 100 → **603** |

## Reproducible vendor build (M2 P0)

For a **repository-local** path that does not clone from GitHub or rely on `/tmp`
handoff directories, use the checked-in vendor bundle and `scripts/m2-native.sh`:

```bash
# From repository root
make m2-native          # restore + cmake build + S1 UDP smoke
make m2-native-restore  # verify SHA256SUMS and unpack source only
make m2-native-build    # build reSIProcate + resip_probe under .cache/m2-resiprocate
make m2-native-smoke    # run ./resip_probe S1 (UDP)
make m2-native-smoke-tcp  # run ./resip_probe --tcp S1 (TCP loopback)
```

Defaults: cache root is `.cache/m2-resiprocate` (`AS_RESIP_CACHE_ROOT`). The
validated matrix is Ubuntu 20.04 x86_64 with OpenSSL 1.1-era runtime libraries;
see [`docs/acceptance/m2-native-build-matrix.md`](../../../docs/acceptance/m2-native-build-matrix.md).

Optional fast path: set `AS_RESIP_USE_PREBUILT=1` on `restore` to unpack the
bundled prebuilt libraries (still prefer `build-probe` so the probe links with
cache RPATH, not `/tmp` RUNPATH). `build-req.sh` remains the legacy online clone
path and is not the M2 P0 offline workflow.

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

### TCP transport（M2 P2b）

`--tcp` 在现有 UDP listener 之外再注册一个 TCP listener（`port=0` 由内核分配）。`--external` 时同时对外提供 UDP + TCP（若还加了 `--tls` 则再加 TLS）。

```bash
# S1 self-test：UAC 目标为 sip:…;transport=tcp，走 TCP 端口
./resip_probe --tcp S1

# external：等外部 SIP 客户端经 TCP 或 UDP 连入
./resip_probe --tcp --external
```

说明：仅 `--tcp`（无 `--tls`）的 self-test 走明文 TCP；TLS 仍用现有 `--tls`（可同时 `--tcp --tls`，self-test 优先 TLS）。这不是产品 transport binding，也不代表 REQ-S-2/3 已验收。

仓库根：`make m2-native-smoke-tcp` 或 `bash scripts/m2-native.sh smoke-tcp`（需先 `make m2-native-build`）。

### E4 TLS 场景

probe 支持同时监听 UDP 和 TLS，用来验证 reSIProcate 的 TLS SIP 收发能力。

```bash
# 1. 生成临时自签证书（有效期 1 天，CN=127.0.0.1）
bash gen-cert.sh

# 注意：若当前目录已存在 cert.pem 或 key.pem（或它们是符号链接），脚本会拒绝运行并退出非零。

# 2. 跑 S1 基本呼叫（消息走 TLS transport）
./resip_probe --tls S1

# 3. external 模式等外部 TLS 客户端
./resip_probe --tls --external

# 4. 指定自定义证书路径
./resip_probe --tls --cert /path/to/cert.pem --key /path/to/key.pem S1
```

说明：仅在 `--tls` 且非 `--external` 的 self-test 模式，probe 才会显式把 `--cert` 指向的本地自签证书加入本进程 trust（用于 loopback `sips:127.0.0.1`）。这不是生产 CA trust、不是 mTLS，也不代表 REQ-S-2/REQ-S-3 或证书热轮换已验收。

运行输出会多一行 `[UAS] 监听 TLS 127.0.0.1:<随机端口>`。
self-test 模式下 UAC→UAS 走 sips: scheme + TLS 端口（进程内 loopback），
external 模式下外部客户端可以用 openssl s_client 或任何支持 TLS 的 SIP UA 连接。

`--hold-ms` 行为说明：S1 在 `onConnected` 时只做 BYE 调度（记录 deadline），实际 `end()` 发送发生在主循环 `processScheduledActions()`。当 `--hold-ms 0` 时，BYE 会在下一次主循环迭代被触发，不会在回调栈内立即发送，因此不保证零时延发送。

TLS S1（BYE-hold 路径）会出现一条静态 scope note（一次）：`TLS S1 note: this BYE-hold path validates signaling only; see README 2026-10-04 testbed evidence for SIGHUP cert-swap observations. This log line does not prove reload execution and does not establish REQ-S-3.`

仅当进程真实收到 `SIGHUP` 且启用了 `--tls` 时，主循环才会打印：`SIGHUP received: invoking SipStack::reloadCertificates()`。

**E4 已知缺口**：上述静态 scope note 与一次性 smoke 证据都不构成热轮换验收结论。
按 reSIProcate 1.14.0 源码核对，公开 API `SipStack::reloadCertificates()` 存在；它会遍历 secure transports 并触发 `TlsBaseTransport::onReload()`，后者仅标记 `mReloadCertificate=true`。证书/私钥实际重读发生在后续 TLS context 访问路径（`getCtx()`）里，通过 `Security::updateDomainCtx(...)` 更新 SSL_CTX。
2026-10-04 已完成一次 **testbed-only** 定时证书替换 smoke（见下节）：运行中的 TLS S1 hold 期间触发 SIGHUP，日志显示 `SipStack::reloadCertificates()` 调用，再完成 BYE；随后新 TLS 连接在仅信任 cert-B 的客户端上校验通过并返回 cert-B。该单次 smoke 仍不足以证明 REQ-S-3 所需的双证书重叠窗口与热轮换验收语义。
这与 [ADR-0019 §7 K8](../../../docs/architecture/adr/0019-sip-stack-selection.md) 的已知短板记录一致。

## 2026-10-04 Testbed-only SIGHUP Cert-Swap Smoke (Post-Contact-fix Valid Run, Not REQ-S-3 Acceptance)

范围：仅 native reSIProcate probe、本机 loopback、单通 active S1、单次手工触发。
有效证据仅指 Contact 修正后（TLS-mode master-profile 使用 `sips:` Contact 且指向 TLS listener 端口）的 90 秒 run。

结果（已观察到；成功证据为 `probe-signal-safe-90s.log`）：

1. probe 以 cert-A 启动 `--tls S1 --hold-ms 90000`，日志确认 INVITE 200/ACK 与 `S1 session established; BYE deadline scheduled`。
2. active hold 期间原子替换同一路径 cert/key 为 cert-B，并向同一 probe PID 发送 `SIGHUP`。
3. 日志顺序确认 `SIGHUP received: invoking SipStack::reloadCertificates()` 先于 `S1 hold deadline reached` 与 BYE。
4. 该 dialog 正常完成 BYE；UAS 收到 BYE 的日志行包含 `tlsd=127.0.0.1`，且 BYE Request-URI/Contact 指向 TLS listener 端口（`sips:` Contact），随后出现 `LocalBye` / `RemoteBye`，probe 在 SIGINT 后正常退出。
5. 对同一仍在运行 probe，新建 OpenSSL TLS 连接使用仅信任 cert-B 的 CA 文件并校验 IP SAN `127.0.0.1`，TLS 1.3 握手与验证成功，表明新连接服务证书为 B。
6. 对同一仍在运行 probe，新建 OpenSSL TLS 连接若仅信任旧 cert-A，会在验证阶段失败（`self signed certificate`）。

排除项（不计入证据）：

- 一次更早的 15/20 秒 hold 尝试未命中窗口，SIGHUP 发生在 BYE 之后；该次不计入证据。

历史纠偏（必须排除）：

- 在 Contact 修正前，TLS-mode master-profile Contact 曾指向 UDP listener 端口。该阶段的 A/B reload 记录即使出现 active-call 完成，也不能证明该 in-flight dialog 的 BYE 保持在 TLS 上。
- 因此，所有 pre-Contact-fix 的 active-call cert-swap 记录均已 superseded，不计入 full TLS in-flight active-call preservation 证据。

边界（明确非结论）：

- 该证据只覆盖一条本机 loopback active call 在一次 SIGHUP reload 调用下完成 BYE，以及一次后续新连接证书切换结果。
- 不等于 operator PKI trust、外部 S-SBC 集成、client certificate identity/mTLS enforcement。
- 不等于 simultanous old/new peer overlap、dual-certificate window、rollback 或多并发呼叫行为验证。
- 不等于生产 platform transport adapter/runtime binding 验证。
- 不构成 REQ-S-2/REQ-S-3 验收；D8 仍 open，M2 仍 open。

## Manual Reproduction Steps (Optional)

下面是一个仅用于 testbed 的手工实验脚手架，用于验证 probe 的 SIGHUP reload hook 是否可触发 `SipStack::reloadCertificates()`：

1. 生成两套本地测试证书/私钥（pair-A、pair-B），都带 `127.0.0.1` 的 SAN。
2. 先用 pair-A 启动 TLS self-test，并拉长通话保持时间，例如 `./resip_probe --tls --hold-ms 5000 S1`。
3. 在不重启 probe 的前提下，原子替换 `--cert/--key` 路径对应文件为 pair-B。
4. 对 probe 进程发送 `SIGHUP`，观察日志出现 `invoking SipStack::reloadCertificates()`。
5. 让当前呼叫自然完成；随后发起一个新的 TLS 客户端连接，确认对端展示的是 pair-B 证书。

说明：这只是 testbed 脚手架与单次 smoke 的复现步骤，不是验收结论；不能据此宣称满足 REQ-S-3。

当前项目状态与 [`docs/plan.md`](../../../docs/plan.md) 一致：reSIProcate 已被 ADR-0019 选定，但 M2 仍未完成；本 probe 仅提供 M2 阶段的 testbed 证据。

## 2026-10-04 已验证证据（M2）

- 依赖准备：在维护者授权下补齐 `libpopt-dev`、`libc-ares-dev`；CMake 3.31.12 来自 Kitware Focal 源，签名 key 指纹已对照 Kitware 公布值。用于 `apt update` 的 Kitware source/key 仅放在 `/tmp` 临时路径，不代表写入 `/etc/apt/sources.list.d`。
- 源码与构建：reSIProcate 使用 tag `resiprocate-1.14.0`（commit `632e215c2ca9aee5416bfe1808851ea6fa380044`），最小构建产物包含 `libresip-1.14.so`、`libdum-1.14.so`、`librutil-1.14.so`、`sipdialer`。
- probe 构建：本仓库 `testbed/simulators/resip-probe` 已在 native 环境构建成功。
- UDP self-test：S1 自测通过（100/180/200，ACK，BYE/200，`probe 退出 OK`）。
- TLS self-test：修复 probe TLS trust 初始化后，空临时 HOME 下 S1 loopback 通过（100/180/200，ACK，BYE/200，`probe 退出 OK`），未出现 `503 Certificate Validation Failure`。
- TLS self-test（非 external，本地自签证书）：S2 返回 `404 Not Found` 并正常退出（`probe 退出 OK`）。
- TLS self-test（非 external，本地自签证书）：S3 返回 `603 Decline` 并正常退出（`probe 退出 OK`）。
- TLS self-test（非 external，本地自签证书）：S4 出现 `UAC → CANCEL`，DUM 日志出现 `RemoteCancel`/`LocalCancel` 与 `487` 路径并正常退出（`probe 退出 OK`）；ACK 线包未独立抓取，不宣称已捕获。
- 2026-10-04 external OpenSSL SIP INVITE over TLS：以空 HOME 启动 `./resip_probe --tls --external`（当次动态端口 35619），另进程使用 `openssl s_client -connect 127.0.0.1:35619 -CAfile /tmp/as-resiprocate-m2-tls-selftest-20261004/cert.pem -verify_return_error -verify_ip 127.0.0.1` 校验本地自签证书/IP SAN 后发送一条 raw `sips:` INVITE（Via/Call-ID/CSeq/SDP 完整）；probe 日志确认收到该 INVITE（`tlsd=127.0.0.1`）并返回 `100 Trying`、`180 Ringing`、`200 OK`。外部客户端未发送 ACK/BYE，因此这是一次 external SIP transaction/early dialog response 证据，不是完整 call/dialog，也不构成 SIP/REQ-S-2/REQ-S-3 验收。
- 2026-10-04 post-Contact-fix active-call cert swap（有效 run：`probe-full-tls-rotation.log`）：cert-A 启动 `--tls S1 --hold-ms 90000`，active hold 期间替换 cert/key 为 cert-B 并发送 `SIGHUP`；日志顺序显示 `SIGHUP received: invoking SipStack::reloadCertificates()` 先于 hold deadline/BYE；BYE 接收行包含 `tlsd=127.0.0.1` 且 Request-URI/Contact 指向 TLS listener 端口，随后 `LocalBye`/`RemoteBye` 与 `probe 退出 OK`；同一进程新连接在 cert-B-only trust 下验证成功、在 old cert-A-only trust 下验证失败。

## 证据边界（保持）

- TLS self-test 在 `--tls` 且非 `--external` 的自测模式下，只显式信任 `--cert` 指向的本地自签证书。
- 上述 TLS S2/S3/S4 结果仅覆盖 `--tls` 非 `--external` 本机 loopback smoke，不是 external 对接结果。
- S4 证据为 `CANCEL`、`487` 与 `RemoteCancel`/`LocalCancel` 回调路径；ACK 线包未独立抓取。
- 上述 external 证据仅证明一次 external raw SIP INVITE over TLS（收到 100/180/200），外部客户端未发送 ACK/BYE，不是完整 dialog。
- pre-Contact-fix（Contact 指向 UDP listener）的 active-call A/B reload 记录已 superseded，不计入 full TLS in-flight active-call 证据。
- 上述结果不证明 operator PKI trust、mTLS/peer identity enforcement、生产平台 transport adapter/runtime binding、外部 S-SBC 连接或证书热轮换。
- 上述结果不证明 mTLS peer allowlisting、证书热轮换期间 active-call preservation，且不构成 REQ-S-2/REQ-S-3 acceptance。
- REQ-S-2/REQ-S-3 仍未验收；M2 仍为 OPEN。

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
- ✅ 消息顺序与响应符合协议预期（S1: INVITE→100→180→200→ACK→BYE→200；S4: INVITE→100→180→CANCEL→487，ACK 为协议预期但本 probe 未独立抓包确认）
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
