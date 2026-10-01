# D10 Recovery Probe

这是一个仅供 `testbed/` 使用的可复现实验，不是产品实现，也不构成 D10 验收。

## 运行

需要 Bash、C++17 编译器、Python 3.10、仓库虚拟环境中的 `redis` 包、Docker，以及可用的 reSIProcate 1.14.0 头文件和共享库。默认路径为：

- `RESIP_HOME=/tmp/as-resiprocate-userbuild/resiprocate-1.14.0`
- `RESIP_BUILD=/tmp/as-resiprocate-userbuild/upstream-minimal-20260930`

可通过环境变量覆盖路径及 `PYTHON` / `CXX`，然后运行：

```sh
bash testbed/simulators/resip-probe/d10-recovery/run.sh
```

Runner 为 Redis 和三个 SIP UDP 端点选择并预检不同的 loopback 动态端口。Redis 容器只发布到 `127.0.0.1`，名称和所有者标签由本次运行随机生成；结束时仅删除本次 runner 创建且 ID、名称、所有者标签均匹配的容器。所有编译、日志、临时字段文件和 Redis 容器 ID 均留在新建的唯一 `/tmp/as-d10-recovery.*` 目录中。

## 流程

1. 原生 phase A 用真实 loopback UDP 消息经 DUM 建立 UAS 对话，再由同一个 `SipStack` 和 DUM 创建 UAC `ClientInviteSession`。假的下游 peer 作为原始 UDP 服务端接收 DUM 的 INVITE、返回带 SDP answer 的 200；DUM 处理 200 并自动发送 ACK 后，phase A 才写出供 Python 读取的源字段并退出。
2. Python 将两条腿映射到当前 `DialogLegCheckpoint` / `CallStateCheckpoint` 类型，通过 `CallStateCheckpointRepository` 和真实 `RedisStateStore` 保存、加载和验证 Redis 值。它不自行序列化后写入 Redis，也不在 SIP 回调中执行 Redis 操作。
3. Phase A 退出后，独立的 phase B 创建全新的 `SipStack` 和 DUM，并在 DUM 前注册 Recovery TU。与已加载 UAS Call-ID、From-tag、To-tag 都匹配的 BYE 才会被接管，并按下游 checkpoint 的目标、对话标识和正 CSeq 转发。
4. 假 peer 回送 UDP 200。phase B 在向上游排队 200 之前停在文件门闩；Python 在进程仍运行时再次通过 repository 加载 Redis checkpoint、核对类型值和 TTL，再释放门闩。
5. 同一个新 DUM 收到未知 BYE：Recovery TU 不匹配，DUM 返回 481；probe 确认该 BYE 未发往下游。

Runner 输出关键命令、各进程 PID 与退出状态，最后输出 `D10_FINAL_RESULT=PASS` 或 `FAIL`。PASS 仅表示此窄范围实验和运行断言通过。

## 边界

此 probe 仅观察“已建立的两条对话 + 新到达 BYE”的 loopback 行为；本 fixture 的两条 `route_set` 都为空，不验证非空路由集。reSIProcate 在 phase A 退出时报告剩余 server transaction，在 phase B 退出时报告剩余 client/server transaction；本实验不评估 graceful transaction drain。它不是产品 native/Python adapter，不解决 ADR-0022 中未定的产品 API，也不代表 D10 接受、发布或验收。它不恢复旧 DUM 会话或进行中的 INVITE/CANCEL 事务，不证明 RTP/媒体、分叉、竞态、ISSU、fencing、active-active、Redis 故障切换或 RPO。