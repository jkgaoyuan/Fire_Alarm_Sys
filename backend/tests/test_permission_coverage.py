"""
权限码覆盖守卫
==============

`scripts/init_data.py` 里定义并逐角色授予了一批 button 型权限码
（`repair:assign`、`system:user:create` …）。**定义了不等于在用**：
一个码如果没有任何端点用 `require_permission` 去校验，它就是摆设——
把它授给某个角色、或从某个角色撤销，都不会改变任何行为。

这个漂移不会有任何报错，只会让人以为 RBAC 生效了。2026-09-13 审计时
119 个端点里就有 15 个这样的码，其中 `repair:*` 5 个是因为 repair.py 改用了
**手写的角色/归属判断**（`if not any(r.role_code == "chief" ...)`），
`system:user:*` / `system:role:*` 7 个是因为端点验的是**更粗的父级 menu 码**。

本守卫把「定义 vs 校验」的差集固定下来，只许减不许加。

配套的事实基础（2026-09-13 实测，不是读代码推的）：
- 119 个端点：95 个有权限码校验 / 20 个仅验登录 / 4 个无鉴权
- 4 个无鉴权的是 login、refresh、logout、设备上报，均属应当公开
- 代码里校验的 44 个码，**全部**在种子数据里有定义（零幽灵码）
"""

import ast
import pathlib

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
INIT_DATA = BACKEND_DIR / "scripts" / "init_data.py"
API_DIR = BACKEND_DIR / "app" / "api" / "v1"

# 已定义但没有任何端点校验的 button 码：**只许减、不许加**。
#
# 三者性质不同，别当成一类处理：
#   ① 被手写检查取代（5）—— repair.py 用 role_code=="chief" / repairer_id==me
#      代替权限码。安全上未必更弱（实测 maint01 打 assign 是 403），
#      但「授予/撤销这些码」是空操作，RBAC 看起来生效实际没接线。
#   ② 被更粗的 menu 码取代（7）—— 端点验的是 system:user / system:role，
#      粒度比定义的 button 码粗。实测这些端点确实 403，不是漏洞，是口径不符。
#   ③ 孤儿码（3）—— 有更细的码在用了，这三个没人引用，多半是早期设计的残留。
UNENFORCED_ALLOWLIST = {
    # ① 被手写检查取代
    # ① 被手写检查取代 —— repair:* 5 个已于 2026-09-13 接线完成，本类清空：
    #    assign/accept/return 的 `role_code == "chief"` 判断换成了
    #    repair:assign / repair:accept 权限码；complete 在保留归属检查的同时
    #    加了 repair:repair；list/get/4 个统计加上了 repair:view / repair:create。
    #    主管不受影响——init_data 里 bind_permissions(chief_role, 全部权限码)。
    # ② 被更粗的 menu 码取代
    "system:user:create",
    "system:user:update",
    "system:user:delete",
    "system:user:resetpwd",
    "system:role:create",
    "system:role:update",
    "system:role:delete",
    # ③ 孤儿码
    "alarm:handle",
    "device:repair",
    "monitor:confirm",
}


def _module_list(name: str) -> list:
    """从 init_data.py 里取出一个**字面量**列表（不用正则，避免键序/嵌套踩坑）"""
    tree = ast.parse(INIT_DATA.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"init_data.py 里找不到 {name}")


def _seeded_button_codes() -> set[str]:
    return {entry["perm_code"] for entry in _module_list("BUTTON_PERMS")}


def _all_seeded_codes() -> set[str]:
    """
    全部已定义的权限码（menu + button）。

    反向检查要用这个而不是 BUTTON_PERMS：端点校验 **menu 码** 是合法的
    （users.py 就验 `system:user`、roles.py 验 `system:role`，
    它们确实是 MENU_LEVEL2 里的菜单码）。只按 button 比会把它们误报成幽灵码。
    """
    codes = set()
    for name in ("MENU_LEVEL1", "MENU_LEVEL2", "BUTTON_PERMS"):
        codes |= {entry["perm_code"] for entry in _module_list(name)}
    return codes


def _enforced_codes() -> dict[str, set[str]]:
    """扫描 app/api/v1 下所有 require_permission("x")，返回 {码: {文件名}}"""
    used: dict[str, set[str]] = {}
    for path in sorted(API_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "require_permission"
            ):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        used.setdefault(arg.value, set()).add(path.name)
    return used


SEEDED = _seeded_button_codes()
ALL_SEEDED = _all_seeded_codes()
ENFORCED = _enforced_codes()


def test_scan_is_not_empty():
    """守卫自身的第一道保险：两侧都必须真的扫到东西"""
    assert len(SEEDED) > 40, f"只扫到 {len(SEEDED)} 个种子 button 权限码，解析可能失效"
    assert len(ALL_SEEDED) > len(SEEDED), "全部码应多于 button 码（还含 menu 码）"
    assert len(ENFORCED) > 30, f"只扫到 {len(ENFORCED)} 个被校验的码，扫描可能失效"


def test_every_button_code_is_enforced_or_allowlisted():
    """
    每个定义并授予出去的 button 权限码，都必须真的被某个端点校验。

    不修会怎样：定义了却没人校验的码是**空操作**——把它授予角色或撤销，
    系统行为毫无变化。看起来 RBAC 生效了，实际那部分权限是假的。
    """
    unenforced = sorted(SEEDED - set(ENFORCED) - UNENFORCED_ALLOWLIST)

    assert not unenforced, (
        "以下 button 权限码在 init_data.py 里定义了，却没有任何端点校验"
        "（授予/撤销它们不会有任何效果）：\n  "
        + "\n  ".join(unenforced)
        + "\n\n要么在对应端点加 require_permission(码)，"
        "要么确认它确实无用并从未授予中删掉。"
    )


def test_allowlist_is_not_stale():
    """
    白名单只许减不许加：已经接上校验的码必须及时移出。

    不修会怎样：某人给 repair.py 接上权限码后忘了删白名单，守卫从此对这几个码
    视而不见，将来再摘掉校验也不会有任何提示。
    """
    stale = sorted(UNENFORCED_ALLOWLIST & set(ENFORCED))

    assert not stale, f"以下码已接上校验，请从 UNENFORCED_ALLOWLIST 移除：{stale}"


def test_allowlist_entries_are_still_defined():
    """白名单里的码必须仍存在于种子数据，防拼写错误导致守卫空转"""
    unknown = sorted(UNENFORCED_ALLOWLIST - SEEDED)

    assert not unknown, f"白名单里的码在 BUTTON_PERMS 中找不到：{unknown}"


def test_no_ghost_codes():
    """
    反向检查：代码里校验的码必须在种子数据里有定义。

    不修会怎样：校验一个从没被定义、也从没授予任何角色的码，
    等于把端点对所有人关闭（主管也过不去，因为主管绑定的是「已定义的权限列表」）。
    这种端点会变成谁都用不了的死接口。
    """
    ghosts = sorted(set(ENFORCED) - ALL_SEEDED)

    assert not ghosts, (
        "以下权限码被代码校验，但 init_data.py 里没有定义——"
        f"对应端点将无人可访问：{ghosts}"
    )
