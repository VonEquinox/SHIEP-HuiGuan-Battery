# V2 安装与运行

Python 依赖由根目录 UV 项目和锁文件固定；旧模型文件与历史结果不会被安装步骤改写。
开发/测试外网默认使用本机 7897 HTTP 代理，可通过环境变量调整。

```bash
./scripts/v2.sh install
cp .env.example .env
./scripts/v2.sh bootstrap --help
./scripts/v2.sh serve
```

在 `.env` 中设置测试 API Key 后，Agent 使用云端 OpenAI 兼容 `/chat/completions`。
不填 Key 时只能执行明确标注的规则回归；这不构成真实 LLM 能力验证。
不要把 `.env` 或运行目录提交到 Git。前端和小程序都不接收服务端 API Key。

默认监听 `127.0.0.1:8787`。手机联调需要显式配置可达地址、允许主机与实际微信账号的网络能力。
程序安装不自动建立账号或自动批准工单；账号由管理员初始化。

首次运行先执行 `./scripts/v2.sh bootstrap` 设置管理员密码，再执行 `./scripts/v2.sh demo`。
demo 创建有演示标记的资产和随机密码测试账号；终端只显示一次新建账号密码。
已有用户时 bootstrap 拒绝重置，可用 `./scripts/v2.sh user 用户名 --name 姓名 --role technician`
交互创建账号。后端角色来自账号记录，小程序不能自行选择角色。

根环境同时固定 `scikit-learn==1.7.2` 与 `tabicl==2.2.0`，兼容原 V1 冻结模型。
`BATTERY_ML_PYTHON` 保留 `.venv/bin/python` 的虚拟环境入口；不要改成其符号链接指向的系统解释器。
旧的 `battery_platform/manage.sh setup` 也委托根 UV 安装，其他旧管理命令继续可用。

数据库初始化按 `app/migrations/` 数字顺序执行升级，记录脚本 SHA256。
升级前备份到独立运行目录 `backups/pre-v2-migration-*.sqlite`，升级失败会回滚本次事务。
每次启动检查已经执行的脚本校验和；不得原地修改已发布迁移，应新增版本。

```bash
./scripts/v2.sh test
cd battery_platform/frontend
npm run build
```

测试命令会清除云端 Key，避免回归测试意外计费。实际云端 API 验收是单独的显式命令：

```bash
set -a
source .env
set +a
.venv/bin/python battery_platform/scripts/verify_v2_cloud_api.py
```

此验收使用临时数据库与合成资产，调用真实提供方、提交和读取真实 API，检查报告有效且批准前正式工单为零。
完成后数据库删除，脱敏证据写入 `battery_platform/reports/v2_integration/cloud_api.json`。

前端编译资源 `/assets/*` 与数字资产详情 `/assets/{id}` 共用旧前缀，服务显式优先匹配数字详情页。
启动时只向 Python 导入路径加入当前仓库根目录，因此从 `battery_platform` 启动也可加载 V2 模型研究包。

使用 `./scripts/v2.sh backup` 创建包含业务库、附件与注册模型的备份。
恢复通过 `./scripts/v2.sh restore 备份文件 新目标目录` 校验并输出到新目录，再停止旧实例、
设置 `BATTERY_RUNTIME` 为恢复目录后启动；恢复命令不会覆盖当前运行库。

模块说明及真实执行证据参见 [实施记录](V2_IMPLEMENTATION_LOG.md)。
