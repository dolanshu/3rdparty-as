# 文档导航（Documentation map）

按读者角色阅读。全部是纯文本 —— Mermaid 或 ASCII 图，绝不放无法 diff 的渲染图片。

## 决定要做什么

| 文档 | 是什么 |
|---|---|
| [`architecture/新系统整体架构.md`](architecture/新系统整体架构.md) | **设计基线。** 每一项已确认决策、其理由、未决清单与风险登记 |
| [`architecture/adr/`](architecture/adr/) | 决策记录；先看它的 README 里的注册表 |
| [`plan.md`](plan.md) | 交付计划：里程碑、顺序、退出标准 |
| [`migration/triage.md`](migration/triage.md) | 在采纳任何东西之前，POC 代码如何被甄别 |

## 构建它

| 文档 | 是什么 |
|---|---|
| [`../AGENT.md`](../AGENT.md) | **写代码之前先读。** 协作守则、分层、TDD 政策、CI 门禁、git 规则 |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | 环境搭建、本地门禁、commit 与评审约定 |
| [`../README.md`](../README.md) | 定位、仓库导览、快速开始 |

## 运行它

| 文档 | 是什么 |
|---|---|
| `operations/` | 部署、runbook、排障 —— 随部署里程碑落地 |
| `acceptance/` | 逐条带证据的验收标准 —— 随首个发布里程碑落地 |

## 参考

| 文档 | 是什么 |
|---|---|
| `glossary.md` | IMS / SIP 术语表 —— 随首个代码里程碑落地 |
| `specs/` | 规范性参考（RFC 3261、RFC 4566、RFC 8688、TS 24.229）与消息样例 |
