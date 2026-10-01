# V2 数据源接入与处理记录

实施日期：2026-10-02（Asia/Shanghai）。本记录覆盖实施总方案第 03 节的数据工程；平台的单个运维 Agent 与实施时用于并行编码的多个 Codex Agent 是不同对象。

## 已完成的实际处理

| 来源 | 官方元数据与许可记录 | 实际下载/复用与解析 | 本次结果 |
|---|---|---|---|
| XJTU | Zenodo 10963339；具体记录声明 CC BY 4.0，保留原始文件 MD5 | 复用只读原始 MAT；先按文件名排除全部 `-5`，冻结 21 个可开发对象为 11/3/4/3 | 初始仅打开 18 个 train/dev/calibration 对象：12,170 条记录、581 个曲线片段、1,972 个 RPT 参考 SOH 标签；3 个新 V2 final 在模型配方冻结后单独写入新目录 |
| MATR | 从官方项目页当前 SPA 中读取 API 路由、原始项目 ID、批次 `structFileId`；官方 API HTTP 200；平台声明 CC BY 4.0 | 下载完整原始 Arbin 单电芯 CSV 111,327,527 bytes；获取官方 2018 批次的原始条码与容量图测量 JSON | 单电芯 542 个明确物理周期、32 条完整原始曲线；容量摘要包注册 36 个条码，35 个有可用测量、38,198 个容量观测、3,801 个统计查询；不是论文完整复现 |
| DyAD | Figshare 23659323；具体记录声明 CC BY 4.0；保留每个包作者 MD5 | 下载最小 `battery_brand3.tar.gz` 55,469,605 bytes，通过 MD5 与 SHA256；100 个车辆标签来自实际 CSV | 在隔离转换进程中，按原始包顺序每车取 8 个片段，共 800 个真实运行片段、100 个独立车辆；按车辆冻结 60/15/10/15 |
| CH-BatteryGen | GitHub Releases 的当前 HTML 与实际 lazy asset 链接；README 声明 CC BY-NC-SA 4.0，并含学术/非商业用途限制 | 下载完整 `V1.0.7z` 386,457,534 bytes 和故障详情 XLSX 13,437 bytes；SHA256 与官方 HEAD 大小核对，作者未发布校验和 | 从实际发布包读取 96 个 CSV，每个故障类别 24 个，LFP/NCM 分别保留；按重复 VIN token 合并为 48 个保守根组、29/7/5/7 |

所有状态以 `source_registry.yaml` 为准。`parsed` 带有 `raw_scope`、具体已下载文件、解析 manifest 与未获取的官方文件列表；它不表示已完成该来源所有文件的导入。GitHub 匿名 API 曾返回 403，实际使用官方 HTML/原始文件路径作为后备并保留原失败信息。MATR 的 JavaScript 页面障碍已经通过当前官方 SPA/API 解决，没有写入猜测的下载地址。

审计分别记录已注册身份、实际有测量的身份和按冻结分组计算的独立对象数。MATR 通道 46 因官方收集问题保留身份并明确排除测量；CH 的 96 个场景身份只有 48 个保守 VIN 根组。新 V2 XJTU 的 final 三对象来自此前 V1 可开发文件集合，不能宣称从未进入过 V1 训练或独立评价 V1 M0；原 V1 保护对象全部仍被禁止读取。

原始下载使用 7897 代理，支持 Range 续传、3 次尝试、字节预算、作者校验和、额外 SHA256 和完成后的原子改名；成功文件设为只读。CH 与 MATR 无作者摘要，记录这一事实，不冒称作者校验通过。持久化下载回执保留稳定官方 URL，不保存过期的重定向签名参数。

## 输入与标签边界

XJTU 的源记录 ordinal 和官方 MATR 容量图的 ordinal 不是已经核验的物理循环数，因此这两种输入不提供 RUL。MATR 原始 Arbin CSV 则含明确 `Cycle_Index`，支持该原始测量任务的 0.88 Ah 阈值与生存事件/删失标记。未到阈值时保留右删失，末次记录加 1 不成为死亡事件。原始容量未强制单调化。

MATR 容量图单独使用第 10 个可见容量观测作固定参考，保留 `soh_nominal` 与参考 SOH 的不同定义。未知充电策略保留 `unknown`。缺曲线的对象走容量历史统计输入，曲线数组为空并有质量标记；不生成虚构电压、电流或温度。完整 corrected MATLAB 三批文件仅解析了官方下载元数据，未下载/复现；`paper_reproduction.json` 显式为 blocked，不能用当前容量摘要成绩冒充论文复现。

MATLAB 续测修复单测覆盖作者一基索引 `[8,9,10,16,17]` 对应 Python `[7,8,9,15,16]`，要求原始条码匹配与容量/周期连续性，拒绝仅凭可重复通道号合并。两次测量的原始曲线、各自路径与周期 offset 都保留，原先第一条曲线不会被第二条记录的 offset 移位。

DyAD 的目标是原始车辆异常标签，不是电芯确诊根因。片段的本地 `timestamp` 不作为全车辆统一时钟；可见时间使用原始车辆 `charge_segment` 序号。原始通道单位未单独核验，适配器只能使用统计特征；不能据此计算物理效率或 RUL。原片段标签与车辆故障标签均从在线特征表移除，只保留在监督目标表。

DyAD `.pkl` 采用 Torch ZIP 包装。本次转换使用限定的静态 opcode 数据语法，将 NumPy 数组状态还原为原始数字；没有调用 `pickle.load`、`torch.load` 或 pickle 指定的任何函数。未知 GLOBAL、dtype、opcode 和超出限制的数据被拒绝。实际转换在 macOS `sandbox-exec` 中禁止网络、派生进程与输出目录之外的写入。平台常规上传解析器仍拒绝所有 pickle/joblib。首次转换因 gzip 随机 seek 超过 CPU 限额而中止；修复为按原包 offset 顺序读取之后成功，未输出错误结果覆盖成功结果。

CH 是作者公开生成数据，`origin=public_generated`，命名空间为 `demo_synthetic`；与本项目 `expert_synthetic` 内容以及 DyAD 真实运行数据分别记录。其原始生成母本 ID 未发布；跨目录复用 VIN token 保持同一 split，不宣称不同 VIN 已通过母本独立性核验。最终测试只能标为探索性，不能声明干净的来源泛化。

效率只在完整起止状态、SOC 可比与计量边界明确时计算。本次这些来源没有形成效率闭合证据的记录保持 unavailable，缺标签不填 0。

## 代码与复现入口

契约位于 `model_lab/modeling/v2/data.py`，下载/官方解析与隔离转换位于 `sources.py`。`ParsedDataset` 写出 `identity_map/cycles/segments/targets.parquet`、逐条排除原因、split 与数据 hash；输出限定在新的 `data/derived/v2` 目录，拒绝覆盖已经存在的 V2 run。

```bash
uv run python -m model_lab.scripts.v2.ingest --source all --metadata-only
uv run python -m model_lab.scripts.v2.ingest --source dyad --download-only --file-name battery_brand3.tar.gz
uv run python -m model_lab.scripts.v2.ingest --source matr --download-only --file-name 2017-06-30_4_65C-44per_5C_CH22.csv
uv run python -m model_lab.scripts.v2.ingest --source xjtu
uv run python -m model_lab.scripts.v2.audit --manifest model_lab/data/derived/v2/xjtu_development_20261001/manifest.json
uv run pytest model_lab/tests/v2/test_data_v2.py model_lab/tests/v2/test_sources_v2.py -q
```

下载 CLI 有单文件 4 GiB 默认上限与 70 GiB 以上的剩余磁盘空间要求，配置中的实际保留值为 75,161,927,680 bytes。原始包解压/源码解析是独立步骤，下载成功不会自动执行压缩包内代码。MATR 逐电芯下载解析通过当前官方 tests API 的实际 `dataFileId`，不是固定镜像地址。

实际导出路径与 hash 汇总在本目录 `*_data_receipt.json`。派生 Parquet、原始下载、完整官网 HTML/SPA JavaScript 与作者处理源码保留为本地证据，不随源码提交。小型官方 JSON、许可条款摘要、URL/内容 hash、来源状态、下载回执、测试与处理脚本进入版本控制；完整网页回执标记 `local_only`，需要复核时可从官方 URL 重新获取。后续批量实验由父 Agent 记录在独立的 V2 实施文档中。

CH 独立的统计故障基准代码由子 Agent 完成，使用作者公开生成数据及原生统计特征，按化学体系训练 GBDT、种子 0/1/2、隔离校准与 VIN 首片段指标、安全数值 JSON 树导出。10 个测试通过；随后父 Agent 释放计算安排，子 Agent 已完成三个种子的实际基准及 JSON 预测/指标重放，最大重放误差为 0。稳定报告位于 `model_lab/reports/v2/ch_generated_20261002/BENCHMARK.md`。所有产物保留 `demo_synthetic/public_generated`；dev 缺高内阻类、探索 final 缺正常类，完整四分类宏指标为 null，最终成绩不能声明真实车队泛化。

## 官方子集可复现 CLI 补交

`model_lab/scripts/v2/prepare_official_subsets.py` 为实际官方子集补充专门入口，分别调用已有 `parse_matr_official`、`parse_matr_csv`、`convert_dyad_archive` + `parse_table`、`parse_ch_csvs`，输出预解析对象 split、数据 manifest、结构审计与 `preparation_receipt.json`。输入使用官方元数据和原始路径；缺少原始文件会明确失败，不用虚构数据填充。所有输出目录必须是尚不存在的 `data/derived/v2` 子目录。以下命令从仓库根目录运行，示例输出名与既有冻结包不同；它们没有在此次补交中实际运行。

```bash
uv run python -m model_lab.scripts.v2.prepare_official_subsets --kind matr-summary \
  --tests-json model_lab/reports/v2/sources/matr/official_batch3_tests.json \
  --max-cells 36 --reference-ordinal 10 --query-stride 10 \
  --out model_lab/data/derived/v2/replay_matr_summary

uv run python -m model_lab.scripts.v2.prepare_official_subsets --kind matr-csv \
  --csv model_lab/data/raw/matr/2017-06-30_4_65C-44per_5C_CH22.csv \
  --metadata-json model_lab/reports/v2/sources/matr/download_receipt_cell_01.json \
  --out model_lab/data/derived/v2/replay_matr_arbin

uv run python -m model_lab.scripts.v2.prepare_official_subsets --kind dyad \
  --archive model_lab/data/raw/dyad/battery_brand3.tar.gz \
  --official-record model_lab/reports/v2/sources/dyad/official_record.json \
  --labels-csv model_lab/reports/v2/sources/dyad/official_labels.csv \
  --numeric-out model_lab/data/derived/v2/replay_dyad_numeric \
  --max-per-vehicle 8 --out model_lab/data/derived/v2/replay_dyad

uv run python -m model_lab.scripts.v2.prepare_official_subsets --kind ch \
  --archive model_lab/data/raw/ch_batterygen/V1.0.7z \
  --csv-root model_lab/data/raw/ch_batterygen/extracted_balanced_20261002 \
  --selection-json model_lab/reports/v2/sources/ch_batterygen/balanced_subset_inventory.json \
  --out model_lab/data/derived/v2/replay_ch_generated
```

必要原始路径是上述 MATR CSV、DyAD 原始 gzip tar、CH 原始 7z 与已解出的 CSV 根目录；它们不进入 Git。CH 的 `selection-json.selected[].path` 是原 7z 内的精确 96 个相对文件名，解压必须保留 `LFP|NCM/类别/vin_x/文件.csv` 四级布局。MATR CSV 元数据接受包含 `source_test` 的下载回执、单个官方 test JSON 或同名匹配的官方 tests JSON；必须保留原始 `cellId/name/dataFileId`。默认来源/许可凭据读取 `model_lab/reports/v2/sources/source_registry.yaml`，迁移目录可用 `--source-registry` 指定；所有命令参数均可用本机原始路径替换。

DyAD 先从原标签 CSV 仅读取 `car` 身份列，冻结车辆 split，再做限定静态数值转换；CH 先从精确文件路径冻结保守 VIN 根 split，再解析数值 CSV。MATR 容量摘要只使用 2018 独立批次，继续保留未知协议和 ordinal 的限制。CLI 只准备新数据包，不训练、校准或评价任何模型；`--dry-list` 仅显示参数，不打开测量文件或写输出。

此补交只执行 `uv run pytest model_lab/tests/v2/test_prepare_official_subsets_v2.py -q` 对应的根环境测试：4 个轻量守卫测试全部通过；另运行 CLI `--help` 检查。测试覆盖 dry-list 不打开缺失原始文件、不建输出目录，拒绝既有/非 V2 输出，原始依赖缺失明确报错，以及 CH 选择路径越界拒绝。没有重解析实际原始数据、运行训练或消费 final，也没有修改冻结表、manifest 或训练记录。

## 验证

13 个数据/来源测试在原 `model_lab/.venv` 和新的根 UV 环境均通过。覆盖原始安全格式拒绝、HDF5 外部链接拒绝、保护测试文件在打开前拒绝、续测身份与两条原始路径、精确/区间/右删失、阈值相等边界、对象级分组、未来特征拒绝、效率闭合条件、续传与作者摘要失败留存，以及静态数值转换拒绝可执行 GLOBAL。六个实际数据包的结构、表 hash、对象分组与明确 query 依赖审计均通过；这些结构检查不等同于模型性能结论。
