# SIP 栈选型探针（ADR-0019）

本目录存放 ADR-0019（SIP 栈选型）的 **probe harness**，用来把两个"纸面判断"变成可执行的证据：

| 探针 | 对应维度 | 对应场景 | 验证什么 |
|---|---|---|---|
| `e1_baseline_probe.py` | E1 行为等价（门槛项） | S1–S11 | 在**真实 socket** 上把 M1 基线（`testbed/contracts/sip-baseline/`）的消息发给"被测栈扮演的 AS"，逐条比对它发出的消息 |
| `tls_hot_rotation_probe.py` | E4 TLS 与证书热轮换（硬约束 H4） | S12 | 证书轮换时进程不重启、在途呼叫不中断（`BYE → 200`） |

> **当前状态：两个探针都未执行。** 本环境没有 reSIProcate 的 Python 绑定（构建选项 `BUILD_PYTHON=ON` 未构建）。
> 两个探针在绑定缺失时**以退出码 2 响亮失败并打印构建指引，不会静默 skip**。
> 因此 E1 与 E4 在 ADR-0019 中**仍是开放的接受缺口**；E5（状态外置）的探针尚未编写，列为后续项。

---

## 目录结构

```
testbed/probe/
├── __init__.py                  # 包说明 + 绑定缺失时的指引文本与退出码常量
├── sequence_compare.py          # 纯函数：两条 SIP 消息序列的比对（无 IO / 无时钟 / 无全局状态）
├── e1_baseline_probe.py         # E1 基线对拍探针（可执行）
├── tls_hot_rotation_probe.py    # E4 / S12 TLS 热轮换探针（可执行）
├── tests/
│   └── test_sequence_compare.py # 比对逻辑的 unit 测试（marker: unit）
├── out/                         # 运行产物（证据），按需生成，不入版本库
└── README.md                    # 本文件
```

## 比对什么、不比对什么

`sequence_compare.py` 是唯一判定"是否等价"的地方，它只比较 ADR-0019 §5 所说的**外部可观测消息行为**：

- 方法（`INVITE` / `ACK` / `BYE` / `CANCEL` …）或响应码（`100` / `180` / `200` / `404` / `603` …）
- `Call-ID`
- Request-URI 的 `host:port`（仅请求；响应没有 Request-URI，因此不产生约束）
- body **逐字节**（REQ-F-4：SDP 穿过 AS 不变）

**不比较**：头域顺序、`Via` branch 的具体取值、SDP `o=` 时间戳。

差异描述是具体的：第几条、哪个字段、实际值 vs 期望值；body 差异会指出第一个不同的字节偏移。
比对器复用内核的 `as_platform.sip.message` 解析器，避免出现"探针和内核对 body 边界的理解不一致"这种自说自话的错误。

---

## 如何运行

### E1 基线对拍

```bash
uv run python testbed/probe/e1_baseline_probe.py
```

常用参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--scenario` | `S1 S2 S3 S4` | 要重放的场景，可重复传；默认只跑**有消息文件**的四个场景 |
| `--bindings-module` | `resip` | 被测栈的 Python 绑定模块名 |
| `--out-dir` | `testbed/probe/out` | 证据输出目录（捕获到的原始消息按场景分目录落盘） |
| `--host` | `127.0.0.1` | 被测 AS 监听的地址 |
| `--port` | `5060` | 被测 AS 监听的端口 |

端口与输出目录**都是可配置的**，没有硬编码：换环境只需改命令行。

```bash
# 只跑一个场景，指定 AS 地址与证据目录
uv run python testbed/probe/e1_baseline_probe.py \
    --scenario S1 --host 127.0.0.1 --port 45060 --out-dir /tmp/probe-out

# 场景没有基线时的行为（S5–S11 目前只有 README，没有消息文件）
uv run python testbed/probe/e1_baseline_probe.py --scenario S5
```

### E4 / S12 TLS 热轮换

```bash
uv run python testbed/probe/tls_hot_rotation_probe.py
```

常用参数：`--bindings-module`（默认 `resip`）、`--host`（默认 `127.0.0.1`）、`--port`（默认 `5061`）、
`--cert` / `--key`（默认 `testbed/probe/out/tls/cert.pem` 与 `key.pem`）。

它按 S12 的四条断言逐条报告：呼叫在 TLS 上建立并保持 in-dialog → 呼叫在途时轮换证书 →
在途呼叫仍能完成（`BYE` 收到 2xx）→ 进程未重启（栈对象标识前后一致）。

---

## 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 全部场景（E1）/ 全部断言（E4）通过 |
| 1 | E1：至少一个场景 FAIL；E4：至少一条断言 FAIL |
| **2** | **被测栈的 Python 绑定缺失（或没有可用的栈句柄工厂）—— 探针没有运行，不是通过** |
| 4 | E1：没有场景 FAIL，但至少一个场景没有基线可比（`NO_BASELINE`）。这是**警告位**，不是失败 |

`4` 是刻意设计的：S5–S11 目前只有 README、没有消息文件，它们既不能被算作通过，也不该让整轮探针失败。
默认只跑 S1–S4，所以默认运行不会出现 `4`。

---

## 绑定缺失时的预期行为（**不是 skip**）

两个探针都**惰性 import** 绑定模块。import 失败时：

1. 在 stderr 打印失败原因（`No module named 'resip'` 之类）；
2. 打印构建指引：如何用 `BUILD_PYTHON=ON` 构建 reSIProcate Python 绑定、如何让它可被 import、
   如何重新运行本探针；
3. `sys.exit(2)`。

实跑证据（2026-09-30，本环境无绑定）：

```
$ uv run python testbed/probe/e1_baseline_probe.py
probe aborted: Python bindings 'resip' are not importable (No module named 'resip')
...（构建指引）...
$ echo $?
2
```

`tls_hot_rotation_probe.py` 同样返回 2。

> 之所以不用 pytest 的 `skip`：**skip 不是证据**。ADR-0019 的 K2 规定"probe 完成前适配层不开工"，
> 一个静默跳过的探针会让 K2 在没有任何证据的情况下被解除。

---

## 与被测栈的接口（Protocol）

两个探针都用极简 Protocol 描述被测栈，**本仓库不实现该适配**（没有绑定，也没有对应的 reSIProcate 代码）：

- `e1_baseline_probe.StackUnderProbe`：`send(payload: bytes) -> bytes | None`
  —— 投递一条消息，返回被测栈发出的下一条消息。事务、对话、重传都在栈内部，那正是被探测的东西。
- `tls_hot_rotation_probe.TlsStackUnderProbe`：`establish_call()` / `rotate_certificate()` /
  `hang_up()` / `process_identity()` —— 对应 S12 的四条断言。

真实接入时，由 reSIProcate 的 Python 绑定适配这两个 Protocol（可选入口：绑定模块暴露
`create_stack_under_probe(host, port)`）。**本次不实现。**

E1 探针自带一个 `_SocketPeer`：它用真实 socket 连到 `--host:--port`，按 RFC 3261 §20.14 的
`Content-Length` 分帧。也就是说，字节是真的上了线路的；缺的是"栈那一侧的适配器"，不是传输。

---

## K2 约束

ADR-0019 §7.1 K2：**probe 完成前，`platform/` 的 SIP 适配层不开工。**

本目录的探针通过之前：

- `platform/src/as_platform/sip/` 的栈绑定实现不开工；
- E1 / E4 / E5 在 ADR-0019 中保持"接受的缺口"状态；
- E5（状态外置 / 序列化）的探针尚未编写，是后续项。

在能构建 `BUILD_PYTHON=ON` 的环境跑通后，结果应回填 `docs/acceptance/report.md`，并据此更新 ADR-0019 的缺口状态。
