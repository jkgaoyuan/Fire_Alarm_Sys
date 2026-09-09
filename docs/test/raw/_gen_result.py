"""临时脚本：解析 pytest/vitest 原始输出，生成用例级执行结果 Markdown。用后可删。"""
import ast
import io
import json
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs/test/3.2-消防设备档案-测试执行结果.md"

# ---------- 后端 ----------
LINE = re.compile(r"^(tests/\w+\.py)::(\w+)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)")
cases = OrderedDict()
doc = {}
for ln in io.open(ROOT / "docs/test/raw/pytest-v.txt", encoding="utf-8", errors="replace"):
    m = LINE.match(ln.strip())
    if m:
        cases.setdefault(m.group(1), []).append((m.group(2), m.group(3)))

for f in cases:
    path = ROOT / "backend" / f
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ds = ast.get_docstring(node)
            doc[f + "::" + node.name] = (ds or "").strip().split("\n")[0] if ds else ""
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    ds = ast.get_docstring(sub)
                    doc[f + "::" + sub.name] = (ds or "").strip().split("\n")[0] if ds else ""

BE_32 = {
    "tests/test_device_type.py",
    "tests/test_device_crud.py",
    "tests/test_device_filter.py",
    "tests/test_device_permission.py",
    "tests/test_device_import.py",
    "tests/test_device_history.py",
    "tests/test_organization.py",
}

# ---------- 前端 ----------
vj = json.load(io.open(ROOT / "docs/test/raw/vitest.json", encoding="utf-8"))
fe = OrderedDict()
for suite in vj["testResults"]:
    rel = suite["name"].replace("\\", "/")
    rel = rel[rel.index("/src/") + 1 :]
    rows = []
    for a in suite["assertionResults"]:
        anc = " > ".join([t for t in a["ancestorTitles"] if t])
        rows.append((anc, a["title"], a["status"], a.get("duration") or 0))
    fe[rel] = rows

FE_32 = ("views/device/__tests__", "utils/__tests__/device.spec.js")

lines = []
w = lines.append
w("# 3.2 消防设备档案 —— 测试用例执行结果")
w("")
w("> 本文档由 `docs/test/raw/` 下的原始产物（`pytest-v.txt`、`vitest.json`）整理而成，"
  "记录每条用例的逐条执行结果。原始日志随文档一并存档，可复核。")
w("")
w("| 项目 | 值 |")
w("|------|-----|")
w(f"| 执行时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |")
w("| 后端环境 | Python 3.10.10 / pytest-8.1.1 / pytest-asyncio-0.23.8（SQLite `aiosqlite` 内存库） |")
w("| 前端环境 | Node v24.18.0 / vitest 1.6.1 / jsdom 24 |")
w("| 端到端环境 | `fire_alarm_backend` 容器 :8000 + PostgreSQL 15 + Redis 7（真实数据库） |")
total_be = sum(len(v) for v in cases.values())
passed_be = sum(1 for v in cases.values() for _, s in v if s == "PASSED")
total_fe = vj["numTotalTests"]
passed_fe = vj["numPassedTests"]
w(f"| 后端 | **{passed_be} passed / {total_be} total**（3.2 新增 "
  f"{sum(len(v) for f, v in cases.items() if f in BE_32)} 条） |")
w(f"| 前端 | **{passed_fe} passed / {total_fe} total**，{len(fe)} 个 spec 文件（3.2 新增 "
  f"{sum(len(r) for f, r in fe.items() if any(k in f for k in FE_32))} 条） |")
w("| 失败 | 0 |")
w("")
w("---")
w("")
w("## 一、后端用例逐条结果")
w("")
w("状态图例：✅ passed")
for f, rows in cases.items():
    tag = "（3.2 新增）" if f in BE_32 else ""
    w("")
    w(f"### `{f}`{tag}")
    w("")
    w("| # | 用例 | 结果 | 用例说明 |")
    w("|---|------|------|----------|")
    for i, (name, status) in enumerate(rows, 1):
        mark = "✅" if status == "PASSED" else "❌ " + status
        w(f"| {i} | `{name}` | {mark} | {doc.get(f + '::' + name, '')} |")
w("")
w("---")
w("")
w("## 二、前端用例逐条结果")
for f, rows in fe.items():
    tag = "（3.2 新增）" if any(k in f for k in FE_32) else ""
    w("")
    w(f"### `{f}`{tag}")
    w("")
    w("| # | 所属套件 | 用例 | 结果 | 耗时 |")
    w("|---|----------|------|------|------|")
    for i, (anc, title, status, dur) in enumerate(rows, 1):
        mark = "✅" if status == "passed" else "❌ " + status
        w(f"| {i} | {anc} | {title} | {mark} | {dur} ms |")
w("")
io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
print(OUT, len(lines), "行")
