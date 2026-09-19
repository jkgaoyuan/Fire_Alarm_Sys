"""
角色权限父子完整性守卫
======================

`scripts/init_data.py` 的 `ROLE_PERM_MAP` 逐个角色列权限码。**列了子权限不等于
能进页面**：菜单树只取 `perm_type='menu'` 的已授权项
（`permission_service.build_menu_tree`），且**不做「父菜单随子权限自动补齐」**
—— 一个 button 码即便 `parent_code` 指向某菜单，也带不出那个菜单。

于是「授予了域的按钮、却没授予域的菜单码」会静默失效：角色持有 `xxx:view` /
`xxx:execute`，侧边栏却没有入口、前端路由也生成不出来（路由是按后端菜单树
生成的，`utils/menu.js` 的 `generateRoutesFromMenus`）。**这些按钮权限等于白给，
而任何测试都不会报错** —— 它们各自单看都合法。

本仓 2026-09-19 实测踩到两处，形态完全相同：

    duty_officer: emergency:view / emergency:timeline   缺 emergency:event
    duty_officer: linkage:view   / linkage:execute      缺 linkage:plan

同组里 `drill:event` 是给对了的，说明「域菜单码要进角色清单」本来就是既定写法。

守卫规则（**严格，无豁免名单**）：
    凡角色持有的权限码，其 `parent_code` 指向的权限码，该角色也必须持有。

写成严格规则是因为实测下来它本来就成立：修掉上述两处后，三个角色（chief /
duty_officer / maintainer）的 77 个权限码里**零违规**。没有豁免名单就不会烂成
垃圾桶（对照 `test_permission_coverage.py` 的 `UNENFORCED_ALLOWLIST`，
那份豁免里有 3 个孤儿码长期挂着）。
"""

import pathlib

from scripts.init_data import BUTTON_PERMS, MENU_LEVEL1, MENU_LEVEL2, ROLE_PERM_MAP

INIT_DATA = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "init_data.py"

ALL_PERMS = [*MENU_LEVEL1, *MENU_LEVEL2, *BUTTON_PERMS]

# perm_code -> parent_code（一级菜单无 parent）
PARENT_OF: dict[str, str | None] = {
    item["perm_code"]: item.get("parent_code") for item in ALL_PERMS
}
DEFINED = set(PARENT_OF)


def test_every_granted_code_is_defined():
    """
    角色清单里的码必须都在权限定义里存在。

    反例后果：`init_data.py` 绑定时是
    `[perm_map[c] for c in ROLE_PERM_MAP[role] if c in perm_map]` ——
    **静默跳过**未定义的码（`if c in perm_map`）。所以写错一个编码不会报错，
    只会少授一个权限，然后在某个页面上表现为莫名其妙的 403 或「按钮不见了」。
    """
    ghosts = {
        role: sorted(set(codes) - DEFINED) for role, codes in ROLE_PERM_MAP.items()
    }
    ghosts = {role: codes for role, codes in ghosts.items() if codes}

    assert not ghosts, f"角色清单里出现未定义的权限码（绑定时会静默跳过）：{ghosts}"


def test_every_granted_code_has_its_parent_granted():
    """
    TC-PERM-030: 授予了子权限，就必须一并授予其父级 —— 否则子权限静默失效。

    重点在 **menu 父级**：缺它时页面进不去、路由生成不出来，而 view/execute
    这类按钮码本身是「合法」的，单看每一行都没问题，因此没有任何用例会报错。
    """
    violations = {}
    for role, codes in ROLE_PERM_MAP.items():
        granted = set(codes)
        missing = []
        for code in codes:
            parent = PARENT_OF.get(code)
            # 二级菜单的父级同样必须授予，否则它会因 parent 不在菜单树里
            # 而被 `build_menu_tree` 当成根节点（层级错乱），这里一并钉住
            if parent and parent not in granted:
                missing.append(f"{code} 需要 {parent}")
        if missing:
            violations[role] = sorted(missing)

    assert not violations, (
        "角色持有子权限却缺父级，子权限会静默失效"
        f"（菜单树不补齐父菜单，页面进不去）：{violations}"
    )


def test_chief_grant_is_by_full_binding_not_a_hardcoded_list():
    """
    主管的全量授权必须仍由「绑定全部权限码」实现，清单本身保持为空。

    对应待办 P2-012：`bind_permissions(chief_role, list(perm_map.values()))`
    这一机制此前无任何回归守卫。把它改成硬编码名单**不会有行为测试发现**——
    直到某个新权限码忘了加进名单，主管莫名其妙少一个权限、页面上少个按钮。

    清单留空是**设计**（不是遗漏），所以两件事一起钉：清单为空 + 绑定语句在位。
    只钉「清单为空」不够——可以在别处改成硬编码；只钉语句在也不够——
    可以同时在清单里堆一长串。

    为什么没有「菜单码必须至少被某角色持有」这条：chief 走全量绑定，
    于是每个已定义码必然被持有，那样的断言**构造上恒真**，测不出任何东西。
    """
    assert ROLE_PERM_MAP["chief"] == [], (
        "chief 的清单应保持为空（由 bind_permissions 全量绑定），"
        f"实际写了 {sorted(ROLE_PERM_MAP['chief'])}"
    )

    source = INIT_DATA.read_text(encoding="utf-8")
    assert "bind_permissions(chief_role, list(perm_map.values()))" in source, (
        "chief 的全量授权语句已不在 —— 若改成硬编码名单，"
        "新增的权限码将不再自动授予主管"
    )
