# main → DEV PDF 的正文、数据与构建来源

最终文件：[`../HuiGuan_DEV_vs_main_20261002.pdf`](../HuiGuan_DEV_vs_main_20261002.pdf)。
固定实现为 main `c4203014` / DEV `0d9a53de`；日期为 2026-10-02。

| 材料 | 用途 |
| --- | --- |
| `report_content.json` / `report_content.md` | 完整正文、表格、公式、每页来源；Markdown 可以直接搜索 |
| `parts/` | 四名协作 Agent 提供的详细章节；汇编脚本统一修正、排序与补充 |
| `data/` | 保留机器回执数值、口径、人口、版本与相对提升复算；不是生成的估计值 |
| `evidence/` | 功能、模型、Agent、Carbon/Skill 的独立研究与复核记录 |
| `figures/` | 归档真实界面截图的裁剪；曲线与流程图直接生成矢量，不需要中间图片 |
| `assemble_report.py` | 固定顺序汇编 50 页正文、结果图说明与证据边界 |
| `build_report.py` | ReportLab 中文矢量排版、封面、目录、页码、书签与 11 页来源索引 |
| `verify_report.py` | 来源版本/hash、公式算术、字体覆盖、文字提取与排版边界检查 |
| `layout_receipt.json` / `qa_receipt.json` | PDF hash、页数、逐页占用、来源 hash 和机器 QA |
| `visual_review.json` | 最新 62 页 PNG 的团队逐页目视结果；不由机器检查代替 |
| `*.py.lock` | UV script 锁定依赖，保证重建所用版本；与项目根 `uv.lock` 独立 |

安装 UV 后，在仓库根运行一键重建：

```bash
HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897 \
  bash output/pdf/source/rebuild.sh
```

`assemble_report.py` 只依赖 Python 标准库；构建与验证由 UV 使用 script 锁文件。
中文排版使用本机 macOS 的 STHeiti Light/Medium；回退字体为 Arial Unicode。
其他系统需为 `init_fonts()` 配置允许嵌入的中文字体。PDF 已嵌入所用字体，阅读文件不依赖本机字体。
ReportLab 使用 invariant 模式，固定输入在已验证的两套运行环境中重建 PDF SHA 完全一致。

构建不执行模型训练、云 API 或 testing/sealed 重评分。历史分数保持原协议，
开发集提升、历史 final、云 pilot 程序质量、数学 fixture 与软件回归分开说明。
`evidence/` 保留汇编前笔记；其中指出的旧文档错误已在正文与原文档中纠正，
最终表述以 `report_content.json` 与 PDF 为准。

机器验证不能取代视觉 QA。重新改动正文/图表后，应再次用 Poppler 渲染并逐页目视：

```bash
mkdir -p tmp/pdfs/render
pdftoppm -r 110 -png output/pdf/HuiGuan_DEV_vs_main_20261002.pdf tmp/pdfs/render/page
```
