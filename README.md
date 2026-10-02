# 慧管电池 V2

增量保留 V1 资产、权限、告警工单与真实模型，新增概率模型研究、一个 Skill 运维 Agent、
自动上下文进化、人工确认排程与独立碳/经济决策。真实实验与合成演示分开标记。

```bash
./scripts/v2.sh install
cp .env.example .env
./scripts/v2.sh bootstrap
./scripts/v2.sh demo
./scripts/v2.sh serve
```

安装需要已安装 UV 和 Node.js；Python 3.12 依赖由 `uv.lock` 固定。外网默认使用 7897 代理。
在本机 `.env` 填入 OpenAI 兼容 API 的 URL、模型名和 Key；凭据不会上传 GitHub。
默认服务地址为 `http://127.0.0.1:8787`。

首次 `bootstrap` 交互设置管理员密码，`demo` 建立有明确演示标记的资产与测试人员。
管理员/调度员批准提案后建立正式工单，确认排程后分配；技术员提交现场观察，另一身份验收。
Memory/Skill 通过程序校验后自动生效，Carbon 在独立工作区计算。

| 内容 | 独立记录 |
| --- | --- |
| 每次 Commit 做了什么 | [实施总记录](docs/V2_IMPLEMENTATION_LOG.md) |
| main→DEV 完整功能、公式、模型选择与分数对比 | [62页图文PDF](output/pdf/HuiGuan_DEV_vs_main_20261002.pdf)、[汇编/复核记录](docs/V2_MAIN_COMPARISON_PDF_20261002.md)、[完整可搜索正文](output/pdf/source/report_content.md) |
| UV 安装、账号、API、升级与恢复 | [运行手册](docs/V2_RUNBOOK.md) |
| 合成数据、16 个 Skill、派单/碳算例 | [合成内容](docs/V2_CONTENT_IMPLEMENTATION.md)、[Skill 明细](docs/V2_SKILLS_DETAIL.md)、[数学算例](docs/V2_FIXTURES_DETAIL.md) |
| 单 Agent、ACE/GEPA 与实际云端对照 | [Agent 实现](docs/V2_AGENT_IMPLEMENTATION.md)、[冻结实验](docs/V2_AGENT_EXPERIMENT.md) |
| Web、后台与微信测试工程 | [Web](docs/V2_WEB_IMPLEMENTATION.md)、[后台](battery_platform/docs/V2_BACKEND_IMPLEMENTATION.md)、[小程序](battery_platform/docs/V2_MINIPROGRAM_IMPLEMENTATION.md) |
| 约束排程与独立碳/经济核算 | [排程](battery_platform/docs/V2_DISPATCH_IMPLEMENTATION.md)、[Carbon](battery_platform/docs/V2_CARBON_IMPLEMENTATION.md) |
| 真实多源数值模型及来源资格 | [模型研究](model_lab/docs/V2_IMPLEMENTATION.md)、[来源交付](model_lab/reports/v2/sources/DELIVERY.md) |
| XJTU+MATR 联合训练与 MLP/LSTM/LightGBM 对照 | [联合实验完整结果](battery_platform/docs/JOINT_XJTU_MATR_RESULTS_20261002.md)、[联合协议](battery_platform/docs/JOINT_XJTU_MATR_AND_BASELINES.md)、[H-M1 优化结果](battery_platform/docs/HM1_OPTIMIZATION_RESULTS_20261002.md) |
| F01–F07 修复、来源影响、新特征重训与完整回归 | [统一修复记录](docs/V2_F01_F07_REPAIR_20261002.md)、[特征与重训](battery_platform/docs/F01_CHANNEL_VALIDITY_RETRAIN_20261002.md)、[GEPA 恢复协议](battery_platform/docs/GEPA_RECOVERY.md) |
| 权限、时间可见性、取消与版本验收 | [跨模块验收](battery_platform/docs/V2_ACCEPTANCE_REVIEW.md) |
| 最终测试、重载证据、截图与提交索引 | [最终交付验收](docs/V2_DELIVERY_ACCEPTANCE.md) |

离线回归使用 `./scripts/v2.sh test`，该命令清除云端 Key。实际云端验收命令和成本见运行手册，
实验报告保留失败、无更新和性能下降；当前小样本试验没有证明自进化改善。

研究结果以实际报告为准；不支持的寿命/效率/故障头不会补造数值。微信小程序是测试工程，
真实预览仍需要微信开发者工具、可用 AppID 与实际网络条件。
