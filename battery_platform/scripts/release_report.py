"""Publish a source-bound acceptance report only after all verification passed."""

from __future__ import annotations
import hashlib
import importlib.metadata
import json
import os
import socket
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
os.environ["BATTERY_DISABLE_WORKER"] = "1"
from app.main import app
from app.services import sha

reports = APP / "runtime/acceptance"
docs = APP / "docs"
suites = list(ET.parse(reports / "backend-tests.xml").getroot().iter("testsuite"))
backend = {
    k: sum(int(s.get(k, 0)) for s in suites)
    for k in ("tests", "failures", "errors", "skipped")
}
browser = json.loads((reports / "browser-results.json").read_text())["stats"]
models = json.loads((reports / "real-model-pipeline.json").read_text())
assert (
    backend["tests"] >= 27
    and backend["failures"] == backend["errors"] == backend["skipped"] == 0
), backend
assert (
    browser["expected"] == 3
    and browser["unexpected"] == browser["skipped"] == browser["flaky"] == 0
), browser
assert models["status"] == "passed" and all(c["passed"] for c in models["checks"])
assert not models["protected_holdout_scored"]
for path, digest in models["original_source_hashes"].items():
    assert sha(APP.parent / path) == digest, path
ports = {}
for port in (8787, 8791, 5173):
    try:
        stream = socket.create_connection(("127.0.0.1", port), timeout=0.2)
        stream.close()
        ports[str(port)] = "listening"
    except OSError:
        ports[str(port)] = "closed"
assert ports["8791"] == "closed", "Browser acceptance server must stop before release"
schema = app.openapi()
(docs / "openapi.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2))
with sqlite3.connect(APP / "runtime/battery.db") as c:
    main_users = c.execute("SELECT count(*) FROM users").fetchone()[0]
lock = json.loads((APP / "frontend/package-lock.json").read_text())
versions = {
    "python_packages": {
        n: importlib.metadata.version(n)
        for n in (
            "fastapi",
            "starlette",
            "SQLAlchemy",
            "uvicorn",
            "pydantic",
            "argon2-cffi",
            "pytest",
            "Pillow",
        )
    },
    "javascript_packages": {
        n: lock["packages"]["node_modules/" + n]["version"]
        for n in (
            "react",
            "react-dom",
            "react-router-dom",
            "vite",
            "typescript",
            "@playwright/test",
        )
    },
}
metadata = {
    "accepted_at_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "greenfield single-node research/demo operations application v1",
    "backend": backend,
    "browser": browser,
    "real_model_pipeline": {
        "status": "passed",
        "checks": len(models["checks"]),
        "elapsed_seconds": models["elapsed_seconds"],
        "protected_holdout_scored": False,
    },
    "versions": versions,
    "api_operations": sum(
        method in ("get", "post", "put", "delete", "patch")
        for path in schema["paths"].values()
        for method in path
    ),
    "local_ports": ports,
    "main_database_users": main_users,
    "legacy_application_imported": False,
    "codex_provider_started": False,
    "codex_reason": "DESKTOP_CONTROL_UNAVAILABLE before model startup; implementation used direct host tools",
}
(reports / "release-metadata.json").write_text(
    json.dumps(metadata, ensure_ascii=False, indent=2)
)
(docs / "ACCEPTANCE.md").write_text(
    f"""# 交付验收记录

验收时间（UTC）：{metadata['accepted_at_utc']}

## 最终结果

| 检查 | 结果 | 机器可核查证据 |
|---|---|---|
| 后端回归 | {backend['tests']}通过；0失败、0错误、0跳过 | runtime/acceptance/backend-tests.xml |
| Chromium端到端 | 3通过；0失败、0不稳定重试、0跳过 | runtime/acceptance/browser-results.json |
| 真实模型流水线 | {len(models['checks'])}项检查通过 | runtime/acceptance/real-model-pipeline.json |
| API契约 | {metadata['api_operations']}个HTTP操作 | docs/openapi.json |
| 原模型与数据 | 核心源文件哈希与验收前一致 | real-model-pipeline.json / original_source_hashes |
| 保护测试电芯 | 未导入、未评分 | 真实流水线保护电芯断言 |
| 临时浏览器服务 | 8791端口关闭 | runtime/acceptance/release-metadata.json |

## 真正执行的模型任务

导入既有XJTU视图中的2058行、21个开发电芯；注册冻结快速/混合模型；通过应用队列运行真实ExtraTrees推理；真实训练三个种子的ExtraTrees版本；只在该版本未训练的电芯上执行验证调用；通过完整冻结混合模型在MPS上执行推理，并核对两分支的几何融合关系。

还故意移走新应用测试目录中新训练的权重文件，确认任务失败且不产生伪预测；恢复后检查数据库持久化和重启中断记录。没有修改或移走model_lab中的原模型权重。上述“真实模型验收”不是合成测试模型替代，也不是新的公开基准/SOTA证明。

## 浏览器覆盖

管理员在桌面提交真实推理，查看结果并从告警派单；维修人员在390px手机视图登录、接单、开始处理、上传证据并提交结果；另外的调度员在桌面独立验收、关闭、刷新确认持久化。另测观察者只读权限，以及七个工作区的桌面/手机渲染和页面运行异常。

自动化用的是独立browser-*运行目录及测试专用账户，不是主库默认口令。为了稳定覆盖告警流程，浏览器测试目录有明确命名的宽阈值测试策略；它不代表业务阈值或工业安全标准。所有模型预测仍由真实模型产生。

## 后端重点

会话/CSRF/跨来源请求/登录限流；观察者写入拒绝；最后管理员保护和会话撤销；密码修改；资产层级和版本冲突；更换/历史隔离/覆盖统计；CSV格式、重复来源与保护电芯排除；超大分块请求上限；小型分块JSON正常处理；任务幂等与取消；告警持续性和去重；派单资格；工单越权与非法跳步；两个并发操作只有一个版本更新成功；本次处理证据要求；附件内容与路径检查；反馈不覆盖原预测；通知归属；同样本模型比较；备份恢复；父进程退出时计算子进程停止。

## 排版与工具修复记录

早期浏览器测试出现精确文本定位器歧义，实际DOM已显示正确附件/关闭状态；已修正为链接/表格作用域定位，并从头重跑完整流程。手机截图必须等侧栏收起动画结束，避免把过渡帧当作最终界面。

Python源码用Black整理；TypeScript/CSS用Prettier整理；生产构建执行TypeScript检查。测试环境目前有Starlette TestClient关于HTTPX兼容层的弃用提醒；测试通过，不把它隐去或当作业务故障。

Codex托管入口在模型启动前返回Desktop app-server适配不可用，未创建模型会话。本次源代码由主机工具直接实现与验证，不声称存在独立Codex审查。

## 范围边界

验收通过的是本地单机、真实实验计算、模拟资产/人员和持久运维闭环。没有接入工业BMS、外部短信邮件、硬件保护控制、生产高可用集群；没有声称RUL、校准安全概率、任意化学体系泛化、最终研究SOTA或零过拟合。
""",
    encoding="utf-8",
)
skip = {
    ".venv",
    "runtime",
    "node_modules",
    "dist",
    "test-results",
    "playwright-report",
    "__pycache__",
    ".pytest_cache",
    ".git",
}
root_allow = {
    "AGENTS.md",
    "README.md",
    ".gitignore",
    "manage.sh",
    "ml_bridge.py",
    "requirements.in",
    "requirements.lock",
}
frontend_allow = {
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "vite.config.ts",
    "playwright.config.ts",
    "index.html",
}
docs_allow = {
    "BUILD_SPEC.md",
    "ARCHITECTURE.md",
    "ACCEPTANCE.md",
    "PROGRESS.md",
    "openapi.json",
}
files = []
for p in APP.rglob("*"):
    relative = p.relative_to(APP)
    if (
        any(part in skip for part in relative.parts)
        or p.name.startswith(".env")
        or p.is_symlink()
    ):
        continue
    allowed = (len(relative.parts) == 1 and p.name in root_allow) or (
        relative.parts[0] in ("app", "scripts", "tests") and p.suffix == ".py"
    )
    allowed = allowed or str(relative) == "scripts/browser_server.sh"
    allowed = allowed or (relative.parts[0] == "docs" and p.name in docs_allow)
    allowed = allowed or (
        len(relative.parts) >= 2
        and relative.parts[0] == "frontend"
        and (
            relative.parts[1] in ("src", "e2e")
            or (len(relative.parts) == 2 and p.name in frontend_allow)
        )
    )
    if not allowed or not p.is_file() or p.name.endswith((".tsbuildinfo", ".pyc")):
        continue
    files.append(p)
files.sort()
source_manifest = {
    "schema": "huiguan-source-v1",
    "created_at_utc": metadata["accepted_at_utc"],
    "files": {str(p.relative_to(APP)): sha(p) for p in files},
    "original_model_hashes": models["original_source_hashes"],
}
(docs / "source-manifest.json").write_text(
    json.dumps(source_manifest, ensure_ascii=False, indent=2)
)
delivery = APP / "runtime/delivery"
delivery.mkdir(exist_ok=True, parents=True)
archive = delivery / "battery_platform_source.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for p in files + [docs / "source-manifest.json"]:
        z.write(p, "battery_platform/" + str(p.relative_to(APP)))
summary = {
    **metadata,
    "source_files": len(files),
    "source_manifest_sha256": sha(docs / "source-manifest.json"),
    "source_archive": str(archive.relative_to(APP)),
    "source_archive_bytes": archive.stat().st_size,
    "source_archive_sha256": sha(archive),
}
(reports / "final-release.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2)
)
print(json.dumps(summary, ensure_ascii=False, indent=2))
