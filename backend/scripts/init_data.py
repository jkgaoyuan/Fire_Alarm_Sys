#!/usr/bin/env python3
"""
数据库初始化脚本
---------------
用途：在真实 PostgreSQL 环境中创建表并插入预置数据（角色、权限、菜单、测试用户）

运行方式：
    cd E:/pycharm/AI_PROJECT_CODE/Fire_Alarm_Sys/backend
    python scripts/init_data.py

依赖：.env 文件中需配置正确的 DATABASE_URL
"""

import asyncio
import sys
from pathlib import Path

# 将 backend 目录加入 Python 路径
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models.base import Base
from app.models.organization import Organization
from app.models.permission import Permission
from app.models.user import Role, User

settings = get_settings()

# 创建异步引擎
engine = create_async_engine(
    settings.database_url_async,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ============ 预置数据定义 ============

ROLES_DATA = [
    {"role_code": "duty_officer", "role_name": "消防值班员", "description": "负责实时监控与报警确认", "is_builtin": True},
    {"role_code": "maintainer",   "role_name": "维保人员",   "description": "负责设备巡检与维修",     "is_builtin": True},
    {"role_code": "chief",        "role_name": "消防主管",   "description": "负责系统管理与统计决策", "is_builtin": True},
]

# 一级菜单（parent_id = None）
MENU_LEVEL1 = [
    {"perm_code": "monitor:dashboard", "perm_name": "监控大屏",   "perm_type": "menu", "route_path": "/monitor/dashboard", "component": "views/monitor/Dashboard.vue",    "icon": "Monitor",   "sort_order": 1},
    {"perm_code": "alarm:center",      "perm_name": "报警中心",   "perm_type": "menu", "route_path": "/alarm/center",      "component": "views/alarm/Center.vue",         "icon": "Bell",      "sort_order": 2},
    {"perm_code": "device:archive",    "perm_name": "设备档案",   "perm_type": "menu", "route_path": "/device/archive",    "component": "views/device/Archive.vue",       "icon": "Box",       "sort_order": 3},
    {"perm_code": "linkage:plan",      "perm_name": "联动预案",   "perm_type": "menu", "route_path": "/linkage/plan",      "component": "views/linkage/Plan.vue",         "icon": "Link",      "sort_order": 4},
    {"perm_code": "inspection:task",   "perm_name": "巡检任务",   "perm_type": "menu", "route_path": "/inspection/task",   "component": "views/inspection/Task.vue",      "icon": "Calendar",  "sort_order": 5},
    {"perm_code": "drill:event",       "perm_name": "消防演练",   "perm_type": "menu", "route_path": "/drill/event",       "component": "views/drill/Event.vue",          "icon": "Fire",      "sort_order": 6},
    {"perm_code": "statistics:report", "perm_name": "统计报表",   "perm_type": "menu", "route_path": "/statistics/report", "component": "views/statistics/Report.vue",    "icon": "Trend",     "sort_order": 7},
    {"perm_code": "system:management", "perm_name": "系统管理",   "perm_type": "menu", "route_path": "/system",            "component": "Layout",                         "icon": "Setting",   "sort_order": 8},
]

# 系统管理子菜单
MENU_LEVEL2 = [
    {"perm_code": "system:user", "perm_name": "用户管理", "perm_type": "menu", "route_path": "/system/user", "component": "views/system/User.vue", "icon": "User", "sort_order": 1, "parent_code": "system:management"},
    {"perm_code": "system:role", "perm_name": "角色管理", "perm_type": "menu", "route_path": "/system/role", "component": "views/system/Role.vue", "icon": "Role", "sort_order": 2, "parent_code": "system:management"},
]

# 按钮/API 权限（parent_code 为关联的业务菜单）
BUTTON_PERMS = [
    # 监控大屏
    {"perm_code": "monitor:view",    "perm_name": "查看监控",     "perm_type": "button", "parent_code": "monitor:dashboard"},
    {"perm_code": "monitor:confirm", "perm_name": "确认监控告警", "perm_type": "button", "parent_code": "monitor:dashboard"},
    # 报警中心
    {"perm_code": "alarm:confirm", "perm_name": "确认报警", "perm_type": "button", "parent_code": "alarm:center"},
    {"perm_code": "alarm:handle",  "perm_name": "处置报警", "perm_type": "button", "parent_code": "alarm:center"},
    # 设备档案
    {"perm_code": "device:view",   "perm_name": "查看设备", "perm_type": "button", "parent_code": "device:archive"},
    {"perm_code": "device:create", "perm_name": "新增设备", "perm_type": "button", "parent_code": "device:archive"},
    {"perm_code": "device:update", "perm_name": "编辑设备", "perm_type": "button", "parent_code": "device:archive"},
    {"perm_code": "device:delete", "perm_name": "删除设备", "perm_type": "button", "parent_code": "device:archive"},
    {"perm_code": "device:retire", "perm_name": "退役设备", "perm_type": "button", "parent_code": "device:archive"},
    {"perm_code": "device:repair", "perm_name": "维修记录", "perm_type": "button", "parent_code": "device:archive"},
    # 联动预案
    {"perm_code": "linkage:config",  "perm_name": "配置预案", "perm_type": "button", "parent_code": "linkage:plan"},
    {"perm_code": "linkage:execute", "perm_name": "执行联动", "perm_type": "button", "parent_code": "linkage:plan"},
    # 巡检任务
    {"perm_code": "inspection:record", "perm_name": "巡检记录", "perm_type": "button", "parent_code": "inspection:task"},
    {"perm_code": "inspection:plan",   "perm_name": "巡检计划", "perm_type": "button", "parent_code": "inspection:task"},
    {"perm_code": "inspection:stat",   "perm_name": "巡检统计", "perm_type": "button", "parent_code": "inspection:task"},
    # 消防演练
    {"perm_code": "drill:full", "perm_name": "演练全流程", "perm_type": "button", "parent_code": "drill:event"},
    # 统计报表
    {"perm_code": "statistics:partial", "perm_name": "部分报表", "perm_type": "button", "parent_code": "statistics:report"},
    {"perm_code": "statistics:full",    "perm_name": "全部报表", "perm_type": "button", "parent_code": "statistics:report"},
    # 用户管理
    {"perm_code": "system:user:create",   "perm_name": "新增用户", "perm_type": "button", "parent_code": "system:user"},
    {"perm_code": "system:user:update",   "perm_name": "编辑用户", "perm_type": "button", "parent_code": "system:user"},
    {"perm_code": "system:user:delete",   "perm_name": "删除用户", "perm_type": "button", "parent_code": "system:user"},
    {"perm_code": "system:user:resetpwd", "perm_name": "重置密码", "perm_type": "button", "parent_code": "system:user"},
    # 角色管理
    {"perm_code": "system:role:create", "perm_name": "新增角色", "perm_type": "button", "parent_code": "system:role"},
    {"perm_code": "system:role:update", "perm_name": "编辑角色", "perm_type": "button", "parent_code": "system:role"},
    {"perm_code": "system:role:delete", "perm_name": "删除角色", "perm_type": "button", "parent_code": "system:role"},
]

# 角色权限映射
ROLE_PERM_MAP = {
    "duty_officer": [
        # 菜单
        "monitor:dashboard", "alarm:center", "device:archive", "statistics:report",
        # 按钮
        "monitor:view", "monitor:confirm",
        "alarm:confirm", "alarm:handle",
        "device:view",
        "statistics:partial",
    ],
    "maintainer": [
        # 菜单
        "device:archive", "inspection:task", "statistics:report",
        # 按钮
        "device:view", "device:repair",
        "inspection:record",
        "statistics:partial",
    ],
    "chief": [
        # 主管拥有全部权限（通过代码自动绑定所有权限）
    ],
}

# 测试用户
USERS_DATA = [
    {
        "username": "admin",
        "password": "Admin1234",
        "real_name": "系统管理员",
        "data_scope": "all",
        "status": "active",
        "role_codes": ["chief"],
    },
    {
        "username": "duty01",
        "password": "Duty1234",
        "real_name": "值班员张三",
        "data_scope": "dept",
        "status": "active",
        "role_codes": ["duty_officer"],
    },
    {
        "username": "maint01",
        "password": "Maint1234",
        "real_name": "维保员李四",
        "data_scope": "self",
        "status": "active",
        "role_codes": ["maintainer"],
    },
]


async def init_database():
    """初始化数据库：建表 + 插入预置数据"""
    async with engine.begin() as conn:
        # 创建所有表（如果已存在则跳过）
        await conn.run_sync(Base.metadata.create_all)
        print("[✓] 数据库表创建完成（已存在则跳过）")

    async with AsyncSessionLocal() as session:
        # 1. 插入组织架构根节点
        org = Organization(org_name="消防管理中心", org_type="building", sort_order=0)
        session.add(org)
        await session.flush()
        org_id = org.id
        print(f"[✓] 组织架构根节点创建完成: id={org_id}")

        # 2. 插入角色
        role_map = {}  # role_code -> Role 对象
        for role_data in ROLES_DATA:
            role = Role(**role_data)
            session.add(role)
            await session.flush()
            role_map[role.role_code] = role
            print(f"[✓] 角色创建完成: {role.role_code} (id={role.id})")

        # 3. 插入一级菜单
        perm_map = {}  # perm_code -> Permission 对象
        for menu_data in MENU_LEVEL1:
            perm = Permission(**menu_data)
            session.add(perm)
            await session.flush()
            perm_map[perm.perm_code] = perm
            print(f"[✓] 一级菜单创建完成: {perm.perm_code} (id={perm.id})")

        # 4. 插入二级菜单
        for menu_data in MENU_LEVEL2:
            parent_code = menu_data.pop("parent_code")
            parent_perm = perm_map[parent_code]
            perm = Permission(parent_id=parent_perm.id, **menu_data)
            session.add(perm)
            await session.flush()
            perm_map[perm.perm_code] = perm
            print(f"[✓] 二级菜单创建完成: {perm.perm_code} (id={perm.id}, parent={parent_perm.perm_code})")

        # 5. 插入按钮/API 权限
        for btn_data in BUTTON_PERMS:
            parent_code = btn_data.pop("parent_code")
            parent_perm = perm_map[parent_code]
            perm = Permission(parent_id=parent_perm.id, **btn_data)
            session.add(perm)
            await session.flush()
            perm_map[perm.perm_code] = perm
            print(f"[✓] 按钮权限创建完成: {perm.perm_code} (parent={parent_perm.perm_code})")

        # 6. 绑定角色权限（先显式加载 relationship，避免 lazy load）
        # 消防主管绑定全部权限
        chief_role = role_map["chief"]
        await session.refresh(chief_role, attribute_names=["permissions"])
        for perm in perm_map.values():
            chief_role.permissions.append(perm)
        print(f"[✓] 消防主管绑定全部权限: {len(perm_map)} 个")

        # 消防值班员
        duty_role = role_map["duty_officer"]
        await session.refresh(duty_role, attribute_names=["permissions"])
        for code in ROLE_PERM_MAP["duty_officer"]:
            if code in perm_map:
                duty_role.permissions.append(perm_map[code])
        print(f"[✓] 消防值班员绑定权限: {len(duty_role.permissions)} 个")

        # 维保人员
        maint_role = role_map["maintainer"]
        await session.refresh(maint_role, attribute_names=["permissions"])
        for code in ROLE_PERM_MAP["maintainer"]:
            if code in perm_map:
                maint_role.permissions.append(perm_map[code])
        print(f"[✓] 维保人员绑定权限: {len(maint_role.permissions)} 个")

        # 7. 插入测试用户
        for user_data in USERS_DATA:
            role_codes = user_data.pop("role_codes")
            password = user_data.pop("password")
            user = User(
                **user_data,
                password_hash=get_password_hash(password),
                org_id=org_id,
            )
            session.add(user)
            await session.flush()
            await session.refresh(user, attribute_names=["roles"])
            for code in role_codes:
                user.roles.append(role_map[code])
            print(f"[✓] 用户创建完成: {user.username} (id={user.id}, 角色: {role_codes})")

        await session.commit()
        print("\n[✅] 数据库初始化完成！")
        print("\n可登录的测试账号：")
        print("  ┌──────────┬─────────────┬────────────┐")
        print("  │ 用户名   │ 密码        │ 角色       │")
        print("  ├──────────┼─────────────┼────────────┤")
        print("  │ admin    │ Admin1234   │ 消防主管   │")
        print("  │ duty01   │ Duty1234    │ 消防值班员 │")
        print("  │ maint01  │ Maint1234   │ 维保人员   │")
        print("  └──────────┴─────────────┴────────────┘")


async def main():
    print(f"[*] 使用数据库: {settings.database_url_async}")
    print("[*] 开始初始化数据...\n")
    try:
        await init_database()
    except Exception as e:
        print(f"\n[❌] 初始化失败: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
