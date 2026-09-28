# 低层设计（LLD）— platform 内核（M2a）

- **版本**：v0.1（reviewed）
- **日期**：2026-09-28
- **状态**：reviewed — 2026-09-28 评审通过，见 docs/reviews/m2-design-review.md
- **依据 ADR**：ADR-0002 / ADR-0003 / ADR-0005 / ADR-0007 / ADR-0016 / ADR-0019 / ADR-0020
- **对应 REQ**：见 `hld.md` §8 追溯表

---

## 1. 文件清单

路径前缀：`platform/src/as_platform/`

| 路径 | 职责 | 关键公共 API（类型签名） | ADR 标注 |
|---|---|---|---|
| `shell.py` | 进程壳：加载配置、注入依赖、注册信号、就绪探针、主循环、draining | `def main(argv: Sequence[str]) -> int`、`def build_context(config: ConfigSource) -> AppContext`、`def run(ctx: AppContext) -> None` | ADR-0002、ADR-0009（skeleton，未落地） |
| `decision/__init__.py` | 决策包入口，重导出判决契约 | `DecisionRequest`、`Decision`、`Rule`、`RuleSet`、`DecisionAction`、`Leg` | ADR-0002 |
| `decision/rules.py` | 规则集合：归一化、最长前缀匹配、候选集构造 | `def normalize_number(raw: str) -> str`、`def match_candidates(rules: RuleSet, number: str) -> tuple[Rule, ...]`、`def select_winner(candidates: tuple[Rule, ...]) -> Rule \| None` | ADR-0002、REQ-F-6 / F-7 |
| `decision/decide.py` | 判决纯函数 | `def decide(request: DecisionRequest, rules: RuleSet) -> Decision` | ADR-0002、AGENT.md §5 |
| `state/store.py` | `StateStore` Protocol 与键命名空间构造 | `class StateStore(Protocol)`、`def build_key(case: str, kind: str, id: str) -> str` | ADR-0002、ADR-0007 |
| `state/in_memory.py` | 测试与本地开发实现 | `class InMemoryStateStore`（实现 `StateStore`） | ADR-0002 |
| `state/redis_store.py` | 生产实现（Redis + Sentinel） | `class RedisStateStore`（实现 `StateStore`） | ADR-0007、ADR-0002 |
| `gating/__init__.py` | feature 门控：判定入口与 `ToggleSource`（两层来源） | `class ToggleSource(Protocol)`、`class StaticToggleSource`、`def is_enabled(name: str, scope: ToggleScope, source: ToggleSource) -> bool` | ADR-0020 |
| `telemetry/__init__.py` | 遥测：有界队列、后台导出、空实现 | `class TelemetrySink(Protocol)`、`class BoundedQueueSink`、`class BackgroundExporter`、`class NoOpSink` | ADR-0005 |
| `api/contract.py` | 内核对用例进程暴露的内部 API 契约（数据结构 + 回调协议） | `DecisionRequest`、`Decision`、`CallState`、`AppContext`、`def handle_request(ctx: AppContext, request: DecisionRequest) -> Decision` | ADR-0002 |
| `sip/transport.py` | 对端白名单与 TLS 配置热轮换 seam | `class PeerIdentity`、`class PeerPolicy`、`class TlsConfig`、`class TransportSeam`、`def authorize_peer(peer, policy) -> bool` | ADR-0016 |
| `sip/adapter.py` | SIP 边界 seam（仅 Protocol，不含栈实现） | `class SipAdapter(Protocol)`、`def to_decision_request(view, received_at) -> DecisionRequest`、`def decision_to_status_code(action) -> int` | ADR-0016、ADR-0019 |

**命名约束**：`src/` 下禁止出现 `util`、`helper`、`misc`、`common`、`tools` 一类模块名（AGENT.md §5）。上表十二个模块名均为领域名。

---

## 2. 数据结构

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Leg(str, Enum):
    """呼叫的哪一条腿产生了本次请求。"""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class DecisionAction(str, Enum):
    """判决动作。取值与 hld.md §5 步骤 4 的四个分支一一对应。"""

    FORWARD = "forward"
    TRANSLATE = "translate"
    DECLINE = "decline"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class DecisionRequest:
    """内核看到的请求。不含任何 SIP 概念（无 header、无 dialog、无事务）。"""

    call_id: str
    calling_number: str
    called_number: str
    method: str
    leg: Leg
    received_at: float  # 由调用方注入，函数内部绝不取时钟。See ADR-0002


@dataclass(frozen=True)
class Decision:
    """decide() 的唯一产出。"""

    action: DecisionAction
    target: str | None
    reason_code: str
    matched_rule_id: str | None


@dataclass(frozen=True)
class Rule:
    rule_id: str
    prefix: str
    action: DecisionAction
    priority: int


@dataclass(frozen=True)
class RuleSet:
    version: str
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class CallState:
    call_id: str
    leg_state: str
    created_at: float  # 同 DecisionRequest.received_at，由调用方注入
    ttl: int  # 运行态键必须带 TTL。See ADR-0007


@dataclass(frozen=True)
class ToggleScope:
    """门控判定范围。ADR-0020 层 ② 的粒度载体。"""

    case: str
    number_range: str | None = None
    call_id: str | None = None
```

### frozen / slots 取舍

- **采用 `@dataclass(frozen=True)`。** 判决路径上的对象一旦可变，纯函数性质与幂等性都无法陈述 —— 不可变是 §3「同输入必同输出」的数据层保证，也让 `RuleSet` 可以安全地在测试间共享而不被意外改写。
- **暂不启用 `slots=True`。** Python 3.10 起可用，但 `slots=True` 会重新构造类，对子类化与序列化（判决对象后续可能要跨进程 / 跨语言边界传递）引入额外摩擦，而判决对象生命周期极短，内存收益不抵这份摩擦。若 M6 容量评估认为对象分配成为热点，再单独裁决启用。
- 所有公共函数与数据结构都有完整类型标注，**`mypy` strict 必须干净**。

---

## 3. `decide()` 算法

```
def decide(request: DecisionRequest, rules: RuleSet) -> Decision:
    # ① 归一化号码：E.164，保留 '+' 前缀；去分隔符与非号码字符
    called = normalize_number(request.called_number)
    calling = normalize_number(request.calling_number)

    # ② 最长前缀匹配：构造候选集（默认匹配对象为被叫号码，REQ-F-6/F-7）
    candidates = match_candidates(rules, called)   # 按 prefix 长度降序

    if not candidates:
        # ④ 无匹配 → NOT_FOUND（404，REQ-F-6）
        return Decision(action=NOT_FOUND, target=None,
                        reason_code="no_rule_matched", matched_rule_id=None)

    # ③ 冲突裁决：block 优先于 translate（与 test-plan REQ-F-7 验收一致）
    winner = select_winner(candidates)            # 最长前缀优先；同长则 priority 高者优先；
                                                  # 跨长度冲突时 block(DECLINE) 压过 TRANSLATE

    # ⑤ 命中 block → DECLINE（603，REQ-F-7）
    if winner.action is DECLINE:
        return Decision(action=DECLINE, target=None,
                        reason_code="blocked", matched_rule_id=winner.rule_id)

    if winner.action is TRANSLATE:
        return Decision(action=TRANSLATE, target=translate(called, winner),
                        reason_code="translated", matched_rule_id=winner.rule_id)

    return Decision(action=FORWARD, target=called,
                    reason_code="forwarded", matched_rule_id=winner.rule_id)
```

**性质（必须成立，也是测试断言的对象）：**

- **纯函数**：无 socket、无时钟、无全局状态（AGENT.md §5）。`received_at` 是入参，不是内部读取。
- **无 IO**：不读配置、不写状态、不发遥测 —— 状态写入与遥测由调用方在拿到 `Decision` 之后做（hld.md §5 步骤 5 / 6）。
- **幂等**：同输入必同输出；重复求值不产生副作用，因此重复执行不改变结果（未决 D3 的前提）。

---

## 4. StateStore

### 4.1 Protocol

```python
class StateStore(Protocol):
    def get(self, key: str) -> bytes | None: ...
    def set(self, key: str, value: bytes, ttl_seconds: int) -> None: ...
    def delete(self, key: str) -> None: ...
    def expire(self, key: str, ttl_seconds: int) -> None: ...
```

语义要求：

- `set` 与 `delete` **幂等**：同一 key 重复 `set` 同一 value 结果一致；删除不存在的 key 不报错。
- `get` 未命中返回 `None`，不抛异常。
- 键由 `build_key(case, kind, entity_id)` 统一构造，命名空间 `as:{case}:{kind}:{entity_id}`（ADR-0007）。**参数名避用 `id`** —— `id` 是内置名，用作参数会触发 `ruff` A002，故取 `entity_id`。

### 4.2 `InMemoryStateStore`

- 用途：测试与本地开发。
- **TTL 判定用注入的到期时间戳 / 单调时钟，不在实现内部读系统时钟。** 这样 TTL 行为可被确定性测试（注入时间即可断言过期），与 §3 的纯函数纪律同源。
- 不引入线程锁假设之外的并发语义；并发语义由契约测试定义。

### 4.3 `RedisStateStore`

- 生产实现（Redis + Sentinel）。
- 键命名空间 `as:{case}:{kind}:{id}`，运行态键**必须带 TTL**。
- 写入**幂等**：同一 key 重复写入同一 value 结果一致（承受脑裂窗口，风险 R5 / 未决 D3）。
- 连接参数（地址、Sentinel 集合、超时）由配置注入，不在代码里写死。
- `redis` 依赖声明在 `platform/pyproject.toml`；根 `pyproject.toml` 已为 `redis` 预留 mypy override。

### 4.4 契约测试

同一套契约用例（`marker = contract`）对两个实现**重放**：键构造、TTL 过期、幂等写入、未命中返回、删除不存在键、二进制安全。任何实现差异都是缺陷，不是"实现特性"。

---

## 5. 门控（gating）

```python
class ToggleSource(Protocol):
    """分层门控必须能区分两层来源，因此是两个方法而不是一个。"""

    def deployment_value(self, name: str) -> bool | None: ...  # 层 ①
    def runtime_override(self, name: str, scope: ToggleScope) -> bool | None: ...  # 层 ②


@dataclass(frozen=True)
class StaticToggleSource:
    """测试与默认实现：未登记的开关一律返回 None（→ 关）。"""

    deployment: Mapping[str, bool] = field(default_factory=dict)
    overrides: Mapping[tuple[str, str], bool] = field(default_factory=dict)

    def deployment_value(self, name: str) -> bool | None:
        return self.deployment.get(name)

    def runtime_override(self, name: str, scope: ToggleScope) -> bool | None:
        return self.overrides.get((name, scope.scope_key()))


def is_enabled(name: str, scope: ToggleScope, source: ToggleSource) -> bool:
    override = source.runtime_override(name, scope)
    if override is not None:
        return override  # 层 ② 压过层 ①。See ADR-0020
    deployment_value = source.deployment_value(name)
    if deployment_value is not None:
        return deployment_value
    return False  # fail-closed：未注册的开关是关。See ADR-0020
```

规则：

- **两层来源分列。** `ToggleSource` 用 `deployment_value(name)`（层 ①，部署级总开关）与 `runtime_override(name, scope)`（层 ②，运行态细粒度覆盖）两个方法，而不是单一 `value()` —— 单一方法无法表达"层 ② 覆盖层 ①"的语义，也无法表达两层的不同失效含义。判定顺序固定为层 ② 优先、层 ① 兜底。
- **默认关。** 未注册的开关名 → 关（**fail-closed**）。这是 ADR-0020 的硬要求，也是"开关债务不变成放行漏洞"的保证。
- **纯函数。** `is_enabled` 不读 Redis、不读时钟、不读全局；值全部来自注入的 `ToggleSource`。测试注入 `StaticToggleSource` 即可覆盖开 / 关两态，不需要任何外部依赖。
- **判定幂等。** 同一 `scope` 重复求值结果一致 —— 脑裂窗口内不得出现翻转。由 `ToggleSource` 实现保证（层 ② 覆盖值最终一致），并由契约测试断言。
- 层 ①（部署级总开关，PG 版本库热加载）在 M4 落地；M2 只定义契约，`StaticToggleSource` 是默认实现。

---

## 6. 遥测（telemetry）

```python
class TelemetrySink(Protocol):
    def emit(self, event: TelemetryEvent) -> None: ...


@dataclass(frozen=True)
class BoundedQueueSink:
    """呼叫路径唯一允许触碰的 sink：入队即返回。"""

    queue: BoundedQueue

    @property
    def dropped_count(self) -> int: ...  # 队列满而丢弃的事件数
    @property
    def export_failure_count(self) -> int: ...  # 导出失败次数

    def emit(self, event: TelemetryEvent) -> None:
        if not self.queue.try_put(event):
            self._dropped += 1  # 丢弃是设计选择，不是异常 See ADR-0005
```

规则：

- 呼叫路径只调用 `emit(event)` → 写入**有界队列**。队列满则**丢弃**新事件并让 `dropped_count` 计数自增（导出失败另计 `export_failure_count`）。遥测丢失可接受，反压呼叫路径不可接受（ADR-0005）。
- `BackgroundExporter` 在**独立线程**消费队列并批量导出。后端中立：代码只依赖 OTel API 与配置，换后端是配置变更不是代码变更。
- `NoOpSink` 是**默认**实现 —— 未配置遥测时零开销，也让测试无需任何后端。
- **绝不在呼叫路径做网络 IO。** 阻塞事件循环里做一次网络写，等于把后端抖动直接加进呼叫建立时延（ADR-0005、AGENT.md §5）。
- 载荷日志默认关闭、可开关；开启时同样走有界队列，不回写到呼叫路径。

---

## 7. 进程壳（shell）

启动顺序：

1. **加载配置** —— 经注入的 `ConfigSource` 读取（配置热更新走同一个 seam，证书热轮换复用它，ADR-0016）。
2. **注入依赖** —— 构造 `StateStore`（`RedisStateStore` 或 `InMemoryStateStore`）、`TelemetrySink`（默认 `NoOpSink`）、`ToggleSource`（默认 `StaticToggleSource`），组装 `AppContext`。
3. **注册 `SIGTERM` / `SIGINT`** —— 触发 draining。
4. **就绪探针** —— 依赖装配完成且可服务后标记 ready。
5. **主循环** —— **M2a 不含 SIP 循环**；SIP 事件循环属 M2b 适配层。

draining（ADR-0009，skeleton，未落地）：

```
收到 SIGTERM
  → 停止接收新请求（摘流）
  → 等 active_calls 归零，或超过 grace window
  → 退出
```

因为进程内无状态（ADR-0002），draining 不需要状态迁移；grace window 与强制释放策略由呼叫时长硬顶定义，作为部署侧参数注入。

---

## 8. 错误策略

| 场景 | 处置 |
|---|---|
| 入口校验失败（对端不在白名单） | **丢弃** + 记一条**安全事件**（不是普通日志）。ADR-0016 / REQ-S-1 |
| 判决异常 | **fail-closed**：按配置返回 404（默认）或 603。**默认 404 不得放行** —— 拿不到判决时，"我不知道这个号段"比"我允许它过去"安全 |
| 状态写入失败 | 记遥测，按策略终止呼叫；不静默继续 |
| 任何异常 | **不得冒泡到 SIP 回调。** 在适配层边界捕获、记遥测、转成 fail-closed 判决。SIP 回调里抛异常意味着状态机停在未知位置 |

---

## 9. 测试策略

| 层 | 覆盖对象 | 断言要点 | marker |
|---|---|---|---|
| unit | `decide()` 与 `rules`（归一化、最长前缀、冲突裁决、无匹配 / DECLINE 分支） | 同输入同输出；block 压过 translate；无匹配 → `NOT_FOUND`；无时钟 / 无 IO（注入 `received_at` 即可断言） | `unit` |
| unit | 门控 `is_enabled` | **开 / 关两态都要覆盖**；未注册开关名 → 关（fail-closed）；同 scope 重复求值一致 | `unit` |
| unit | 遥测 `BoundedQueueSink` | 入队不阻塞；队列满 → 丢弃且 `dropped_count` 自增；`NoOpSink` 零副作用 | `unit` |
| unit | `InMemoryStateStore` TTL 与幂等 | 注入时钟可确定性断言过期；重复 `set` / 删除不存在键不报错 | `unit` |
| contract | `StateStore` 契约 | **同一套用例对 `InMemory` 与 `Redis` 两个实现重放**：键构造、TTL、幂等、未命中、二进制安全 | `contract` |
| contract | `api/contract.py` 内部 API 契约 | 用例进程视角的请求 / 判决契约，跨实现一致 | `contract` |
| integration | 进程壳启动 / draining、遥测后台导出 | 真实信号 → 摘流 → active_calls 归零 → 退出；导出线程与呼叫路径隔离 | `integration` |

**强制 TDD**：`decide()` 与规则匹配走**红 - 绿 - 重构**（AGENT.md §6）。这两处纯函数是 TDD 回报最高的地方，不允许先写实现再补测试。

---

## 10. 代码标注约定

- 不显而易见的代码行末标 `# See ADR-00NN`（AGENT.md §5、REQ-G-3）。审稿人必须能从代码一步走到理由。
- 所有公共函数必须有完整类型标注；`mypy` **strict** 必须干净。
- `ruff` 必须干净：google docstring 约定、`line-length = 100`。
- 标识符、注释、日志、错误字符串用英文；面向人的文档用中文（AGENT.md §5）。
- 禁止 `util` / `helper` / `misc` / `common` / `tools` 模块名（AGENT.md §5）。
