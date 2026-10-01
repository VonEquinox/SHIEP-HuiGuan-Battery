# 慧管电池 V2：Skills、合成内容与回放实施记录

本文件独立记录文档二的内容交付，同时记录其对文档一单 Agent、权限、自动 Context 更新与独立 Carbon 的接入。用户明确授权本次合成；原文“由用户负责具体合成”是附带规范的职责说明，不限制本次已经明确授权的工作。本阶段由内容负责人以及 Skill、数学 fixture 两个子 Agent 协作完成，Git 提交由总负责人统一执行，避免共享 checkout 的并发 Git 写入。

## 实际交付与来源

`content_v1/` 包含 2,400 个根情景，12 个主桶各 200。根划分为 cold_start 960、evolution 720、dev 360、sealed_test 360；evolution 分为六轮，每轮 120 个根事件，覆盖 12 桶。另含 31,200 个授权观察分支样本、33,600 条根/子样本 parentage 记录、16 个 Skill 包、64 份 Skill 示例、17 条项目知识证据、40 个派单 fixture、30 个 Carbon fixture、7 类越权/泄漏探针及 JSON Schema、SHA-256 manifest 和 S01–S12 验证报告。

所有电池情景是项目自合成的配置状态与简化量值关系；不是实际电化学模拟器验证结果，不是真实现场根因，也没有冒称重新训练过的预测模型。容量按冻结参考容量及配置比例生成，测量单位、安装身份、缺失和时间显式记录；独立测量分支用于区分物理状态差异和测量条件差异。合成量值只属于个例，不能成为通用 Skill 的现实安全阈值。合成预测使用 `configured-synthetic-head-v1` 和 `unvalidated_synthetic` 状态。

本阶段没有下载或导入 MATR、XJTU、CH-BatteryGen、BattFailScholar 的外部全文/真实数据，也没有宣称取得其许可。`approved_synthetic` 表示本项目自合成材料可用于项目合成/回放；外部许可没有借此获批。作者字段是 AI-assisted project synthesis，不是生成模型冒充人类专家。参考遵循项目规范；格式核对来源为公开 Agent Skills specification，未复制外部付费材料。

## 真实云端合成记录

通过现有 OpenAI 兼容客户端，使用用户授权的 DeepSeek 测试服务、`deepseek-flash` 与 `http://127.0.0.1:7897` 代理进行了 28 次实际 HTTP 请求，28 次通过语言结构检查：16 次各生成一个 Skill 的三条补充条件/反例；12 次各生成一个主桶的六段工程师自由文字，合计 48 条补充说明和 72 段自由反馈变体。没有重试，成功数与尝试数分别记录，不用“生成成功”掩盖失败。提供商 usage 合计 prompt 6,280、completion 39,128、total 45,408 tokens；没有取得账单，因此不推测金额。

`manifests/cloud_enrichment.json` 保存不含凭据的语言结果、目标、请求/响应 hash、usage、成功状态、model/base URL 与 `expert_review=not_performed`。API Key 仅在执行环境中读取，没有写入代码、内容包、日志或提交。云端内容提供措辞和反例补充；物理参数、根因配置、split、概率、VOI、派单和 Carbon 数学 oracle 由程序生成，不由同一 LLM 充当唯一答案和裁判。`reviewed_notes` 是兼容输入键名，并不表示专业盲审，生成的 Skill 正文明确说明尚未经过独立专家审查。

## 可见内容与隐藏答案

在线 `PublicContentStore` 只读许可通过且工具未增权的 `skills`、`knowledge` 和 `cases/cold_start.jsonl`。公开根情景不含 hidden_truth、未来 branches、反馈答案、expected_patch、评分、主桶标签或母模板 ID。资产、安装、电芯、情景和观察 ID 使用不带故障名称的稳定 hash；源定位器也使用不泄漏主桶的根 ID。Skill 示例仅从 cold_start 的当前观察生成，非冷启动、未来 available_after 和超 cutoff 记录直接拒绝。

隐藏标签位于 `oracle/labels.jsonl`，未来观察位于 `oracle/observations.jsonl`，封存输入位于 `evaluation/sealed/`，Carbon/派单 golden cases 位于 `fixtures/`。`export_public` 复制许可通过的 Skill 资源和冷启动可见资料到一个必须为空的独立目录；不复制 oracle、evolution、dev/sealed 或任何 Carbon fixture。路径穿越和指向目录外的 symlink 被解析后的目录边界拒绝。

`EvaluatorReplay` 构造时要求显式 `oracle_access=True`，不注册为 Agent 工具。它从当前状态选择合法测试；未授权、未知、尚不可达、要求新增授权却未记录批准的测试拒绝揭示。测试读取观察，默认不发生维修或容量恢复。重复调用返回原结果且 `new_evidence=False`，不能累积假独立置信度。未来工程师反馈只有对应 evidence_ids 实际被揭示后才返回。

冷启动还提供 96 个已经到达的 `visible_feedback` 例子，时间早于 cutoff，只引用初始可见测量。这些员工描述保持 reported 状态，不能自动升级为确诊。反馈 Skill 示例保留自由原文、span、引用及适用边界；将未核验意见用于确诊/增权的更新拒绝。

## 内容覆盖与数据组织

每个主桶有 20 个母模板组、每组 10 个根情景。同初始症状/不同原因的成对根留在同一组；组在合成前整体划分。物理对象、根情景、母模板、已知近重复簇不跨 split。近重复报告同时记录结构、参数/信号、文本/来源和已知生成 parentage；严格归一化后相同数值序列不跨集合。不同参数/工况的组被整组留出。宽泛的简化物理生成 recipe 在各集合共享，这一限制公开记录，未将它宣称为外部独立机制测试或穷尽的语义去重。

初始补测为 1,760/2,400（73.33%）；正常、域外或证据不足 1,000/2,400（41.67%）；冲突/未解决 640/2,400（26.67%），均达到最低覆盖要求。这些交叉标签在 oracle 统计，不作为在线答案线索。多轮分支覆盖正常返回、支持 A/B、无区分力、失败、超量程、重复上传、矛盾、工程师拒绝/无法执行和新授权。失败/无区分力/矛盾不自动确诊。

反馈保留结构化检查、自由文字、证据和原文 span。12 种具体报告错误覆盖错体系、分数当概率、相关当根因、漏反证、缺测、低价值测试、重复检查、越权工单、不存在引用、未确认意见、干预混淆、混合问题全部解除。每个样本提供错误段落、纠错、该改的内容和不可变边界；更新覆盖 ADD/REVISE/DEPRECATE/CONFLICT/NO_UPDATE。提示注入样本的正确更新是 NO_UPDATE，不引入 Memory 经理审批。

群体情景显式标模拟拓扑，包括共同采集偏置、单体问题、共同环境、共用问题夹单体问题、同批次不同时间和映射错误。`correlated_group` 与 `confirmed_common_cause` 分开，保留新证据后拆分的标签和成员状态。测试似然只有配置支持的情景才提供；程序检查归一化并以先验、似然、损失和成本计算一阶 VOI。重复噪声有关联，不将同一测量视为独立样本。

## 可重复命令

先用仓库 UV 锁文件同步环境，再运行以下命令。云端步骤仅在环境已经配置测试凭据时执行；冻结文件本身足够重建，无须再次消耗 API 额度。

```bash
uv sync --frozen
uv run python -m tools.content.synthesize --out content_v1/manifests/cloud_enrichment.json --max-calls 28 --workers 3
uv run python -m tools.content.generate --out content_v1 --cloud-enrichment content_v1/manifests/cloud_enrichment.json
uv run python -m tools.content.validate --root content_v1
uv run python -m pytest tests/content -q
```

`generate` 不依赖网络，使用保存的 cloud enrichment 即可确定性重建。`validate` 默认检查全部 hash。可将报告写到包外，例如 `--write-report /tmp/huiguan-content-validation.json`；不要直接覆盖冻结报告而不重算 manifest。生成器先检查结构和数学，建立 hash，再执行完整 hash 校验，保存 `hashes_checked=true` 的报告并再次核对最终 manifest。

公共导出示例：

```python
from tools.content.replay import PublicContentStore, EvaluatorReplay, export_public
export_public("content_v1", "/tmp/huiguan-public-content")  # 目标须为空
store = PublicContentStore("/tmp/huiguan-public-content")
store.route({"chemistry": "LFP", "symptoms": ["sensor", "time alignment"]})
store.load_skill("sensor-anomaly")
```

## 验证、修复与提交记录

已执行标准 Skill 格式校验 16/16，内容测试最终全量结果 `82 passed in 8.25s`；最终生成器返回 `validation=passed, hashes_checked=true`，冻结报告亦记录 true，S09/S10 分别明确记录 40/30。实际检查包括冻结 JSON Schema/hash、2,400 根与 split/parentage、公开部署不含隐藏文件、许可/工具增权拒绝、路径越界、未授权/未来/新授权测试、幂等重复、反馈到达门槛、同症状不同真值、封存与未来示例拒绝、VOI 数学、不可见引用及工单/Carbon 权限边界。fixture 的独立 73 个测试含 40 个 CP-SAT 对独立穷举 oracle 的目标和约束比较以及部分 Carbon 实际引擎比对，具体覆盖/限制在 `V2_FIXTURES_DETAIL.md`。

集成中发现 fixture JSON Schema 将所有 kind 限定为 dispatch/carbon，但 Carbon 文件的 kind 表示 unit_conversion 等数学子类型；已将 schema 改为非空字符串，具体合法性仍由完整 fixture 数学校验器检查。另修复包 manifest 漏掉子 Skill manifest 的 hash、S09/S10 验证结果字段映射导致摘要为空、冻结报告初次仅结构检查的问题。最终生成进行 hash 真校验，不用静态通过标志替代结果。

本文件记录的是程序验收和合成回放准备完成；没有独立专业盲审，没有真实设备现场闭环实验，也没有以平衡合成分布宣称真实部署 precision。完整实际 LLM 单 Agent 回放与上下文实验由运行时实施记录说明。阶段性提交的 Git hash 和后续检查结果由总负责人在统一提交后追加到主实施台账；本模块负责人未单独执行 commit。
