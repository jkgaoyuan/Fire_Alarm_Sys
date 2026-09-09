#!/usr/bin/env python3
"""
数据库初始化脚本
---------------
用途：在真实 PostgreSQL 环境中创建表并插入预置数据（角色、权限、菜单、设备类型、测试用户）
脚本幂等，可重复执行：已存在的记录会被跳过，仅补齐缺失项（容器每次启动都会执行）

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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models.base import Base
from app.models.device_type import DeviceType
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
    {"perm_code": "system:log", "perm_name": "登录日志", "perm_type": "menu", "route_path": "/system/login-log", "component": "views/system/LoginLog.vue", "icon": "Document", "sort_order": 3, "parent_code": "system:management"},
    {"perm_code": "system:org", "perm_name": "组织管理", "perm_type": "menu", "route_path": "/system/org", "component": "views/system/Org.vue", "icon": "OfficeBuilding", "sort_order": 4, "parent_code": "system:management"},
]

# 按钮/API 权限（parent_code 为关联的业务菜单）
BUTTON_PERMS = [
    # 监控大屏
    {"perm_code": "monitor:view",    "perm_name": "查看监控",     "perm_type": "button", "parent_code": "monitor:dashboard"},
    {"perm_code": "monitor:confirm", "perm_name": "确认监控告警", "perm_type": "button", "parent_code": "monitor:dashboard"},
    {"perm_code": "monitor:config",  "perm_name": "配置平面图",   "perm_type": "button", "parent_code": "monitor:dashboard"},
    # 报警中心
    {"perm_code": "alarm:view",    "perm_name": "查看报警", "perm_type": "button", "parent_code": "alarm:center"},
    {"perm_code": "alarm:confirm", "perm_name": "确认报警", "perm_type": "button", "parent_code": "alarm:center"},
    {"perm_code": "alarm:silence", "perm_name": "报警消音", "perm_type": "button", "parent_code": "alarm:center"},
    {"perm_code": "alarm:reset",   "perm_name": "系统复位", "perm_type": "button", "parent_code": "alarm:center"},
    {"perm_code": "alarm:handle",  "perm_name": "处置报警", "perm_type": "button", "parent_code": "alarm:center"},
    # 设备档案
    {"perm_code": "device:view",   "perm_name": "查看设备", "perm_type": "button", "parent_code": "device:archive"},
    {"perm_code": "device:create", "perm_name": "新增设备", "perm_type": "button", "parent_code": "device:archive"},
    {"perm_code": "device:update", "perm_name": "编辑设备", "perm_type": "button", "parent_code": "device:archive"},
    {"perm_code": "device:delete", "perm_name": "删除设备", "perm_type": "button", "parent_code": "device:archive"},
    {"perm_code": "device:retire", "perm_name": "退役设备", "perm_type": "button", "parent_code": "device:archive"},
    {"perm_code": "device:repair", "perm_name": "维修记录", "perm_type": "button", "parent_code": "device:archive"},
    # 联动预案
    {"perm_code": "linkage:view",      "perm_name": "查看预案",     "perm_type": "button", "parent_code": "linkage:plan"},
    {"perm_code": "linkage:create",    "perm_name": "新增预案",     "perm_type": "button", "parent_code": "linkage:plan"},
    {"perm_code": "linkage:update",    "perm_name": "编辑预案",     "perm_type": "button", "parent_code": "linkage:plan"},
    {"perm_code": "linkage:delete",    "perm_name": "删除预案",     "perm_type": "button", "parent_code": "linkage:plan"},
    {"perm_code": "linkage:execute",   "perm_name": "执行联动",     "perm_type": "button", "parent_code": "linkage:plan"},
    {"perm_code": "linkage:simulate",  "perm_name": "模拟测试",     "perm_type": "button", "parent_code": "linkage:plan"},
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
    # 登录日志
    {"perm_code": "system:log:view", "perm_name": "查看登录日志", "perm_type": "button", "parent_code": "system:log"},
    # 组织管理（P2-010）
    {"perm_code": "system:org:create", "perm_name": "新增组织", "perm_type": "button", "parent_code": "system:org"},
    {"perm_code": "system:org:update", "perm_name": "编辑组织", "perm_type": "button", "parent_code": "system:org"},
    {"perm_code": "system:org:delete", "perm_name": "删除组织", "perm_type": "button", "parent_code": "system:org"},
]

# 角色权限映射
ROLE_PERM_MAP = {
    "duty_officer": [
        # 菜单
        "monitor:dashboard", "alarm:center", "device:archive", "statistics:report",
        # 按钮
        "monitor:view", "monitor:confirm",
        "alarm:view", "alarm:confirm", "alarm:silence", "alarm:reset", "alarm:handle",
        "device:view",
        "statistics:partial",
        # 联动预案（值班员只能查看和执行）
        "linkage:view", "linkage:execute",
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

# 预置 8 种设备类型（FR-007）
# attribute_schema 采用计划 5.1 的简化格式，字段 type 仅用 string / number / select
# （计划第八节降险策略：复杂类型延期至 P1）
DEVICE_TYPES_DATA = [
    {
        "type_code": "smoke_detector",
        "type_name": "烟感探测器",
        "category": "detector",
        "attribute_schema": {
            "sensitivity": {"label": "灵敏度", "type": "select", "options": ["高", "中", "低"]},
            "detection_area": {"label": "探测面积", "type": "number", "unit": "㎡"},
            "working_voltage": {"label": "工作电压", "type": "string", "unit": "V"},
        },
    },
    {
        "type_code": "heat_detector",
        "type_name": "温感探测器",
        "category": "detector",
        "attribute_schema": {
            "alarm_temp": {"label": "报警温度", "type": "number", "unit": "℃"},
            "response_type": {"label": "响应类型", "type": "select", "options": ["定温", "差温", "差定温"]},
        },
    },
    {
        "type_code": "manual_alarm",
        "type_name": "手动报警按钮",
        "category": "alarm",
        "attribute_schema": {
            "with_phone_jack": {"label": "电话插孔", "type": "select", "options": ["有", "无"]},
            "material": {"label": "面板材质", "type": "string"},
        },
    },
    {
        "type_code": "hydrant",
        "type_name": "消火栓",
        "category": "extinguishing",
        "attribute_schema": {
            "outlet_count": {"label": "出水口数量", "type": "number", "unit": "个"},
            "design_flow": {"label": "设计流量", "type": "number", "unit": "L/s"},
            "has_nozzle": {"label": "是否配水枪", "type": "select", "options": ["是", "否"]},
        },
    },
    {
        "type_code": "sprinkler",
        "type_name": "喷淋头",
        "category": "extinguishing",
        "attribute_schema": {
            "k_value": {"label": "流量系数 K", "type": "number"},
            "action_temp": {"label": "动作温度", "type": "number", "unit": "℃"},
            "spray_type": {"label": "喷洒方式", "type": "select", "options": ["直立", "下垂", "边墙"]},
        },
    },
    {
        "type_code": "exhaust_fan",
        "type_name": "排烟风机",
        "category": "exhaust",
        "attribute_schema": {
            "power": {"label": "功率", "type": "number", "unit": "kW"},
            "air_volume": {"label": "风量", "type": "number", "unit": "m³/h"},
            "noise": {"label": "噪声", "type": "number", "unit": "dB"},
        },
    },
    {
        "type_code": "fire_door",
        "type_name": "防火门",
        "category": "door",
        "attribute_schema": {
            "fire_rating": {"label": "耐火等级", "type": "select", "options": ["甲级", "乙级", "丙级"]},
            "open_direction": {"label": "开启方向", "type": "select", "options": ["左开", "右开", "双开"]},
            "door_width": {"label": "门洞宽度", "type": "number", "unit": "mm"},
        },
    },
    {
        "type_code": "emergency_light",
        "type_name": "应急照明",
        "category": "lighting",
        "attribute_schema": {
            "battery_duration": {"label": "持续供电时间", "type": "number", "unit": "min"},
            "luminous_flux": {"label": "光通量", "type": "number", "unit": "lm"},
            "charge_type": {"label": "供电方式", "type": "select", "options": ["集中", "独立"]},
        },
    },
]

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


async def get_or_create(session, model, defaults=None, **filters):
    """按唯一键复用已有记录，仅在缺失时插入，返回 (实例, 是否新建)"""
    stmt = select(model).filter_by(**filters)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is not None:
        return obj, False
    obj = model(**{**filters, **(defaults or {})})
    session.add(obj)
    await session.flush()
    return obj, True


async def init_database():
    """初始化数据库：建表 + 插入预置数据"""
    async with engine.begin() as conn:
        # 创建所有表（如果已存在则跳过）
        await conn.run_sync(Base.metadata.create_all)
        print("[✓] 数据库表创建完成（已存在则跳过）")

    async with AsyncSessionLocal() as session:
        # 1. 插入组织架构根节点
        org, created = await get_or_create(
            session,
            Organization,
            defaults={"sort_order": 0},
            org_name="消防管理中心",
            org_type="building",
        )
        org_id = org.id
        print(f"[✓] 组织架构根节点{'创建完成' if created else '已存在，跳过'}: id={org_id}")

        # 2. 插入角色
        role_map = {}  # role_code -> Role 对象
        for role_data in ROLES_DATA:
            role, created = await get_or_create(
                session, Role, defaults=dict(role_data), role_code=role_data["role_code"]
            )
            role_map[role.role_code] = role
            print(f"[✓] 角色{'创建完成' if created else '已存在，跳过'}: {role.role_code} (id={role.id})")

        # 3. 插入一级菜单
        perm_map = {}  # perm_code -> Permission 对象
        for menu_data in MENU_LEVEL1:
            perm, created = await get_or_create(
                session, Permission, defaults=dict(menu_data), perm_code=menu_data["perm_code"]
            )
            perm_map[perm.perm_code] = perm
            print(f"[✓] 一级菜单{'创建完成' if created else '已存在，跳过'}: {perm.perm_code}")

        # 4. 插入二级菜单
        for menu_data in MENU_LEVEL2:
            data = dict(menu_data)
            parent_code = data.pop("parent_code")
            parent_perm = perm_map[parent_code]
            perm, created = await get_or_create(
                session,
                Permission,
                defaults={**data, "parent_id": parent_perm.id},
                perm_code=data["perm_code"],
            )
            perm_map[perm.perm_code] = perm
            print(f"[✓] 二级菜单{'创建完成' if created else '已存在，跳过'}: {perm.perm_code} (parent={parent_perm.perm_code})")

        # 5. 插入按钮/API 权限
        for btn_data in BUTTON_PERMS:
            data = dict(btn_data)
            parent_code = data.pop("parent_code")
            parent_perm = perm_map[parent_code]
            perm, created = await get_or_create(
                session,
                Permission,
                defaults={**data, "parent_id": parent_perm.id},
                perm_code=data["perm_code"],
            )
            perm_map[perm.perm_code] = perm
            print(f"[✓] 按钮权限{'创建完成' if created else '已存在，跳过'}: {perm.perm_code} (parent={parent_perm.perm_code})")

        # 6. 绑定角色权限（先显式加载 relationship，避免 lazy load）
        def bind_permissions(role, perms):
            missing = [perm for perm in perms if perm not in role.permissions]
            role.permissions.extend(missing)
            return len(missing)

        # 消防主管绑定全部权限
        chief_role = role_map["chief"]
        await session.refresh(chief_role, attribute_names=["permissions"])
        added = bind_permissions(chief_role, list(perm_map.values()))
        print(f"[✓] 消防主管权限绑定: 新增 {added} 个，共 {len(chief_role.permissions)} 个")

        # 消防值班员
        duty_role = role_map["duty_officer"]
        await session.refresh(duty_role, attribute_names=["permissions"])
        added = bind_permissions(duty_role, [perm_map[c] for c in ROLE_PERM_MAP["duty_officer"] if c in perm_map])
        print(f"[✓] 消防值班员权限绑定: 新增 {added} 个，共 {len(duty_role.permissions)} 个")

        # 维保人员
        maint_role = role_map["maintainer"]
        await session.refresh(maint_role, attribute_names=["permissions"])
        added = bind_permissions(maint_role, [perm_map[c] for c in ROLE_PERM_MAP["maintainer"] if c in perm_map])
        print(f"[✓] 维保人员权限绑定: 新增 {added} 个，共 {len(maint_role.permissions)} 个")

        # 6.5 插入预置设备类型（幂等：已存在的 type_code 跳过，支持脚本重跑）
        result = await session.execute(select(DeviceType.type_code))
        existing_type_codes = {row[0] for row in result.all()}
        created_types = 0
        for type_data in DEVICE_TYPES_DATA:
            if type_data["type_code"] in existing_type_codes:
                continue
            session.add(DeviceType(**type_data))
            created_types += 1
        await session.flush()
        print(
            f"[✓] 设备类型预置完成: 新增 {created_types} 种，"
            f"跳过已存在 {len(DEVICE_TYPES_DATA) - created_types} 种"
        )

        # 7. 插入测试用户（已存在则只补齐角色绑定，不重置密码）
        for user_data in USERS_DATA:
            data = dict(user_data)
            role_codes = data.pop("role_codes")
            password = data.pop("password")
            user, created = await get_or_create(
                session,
                User,
                defaults={**data, "password_hash": get_password_hash(password), "org_id": org_id},
                username=data["username"],
            )
            await session.refresh(user, attribute_names=["roles"])
            missing_roles = [role_map[code] for code in role_codes if role_map[code] not in user.roles]
            user.roles.extend(missing_roles)
            print(
                f"[✓] 用户{'创建完成' if created else '已存在，跳过'}: {user.username} "
                f"(id={user.id}, 角色: {role_codes}, 新增绑定 {len(missing_roles)})"
            )

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
