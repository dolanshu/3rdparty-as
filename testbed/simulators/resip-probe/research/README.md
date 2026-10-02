# reSIProcate D9/D10 探索性证据索引

本目录归档来自 `/tmp` 的 D9/D10 探索性探针源码、运行脚本、结果记录，以及经筛选的 SIP 原始报文。它们用于保留实验事实和边界，**不是已接受的产品实现、验收证据或架构决策**。这些实验均不改变 ADR-0019，也不表示 D10 已通过；D10 仍未解决。

除单独注明外，DUM 探针使用 reSIProcate 1.14.0 和 CPython 3.10.21。D10 UAC 进程重启及 fresh-UAS 结果记录明确给出的 reSIProcate 源码 commit 为 `632e215c2ca9aee5416bfe1808851ea6fa380044`。D9 结果记录未逐项标明该 commit，不应据此推定每个 D9 构建都固定在此提交。纯 Python/native bridge 探针只验证 CPython 回调桥，不绑定或验证 reSIProcate DUM。

运行记录包含此机器上的 `/home/shudong/...`、`/tmp/as-resiprocate-userbuild/...`、uv Python/include/library 路径、编译器路径和端口等环境细节。归档没有复制 reSIProcate 依赖/构建树，runner 也可能引用这些机器专属路径；不能将它们视为可移植或可直接重跑的独立包。

## D9 探针

- [`d9-python-bridge/`](d9-python-bridge/)：来源 `/tmp/as-resip-python-bridge-spike/`，包括 `bridge.cpp`、`harness.py`、`run.sh` 和 `results.md`。同线程及单个 native worker 线程的回调、异常传播和引用计数检查通过；只支持 CPython/native bridge 可行性，不证明 DUM 绑定或 DUM handle 线程亲和性。
- [`d9-dum-python/`](d9-dum-python/)：来源 `/tmp/as-resip-dum-python-slice/`，包括 `dum_module.cxx`、`run_integration.py`、`build.sh`、`validate.sh` 和 `RESULTS.md`。真实 UDP INVITE 经 DUM/Python 决策后返回 404；故意触发的回调异常映射为 500。它不是产品 adapter、完整 B2BUA 或已批准的桥接设计。
- [`d9-two-leg-486/`](d9-two-leg-486/)：源码、runner 和结果来自 `/tmp/as-resip-dum-two-leg-spike/`；`wire/` 仅保留该来源中的 `.sip` 报文。实验覆盖一条无 SDP 的 two-leg 486 失败路径：下游 UAC failure 映射到原始上游 UAS 呼叫。它不证明完整 B2BUA、SDP 保真、CANCEL、并发或恢复行为。
- [`d9-early-cancel/`](d9-early-cancel/)：源码和 runner 来自 `/tmp/as-resip-dum-final-probes/`；另保留指定的 `logs/probe-b-final-isolated.log`、`inputs/probe-b-upstream-invite.sip` 和 `wire/probe-b-*.sip`。证据仅覆盖一个 early-CANCEL 分支：上游在下游收到 180 后取消，DUM 向下游发 CANCEL，INVITE/上游最终得到 487，并记录相关 ACK。**这是一个分支，不是完整 CANCEL 状态机或完整呼叫流程验证。** Probe A 和 D11 产物未归档。

## D10 探针

- [`d10-uac-process-restart/`](d10-uac-process-restart/)：来源 `/tmp/as-resip-dum-process-restart/`，保留 `dum_phase_child.cxx`、`process_restart.py`、`run.sh` 和 `RESULTS.md`。两个不同进程分别完成 UAC 初始 INVITE 与使用 `DialogSetId` 构造的 CSeq 2 re-INVITE。应用显式重建 To-tag、Route、目标和 CSeq；这是新进程中的 dialog/request recreation，**不是原 DUM live session、transaction 或状态的恢复**。
- [`d10-uac-two-leg-restart/`](d10-uac-two-leg-restart/)：来源 `/tmp/as-resip-two-leg-restart-recovery/`，保留指定的 C++/Python 源码、runner 和 `RESULTS.md`；没有复制 `runs/` 历史目录。两个 UAC leg 在新进程中分别重建并完成 re-INVITE/ACK，属于 UAC `DialogSetId` 重建探针。**这个 two-leg UAC 探针不建立 UAS 恢复能力，也不证明全局 REQ-NF-1。**
- [`d10-uas-fresh-dum-481/`](d10-uas-fresh-dum-481/)：来源 `/tmp/as-resip-dum-uas-restart/`，保留指定源码、runner、`RESULTS.md`、`wire-events.jsonl` 和 `messages/` 下的 `.sip` 报文。未向 fresh DUM 提供或注入 Phase A 的状态；对先前 UAS dialog 的 in-dialog BYE，fresh DUM 实际返回 481。它只记录默认 fresh-DUM 行为，不证明自定义恢复不可能，也不是 REQ-NF-1 验收。

canonical、可重复运行的 Redis D10 探针仍是现有 [`../d10-recovery/`](../d10-recovery/)，本目录不复制它。

## 归档边界

只保留上述指定的原始源码、脚本、结果文件和 SIP 报文。未复制编译扩展或可执行文件、`.o` 文件、`build/`、`tmp/`、`__pycache__/`、uv cache、Redis 容器状态/ID、无关日志、重复的 `/tmp/as-d10-recovery.*` 运行目录，或大型 `/tmp/as-resiprocate-userbuild` 依赖/构建树。没有预期的指定源码或 capture 缺失。