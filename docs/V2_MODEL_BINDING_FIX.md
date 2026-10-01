# V2 模型包输入与真实周期接入复核

本软件阶段发生在冻结云端实验和数值研究之后，不修改旧协议、模型参数、sealed 分数或原始数据。
复核依据是实际运行接口和手工输入边界测试，不使用 final 标签选择实现。

## 实际问题与修改

原运行适配器默认把全部安全包绑定到同一 XJTU 特征包。新增 MATR 与多源包的模型域、物理对象和
输入模式不同，这会造成错误绑定。现在服务端从已校验包的 `run.json` 解析当前仓库内的 V2
开发清单，先检查命名空间、划分和保护身份，再打开数值数组。历史绝对路径只用于匹配仓库内
`data/derived/v2` 后缀，不允许读取仓库外文件。

含 final/sealed/protected 对象或未交付的研究清单不能成为运行输入。此类安全包仅使用已 hash
校验、全部属于 dev 的包内重载样例，且 NPZ 必须恰好只有 features、sequences、sequence_mask、
domain 四个输入键。包版本或输入清单变化会拒绝旧绑定；安装身份与 V1 源映射仍需一致。

`/api/v2/model-packages` 对每个包返回自己的 `feature_rows` 和 `binding_input_source`；Web 切换包
会清空旧观察选择。开发清单无可用输入时返回空列表与明确状态。

原接口还将真实 MATR 周期统一展示为来源记录序号。现在仅当 source_id 非空、
time_basis=verified_physical_cycle 且 physical_cycles_known 严格为布尔 true 时保留物理周期。
结构化 source_time 携带同样证明字段；缺少证明仍按序号处理，ISO 墙钟时间保持其语义。
Agent 输入验证同步接受有来源证明的物理周期，并保留查询前可见性约束。

运行查询排除 split、target_observed_at/available_at、survival_censor_type 和未来生存标签时间。
寿命阈值与比较算符是已冻结的目标定义，可以保留；未来删失结果不能进入输入。

## 实际验证

```bash
env BATTERY_LLM_API_KEY= .venv/bin/python -m pytest -q \
  battery_platform/tests/test_v2_package_live.py \
  battery_platform/tests/test_v2_package_inputs.py \
  battery_platform/tests/test_v2_source_coordinates.py
```

结果为 **14 passed in 3.61s**。其中两个用例调用真实 API 和模型作业，再执行规则 Agent，
没有模型/HTTP mock：M1 MATR 以开发特征和真实周期运行，SOH/RUL 有输出；M1 多源以 label-free
dev 样例运行 MATR 观察。两者均保持实验回放来源、不建立 V1 绑定、不自动产生正式工单。
其余手工测试检查 final/sealed/protected 在数值加载前被拒、标签数组拒绝、包版本变化、
未来字段过滤和周期证明类型。MATR 的效率/故障仍 unsupported，寿命未校准，SOH CQR 样本不足。

首次测试误把 SOH 的 calibrated_interval 当作 RUL 字段，实际数值作业已成功；修正测试为验证
RUL discrete_survival 与 calibration_version=null 后重验通过，没有改变模型或接口。

真实 Chrome 闭环也重验：安全包选择→数值作业→截止时间诊断，**1 passed (13.2s)**。
它使用原 XJTU 包与临时数据库，不拦截 API；新 MATR/多源包由上述两个实际 API 用例覆盖。

此结果验证接入一致性，不证明小样本寿命泛化、真实现场诊断准确率或生产部署资格。
