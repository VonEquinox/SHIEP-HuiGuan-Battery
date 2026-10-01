# V2 Web 实施与验证记录

记录日期：2026-10-02（Asia/Shanghai）。本记录对应《01_实施总方案》第 11–12 节，并将已实现页面行为、接口联动和验证边界分开列明。原七个工作区仍保留；新增专业页面通过同一侧栏进入。云端 LLM 的 URL、模型和 Key 由服务器配置，前端没有凭证输入框或内置 Key。

浏览器合同测试使用确定性合成测试响应，验证页面请求和状态处理，不构成模型性能、真实设备诊断或现实减排证据。正式的数据、数值模型、Agent、排程、Carbon 实施细节分别见其他独立实施记录。

## 快速运行与验收

从仓库根目录运行以下命令。依赖通过已锁定的 `package-lock.json` 安装。若本机没有系统 Chrome，可先安装 Playwright 对应浏览器并省略 `PLAYWRIGHT_CHANNEL=chrome`。

```bash
npm --prefix battery_platform/frontend ci
npm --prefix battery_platform/frontend run build
PLAYWRIGHT_CHANNEL=chrome npm --prefix battery_platform/frontend run test:e2e:v2
```

原有真实后台回归的可复现命令：

```bash
cd battery_platform/frontend
PLAYWRIGHT_CHANNEL=chrome npx playwright test e2e/platform.spec.ts --config playwright.config.ts
PLAYWRIGHT_CHANNEL=chrome npx playwright test e2e/v2.integration.spec.ts --config playwright.config.ts
```

两份 Playwright 配置都支持 `PLAYWRIGHT_CHANNEL`。V2 合同测试仅启动 127.0.0.1:8794 的 Vite；原有回归和新增V2真实联通测试通过 `browser_server.sh` 建立独立验收数据库和 127.0.0.1:8791 后台，测试运行结束自动停止服务器。V2真实联通测试不拦截API，使用安全包和匹配既有物理映射的XJTU开发源对象；该隔离服务器清空云端Key，因此诊断明确显示实际 `rule_baseline`。验收不会写入默认生产数据库或提交真实物理控制。

## 按页面使用

| 页面 | 已实施行为 | 请求与版本联动 |
|---|---|---|
| `/` | 原有总览后增加未确认提案、待测轮次、失败作业、未支持头；三类来源分别计数；Carbon 独立入口 | `GET /api/v2/overview`；卡片进入对应列表 |
| `/data` | 来源/许可/状态、登记物理对象和本任务有效对象分列；标签/域/split/hash可展开；来源分页；元数据校验与已登记本地数据关联两种操作明确分开 | `GET /sources?cursor&limit`，`POST /sources/{id}/ingest {mode,dataset_id?}`；异步作业有结果与失败原因 |
| `/models` | 保留原 M0 训练/评估/推理；新增 M1/M2、种子、消融与训练/校准/评测操作；展示任务支持、域指标、校准方法和样本状态 | `GET /models`；`POST /model-runs {kind,family,seed,ablation,run_id?}`；校准/评测必须选择服务端登记的运行 ID |
| `/assets`、`/assets/:id` | 保留既有资产管理；增加安装身份、多头结果、原始充电片段、截止时间与诊断入口；模型包及源物理对象回放绑定后真实执行 V2 推理 | `GET /assets/{id}/prediction-profile?cutoff`，`GET /model-packages`，`POST /assets/{id}/v2-binding {version,installation_id,package_id,row_index}`，`POST /model-runs {kind:v2_inference,asset_id}` |
| `/health` | 多头 SOH/寿命/越阈/效率/故障逐一保留；量纲与 H 不省略；unsupported不补0；分位带、登记参数密度、生存曲线按数据类型绘制 | 读当前安装与截止时间的预测；校准区间无界或域未校准时明确提示 |
| `/risk` | 按严重性筛选、勾选至少两个资产分析共享风险；展开群组、单体与数据问题；按版本和拆分依据拆组；发起诊断，不直接生成派发工单 | `GET /incidents`，`POST /incidents/analyze {asset_ids,visible_cutoff,window_minutes}`，`GET /incidents/{id}`，`POST /incidents/{id}/split {version,note,member_asset_ids}` |
| `/diagnosis/:session` | 截止时间绑定、已保存会话入口；左侧可见充电片段/事实/引用、中间候选/反证/未知、右侧授权补测；报告版本、实际执行方式、Token使用；轮次、原始反馈与本轮差异 | `POST /agent/runs`，轮询作业及 run/session；提案使用报告 ID；定点反馈指定断言路径、原文与来源 |
| `/operations` | 保留原工单接单、开始、附件、处理、独立验收、关闭；新增提案审阅/确认、排班与工具资源、约束求解、草案甘特/负载、未分配原因、可编辑分配和人工确认 | 提案审批使用 `version`；排程 `PATCH` 与 `confirm` 使用草案 `version`；接单或资源变化以409拒绝覆盖 |
| `/operations` 检查轮次 | 正式工单显示已授权 test_id、安装、当前轮、附件与原报告；测量/仪器/校准/原始自由文字/结果状态回填；失败、拒测、未测可保留未知；按具体原文跨度纠正抽取事实 | `GET /orders/{id}/inspection`，`POST /observations`，`POST /rounds/{n}/submit`，`POST /observations/{id}/facts`；工单版本与幂等提交 UUID 都传给服务器 |
| `/evolution` | Skill/Memory版本、状态、反例与来源；Context两版本差异；ACE/Reflexion/GEPA/固定/无Memory离线实验；来源分开绘图，下降/失败保留；按活动版本恢复快照 | `/skills`、`/memories`、`/context-snapshots`、`/evolution/runs`；离线实验默认dev且不激活；回滚携带base_version；没有强制专家批准进化队列 |
| `/carbon` | 独立情景、因子/价格依据、政策资格、活动台账、预测/结算/合成分类、正式/内部可复算JSON导出；管理员追加冲销 | `/carbon/factors`、`/policy-benefits`、`/scenarios`、`/ledger`、`/exports?formal=`；正式资格由服务器筛选 |
| `/carbon/scenarios/:id` | 服务边界与共同服务、Γ异步重算、冻结结果版本、名义/参数集范围、成本/碳/负减排/影子价值/现金资格分别显示；Pareto、ε与敏感性；点击数字看活动和因子分解 | `/scenarios/{id}`、`POST /solve {expected_version,gamma}`、`GET /results/{id}`；旧结果保留Γ与版本；追加台账不将预测自动改成已结算 |
| `/system` | 保留原账号/角色/通知/审计/连接；新增V2生产连接状态、Context版本和后台任务错误 | 服务器仍决定管理权限；没有普通用户开启自动审批或生产模式的控件 |

表内简写路径均以 `/api/v2` 为前缀；原有 V1 工单、账户、附件、数值计算作业接口继续保留 `/api` 路径和服务端权限。

### 原始反馈和具体断言纠正

诊断反馈表单选择 `r1.hypotheses[0]` 或具体事实路径，原文独立保存；不要求将整份报告评价为“正确/错误”。检查观察的“修正抽取事实”保留其他事实，提交准确原文片段和来源跨度。客户端只可选择 `reported`、`measurement_supported`、`contradicted`；不能自称 `independent_verified`。

定量观察没有数值时发送空 `measurements`，不会填0。`inconclusive`、`failed`、`refused`、`requires_authorization`均独立于测量阴性。仪器身份、校准状态、附件等缺项在服务端提交轮次时列出。最终验收仍在原正式工单流程由另一身份执行。

### 模型分布与实验身份

V2 回放选择的是服务器安全包和已登记开发源观察编号，不能通过浏览器指定任意模型文件或上传pickle。界面同时显示源物理电芯、split、源截止和安装身份；数值源的记录序号明确标为“非现场时间”，不会显示成安装UTC观测时间。槽位仿真身份不因回放而转为实测BMS。

分位带不是完整密度。仅登记为 `lognormal` 或 `logit_normal`、具有合法位置/尺度参数时计算其展示密度；图窗为变换域±4个尺度，尾部仍由登记参数定义。生存图只使用已有物理横轴与实际 survival 值，不对缺值补0。CQR校准区间的null上下界提示“校准样本不足或域未校准，区间无界”，不能将无界区间覆盖率1.0当作有效校准保证。

### Carbon 两种输入方式

常规表单建立明确标注的合成研究比较：共同服务量、起始状态、期末处理、确认依据、已登记电力因子、两方案用电与成本由使用者填写，并明确确认服务及安全等约束可比。它不代表实际测量或正式减排。

复杂寿命递推、材料流/回收抵扣、政策凭据和产品全生命周期边界使用完整情景规范编辑器。服务器严格检查单位、因子日期、共享不确定变量、状态概率、资格及重复计算；错误显示给使用者。页面没有“询问运维Agent”按钮或以Agent报告填碳数值的入口。

## 共享状态与权限

`src/v2.tsx` 提供列表封装、请求竞态保护、错误、证据展开、版本与作业组件。更换路径时清除旧对象，迟到响应不会覆盖新选择。已保存结果不会因刷新变成随机进度或随机曲线。

状态可显示空态、排队、运行、完成、部分、不支持、证据不足、失败、取消、中断与过期。预测和求解页显示模型/Context/安装/情景版本；排程冲突需刷新重算。错误保留 `code`、`message`、`missing_fields`、`retryable`、`request_id`；401按原逻辑结束本地登录状态。状态最终由服务端决定。

按钮依据身份限制：观察者不能训练、发起诊断、批准、派发、进化或碳写入；技术员只能处理获派工单；调度员批准提案和排程；研究员训练/评测、离线实验与碳研究；管理员管理规则和纠正台账。作业取消还核对管理员/研究员及创建者，不用客户端身份字段替代后端校验。人员技能新增 `instrumentation`，支持仪器复核授权。

`Field` 对单个输入显式提供稳定的 `aria-labelledby`，避免下拉选项被混入字段名称。专业页面在390像素宽度使用单列，不横向溢出；侧栏可滚动并保留原移动展开方式。

## 验证证据

| Evidence | 复现命令/记录 | 观察 | 支持的结论 |
|---|---|---|---|
| E-WEB-01 | `npm --prefix battery_platform/frontend run build` | TypeScript与Vite构建通过，1604模块 | 页面与合同类型可构建；不证明数据有效性 |
| E-WEB-02 | `PLAYWRIGHT_CHANNEL=chrome npm --prefix battery_platform/frontend run test:e2e:v2` | 8项通过，最终5.2秒 | 空/拒判、诊断请求、提案、反馈、Γ/负减排、结构化409、进化下降、权限、移动与排程版本交互通过 |
| E-WEB-03 | `platform.spec.ts --config playwright.config.ts` | 3项通过，15.1秒 | 真实模型推理→告警→分配→技术员附件→独立验收→重载后关闭；观察者权限；原七区桌面/移动无JS运行错误 |
| E-WEB-04 | `battery_platform/runtime/acceptance/v2-contract-screenshots/*.png` | 合同测试截图已生成并检查诊断/Carbon布局 | 专业页面三栏与负减排/Pareto显示可读；截图内合同数值属于测试夹具 |
| E-WEB-05 | `v2.integration.spec.ts --config playwright.config.ts` | 不拦截API，1项通过，最终13.8秒；资产深链200，安全包列表/绑定/真实SOH推理/诊断保存通过，JS错误及API 5xx均为空 | 实际前后台数值与诊断联通；四个缺标签头保持null，CQR无界状态和实际rule_baseline可见；不证明现场效果 |
| E-WEB-06 | `battery_platform/runtime/acceptance/v2-live-screenshots/*.png` | 真实SOH95.32%、其余头unsupported、诊断证据不足截图已检查 | 页面没有把真实数值推理或合成回放自动升级成确认故障 |

调用路径 P-WEB-01：选安装与cutoff → Agent作业 → 报告/具体断言反馈 → 人确认提案 → 数学求解草案 → 人确认排程 → 授权轮次观察 → 原独立验收。E-WEB-02验证前端请求合同与冲突处理；E-WEB-03验证原正式工单后半段真实持久化；E-WEB-05验证真实V2数值包与诊断前半段。三类证据不互相替代。

真实测试发现两处仅在正式编译部署下出现的问题并协调修复：后台从 `battery_platform` 工作目录启动时不能导入 `model_lab`，由集成人员加入受信仓库根路径；SPA `/assets/{id}` 被静态资源 `/assets` mount吞掉，由集成人员在静态mount前登记整数资产详情路由。E-WEB-05重新启动实际服务器，确认模型包API与资产深链均200且编译脚本正常加载。

截图通过合同测试生成，默认运行目录被Git忽略，避免将浏览器临时文件作为产品数据提交。原有回归截图位于 `battery_platform/runtime/acceptance/screenshots`，JSON结果位于同目录的 `browser-results.json`。

## 明确的限制

1. V2合同浏览器验收使用拦截响应，不能据此宣称完成云端模型效果、真实现场循环或现实减排验证。新增真实测试虽已确认模型包与部署路由修复、前后台联通和保存结果，隔离服务器仍使用规则基线，并诚实保留证据不足；云端API和独立算法实验另列记录。
2. 来源元数据、官方原始对象数、本任务有效标签数取自服务端实际登记记录。没有返回的字段显示未提供，未下载/未授权来源保持metadata-only或blocked；点击“更新来源元数据”不声称已下载原始文件。
3. 已验证真实XJTU开发数据目前只有可支持的SOH目标。没有真实寿命、完整效率和确认故障标签的头继续unsupported；合成诊断案例和模型数值性能不混用。
4. 对复杂因子/政策/状态递推保留规范编辑器，尚不是可视化多期建模向导；传统参数集范围/敏感性不会伪装为统计置信区间。完整产品足迹必须使用明确的全生命周期边界，常规两方案表单只覆盖活动/前瞻比较。
5. 列表支持后端游标时显示分页；Carbon和排程接口当前返回其模块的完整列表/限定列表，不自行固定伪造总数。图表只使用返回数值。正式上线、生产BMS、微信身份/真机能力和碳信用登记核证均不由Web页面证明。

## 本次独立工作记录与提交交接

| 部分 | 文件/动作 | 验证与交接 |
|---|---|---|
| Web-1 导航和公共合同 | `App.tsx`、`api.ts`、`components.tsx`、`v2.tsx`；保留七区，新专业路由，结构化错误与可访问标签 | Build通过；根Agent统一提交到DEV |
| Web-2 数据/模型/预测 | `V2Foundation.tsx`；来源作业，M1/M2配置，安全包/开发源绑定，真实V2推理，分布/拒判、源记录序号与现场时间分列 | Build与null合同通过；真实模型包API/绑定/数值输出通过；后台模型导入路径已协调修复并重验 |
| Web-3 诊断/风险/闭环 | `V2Diagnosis.tsx`、`V2Operations.tsx`、人员instrumentation；提案、断言纠正、群组、约束排程、观察与原文跨度纠正 | cutoff/提案/定点反馈、群组失败、排程409合同通过；原V1真实闭环通过 |
| Web-4 自动进化/独立Carbon | `V2Evolution.tsx`、`V2Carbon.tsx`；来源分开曲线、快照diff、离线实验/回滚、因子/规则/情景/求解/台账/导出 | 下降曲线/只读权限/Γ/负减排/活动分解合同通过 |
| Web-5 页面与验收 | `styles.css`、`playwright.v2.config.ts`、`v2.contract.spec.ts`、`v2.integration.spec.ts`、本独立文档；响应布局与合同/真实截图 | 8合同+3原用例+1真实V2用例通过；部署资产详情路由已修复并重验；测试服务器均随Playwright结束停止 |

本Agent按协调约定没有单独Git提交，避免共享工作目录并发提交混入其他模块。各部分由根Agent在DEV分批提交，完整commit与后续修复记录进入总实施日志；本记录提供每部分真实文件、操作、命令与限制，供每次提交引用。
