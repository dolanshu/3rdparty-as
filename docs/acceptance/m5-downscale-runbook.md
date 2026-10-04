# M5 缩容与 draining 运维 runbook

> 判据实现：`platform/src/as_platform/ops/downscale_guard.py`（ADR-0010）  
> 执行语义：ISSU = draining（ADR-0009）  
> 计划：`docs/plan.md` §4.4.4 M5-2d / M5-3b

## 1. 前置

- 每 Pod 可查询 **`as_active_calls`**（`GET :8080/metrics` 或遥测导出）。
- `AS_DOWNSCALE_GUARD_ENABLED` / `AS_DOWNSCALE_GUARD_PROTECT_ABOVE` 由 Helm ConfigMap 注入（默认 enable + 阈值 0）。
- HPA **可不启用**（O1/M6 前无阈值）；缩容可为手工或集群 autoscaler 提议副本数。

## 2. 输入：`plan_scale_down`

对每个实例收集：

| 字段 | 来源 |
|------|------|
| `instance_id` | `POD_NAME` / `pod` 标签 |
| `active_calls` | Prometheus `as_active_calls{pod="..."}` 或 `/metrics` |
| `draining` | 已对 Pod 执行 cordon + 删除流程且 readiness 已为 503 |

调用：

```python
from as_platform.ops.downscale_guard import InstanceLoad, plan_scale_down

plan = plan_scale_down(
    (
        InstanceLoad("as-translation-abc", active_calls=0, draining=False),
        InstanceLoad("as-translation-def", active_calls=3, draining=False),
    ),
    desired_replicas=1,
    protect_above=0,  # 与 AS_DOWNSCALE_GUARD_PROTECT_ABOVE 一致
)
```

- `plan.allowed` 为 `False`：无足够零呼叫实例可删 → **不要删 Pod**，或先对高负载实例发起 draining。
- `plan.candidates`：可先删的实例 ID 列表（仍须走 draining，不得 SIGKILL）。

## 3. 推荐顺序（手工缩容）

1. **计算** `plan_scale_down`（或运维脚本包装）。
2. 对 **removable** 中每个 Pod：`kubectl delete pod` 前确认 `active_calls==0`；Kubernetes 删除会触发 `preStop sleep` + SIGTERM。
3. 对 **仍承载呼叫** 的 Pod：不删除；等待自然结束，或业务层结束呼叫；readiness 在 `request_terminate` 后为 **503**，Endpoint 应摘流。
4. 若 `blocked`：仅缩减 `removable` 子集，或等待。

## 4. M5 测试挂钩

- 设置 `AS_M5_SIMULATED_ACTIVE_CALLS=N`（仅测试/证据）：模拟 N 路在途；SIGTERM 后每秒减 1，用于 kind 证据脚本验证 draining 与判据。

## 5. 证据路径

- **§217①② + H10**：`bash deploy/kind/m5-issu-scale-evidence.sh`（或 `make m5-issu-scale-evidence`）→ `artifacts/m5/<date>/issu-scale-evidence.log`
- 全量 bundle：`deploy/kind/m5-cluster-evidence.sh`（含 rollout + ISSU/scale）
- 集群实验日志：`artifacts/m5/<date>/cluster-evidence.log`
