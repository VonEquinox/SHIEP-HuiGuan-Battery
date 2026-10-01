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

数据库初始化按 `app/migrations/` 数字顺序执行升级，记录脚本 SHA256。
升级前备份到独立运行目录 `backups/pre-v2-migration-*.sqlite`，升级失败会回滚本次事务。
每次启动检查已经执行的脚本校验和；不得原地修改已发布迁移，应新增版本。

```bash
./scripts/v2.sh test
cd battery_platform/frontend
npm run build
```

模块说明及真实执行证据参见 [实施记录](V2_IMPLEMENTATION_LOG.md)。
