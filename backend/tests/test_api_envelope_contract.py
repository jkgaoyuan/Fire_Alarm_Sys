"""
API 响应信封契约守卫
====================

`docs/plan/API_RESPONSE_FORMAT_SPECIFICATION.md` 要求所有 JSON 业务接口返回统一信封
`{code, message, data}`（`CLAUDE.md` 的 AI 协作协议第一节同样强制）。

这条约定**没有自动化约束**，而漏掉它的后果是**静默的**：
`frontend/src/utils/request.js` 的响应拦截器对两种形状都放行——

    if (data && typeof data.code === 'number') { return data }
    return data            # 没有 code 也照样返回

于是组件按 `res.data.items` 读一个裸返回的响应时拿到 `undefined`，再被 `|| {}`
兜底，页面**显示 0 而不是报错**。2026-09-13 的「维修统计页四项指标恒为 0」
就是这样漏了几个月——后端有数据，前端全显示空。

所以本文件用静态方式守住这条契约：扫描 `app/api/v1/` 下所有路由函数，
要求每个 `return` 都是信封。不依赖数据库、不依赖鉴权、毫秒级。

分类规则（`_classify`）：
- `envelope` —— `Response(code=..., ...)`，或含 `code` 键的手写 dict
  （`devices.py` 就是手写的，合规）
- `raw-http` —— `Response(content=/media_type=/headers=)`、`FileResponse`、
  `StreamingResponse`、`PlainTextResponse`、`HTMLResponse` 等**文件/流式下载**，
  合法豁免：它们不是 JSON 业务载荷，塞不进信封
- `no-body` —— `status_code=204`，按 HTTP 规范不得有响应体，豁免
- `bare` —— 裸模型 / 裸 dict，**违规**

维护规则：`KNOWN_VIOLATIONS` 只许删、不许加。新增接口必须直接合规。
"""

import ast
import pathlib

import pytest

API_DIR = pathlib.Path(__file__).resolve().parent.parent / "app" / "api" / "v1"

# 原始 HTTP 响应（下载/流式），不是 JSON 业务载荷，合法豁免
_RAW_RESPONSE_NAMES = {
    "FileResponse",
    "StreamingResponse",
    "PlainTextResponse",
    "HTMLResponse",
    "RedirectResponse",
}

# 迁移中的已知违规：**只许删、不许加**。
# 三个文件整块没跟上统一信封（其余 15 个文件 119 个端点已 100% 合规）。
KNOWN_VIOLATIONS = {
    # linkage_logs.py —— 已于 2026-09-13 迁移完成，白名单清空。
    # 注：同文件的 export_alarm_linkage_logs 是 PlainTextResponse（CSV 下载），
    # 属天然豁免，本就不该进白名单——最初误加，被
    # test_known_violations_are_still_actually_violating 当场拦下。
    # linkage_plans.py（7）
    ("linkage_plans.py", "get_linkage_plans"),
    ("linkage_plans.py", "get_linkage_plan_detail"),
    ("linkage_plans.py", "create_linkage_plan"),
    ("linkage_plans.py", "update_linkage_plan"),
    ("linkage_plans.py", "toggle_linkage_plan_status"),
    ("linkage_plans.py", "simulate_linkage_trigger"),
    ("linkage_plans.py", "execute_linkage_plan"),
    # repair.py（11）
    ("repair.py", "list_repair_orders"),
    ("repair.py", "create_repair_order"),
    ("repair.py", "get_repair_order"),
    ("repair.py", "assign_repair_order"),
    ("repair.py", "complete_repair_order"),
    ("repair.py", "accept_repair_order"),
    ("repair.py", "return_repair_order"),
    ("repair.py", "get_repair_overview"),
    ("repair.py", "get_repairer_workload"),
    ("repair.py", "get_fault_distribution"),
    ("repair.py", "get_top10_fault_devices"),
}


def _is_route(node: ast.AST) -> bool:
    """是否是 @router.<method>(...) 装饰的函数"""
    for dec in getattr(node, "decorator_list", []):
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and isinstance(dec.func.value, ast.Name)
            and dec.func.value.id == "router"
        ):
            return True
    return False


def _decorator_status_code(node: ast.AST):
    """从路由装饰器里取出 status_code，用于识别 204"""
    for dec in getattr(node, "decorator_list", []):
        if not isinstance(dec, ast.Call):
            continue
        for kw in dec.keywords:
            if kw.arg == "status_code":
                v = kw.value
                if isinstance(v, ast.Attribute):
                    return v.attr  # 如 HTTP_204_NO_CONTENT
                if isinstance(v, ast.Constant):
                    return v.value
    return None


def _classify(value: ast.AST) -> str:
    """给单个 return 表达式分类"""
    if isinstance(value, ast.Call):
        fn = value.func
        name = (
            fn.id
            if isinstance(fn, ast.Name)
            else (fn.attr if isinstance(fn, ast.Attribute) else "")
        )
        if name in _RAW_RESPONSE_NAMES:
            return "raw-http"
        if name == "Response":
            # 关键区分：Response(code=...) 是信封；Response(content=/media_type=)
            # 是文件下载（如 devices.py 的导入模板、轨迹导出）
            kw_names = {kw.arg for kw in value.keywords}
            return "envelope" if "code" in kw_names else "raw-http"
        return "bare"

    if isinstance(value, ast.Dict):
        keys = {k.value for k in value.keys if isinstance(k, ast.Constant)}
        return "envelope" if "code" in keys else "bare"

    return "bare"


def _iter_routes():
    """产出 (文件名, 函数名, 行号, 分类集合)"""
    for path in sorted(API_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _is_route(node):
                continue

            if str(_decorator_status_code(node)) in ("204", "HTTP_204_NO_CONTENT"):
                yield path.name, node.name, node.lineno, {"no-body"}
                continue

            kinds = set()
            has_value_return = False
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and sub.value is not None:
                    has_value_return = True
                    kinds.add(_classify(sub.value))
            if not has_value_return:
                # 没有 return 值，且非 204：也归为无响应体
                kinds = {"no-body"}

            yield path.name, node.name, node.lineno, kinds


ROUTES = list(_iter_routes())


def test_router_scan_is_not_empty():
    """守卫自身的第一道保险：扫描必须真的扫到东西"""
    assert len(ROUTES) > 100, f"只扫到 {len(ROUTES)} 个路由，扫描逻辑可能失效了"


def test_json_endpoints_return_envelope():
    """
    每个返回 JSON 的路由都必须用统一信封。

    不修会怎样：裸返回被前端拦截器静默放行，组件读 res.data 拿到 undefined，
    再被 `|| {}` 兜底 → 页面显示 0/空白而不报错。维修统计页全 0 即此。
    """
    offenders = [
        f"{file}:{lineno} {name} -> {'/'.join(sorted(kinds))}"
        for file, name, lineno, kinds in ROUTES
        if "envelope" not in kinds
        and not kinds <= {"raw-http", "no-body"}
        and (file, name) not in KNOWN_VIOLATIONS
    ]

    assert not offenders, (
        "以下路由返回裸数据，未使用统一信封 {code, message, data}：\n  "
        + "\n  ".join(offenders)
        + "\n\n修复方式见 docs/plan/API_RESPONSE_FORMAT_SPECIFICATION.md；"
        "若是文件下载请用 FileResponse/StreamingResponse（天然豁免）。"
    )


def test_known_violations_are_still_actually_violating():
    """
    白名单只许减不许加：已修好的条目必须及时移出，否则白名单会悄悄腐烂成噪音。

    不修会怎样：某人迁移完某模块却忘了删白名单，守卫从此对该模块视而不见，
    下次再退化不会有任何提示。
    """
    still_bad = {
        (file, name)
        for file, name, _, kinds in ROUTES
        if "envelope" not in kinds and not kinds <= {"raw-http", "no-body"}
    }

    stale = KNOWN_VIOLATIONS - still_bad
    assert not stale, (
        f"以下条目已不再违规，请从 KNOWN_VIOLATIONS 中删除：{sorted(stale)}"
    )


@pytest.mark.parametrize("file,name", sorted(KNOWN_VIOLATIONS))
def test_known_violation_still_exists(file, name):
    """白名单里的条目必须真的还存在，避免拼写错误导致守卫空转"""
    names = {(f, n) for f, n, _, _ in ROUTES}
    assert (file, name) in names, f"{file}:{name} 在路由里找不到，白名单写错了？"
