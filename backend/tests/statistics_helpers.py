"""
3.9 统计报表测试共用工具

构造统计测试所需的组织/设备/报警/巡检/维修数据。
"""

from datetime import date, datetime, timedelta

from app.core.security import create_access_token, get_password_hash
from app.models.alarm import Alarm
from app.models.device import Device
from app.models.device_type import DeviceType
from app.models.inspection import InspectionPlan, InspectionTask
from app.models.organization import Organization
from app.models.permission import Permission
from app.models.repair import RepairOrder
from app.models.user import Role, User
from sqlalchemy import select


STATISTICS_PERMS = [
    "statistics:view",
    "statistics:export",
]


async def create_org(db, org_name: str, parent=None) -> Organization:
    """创建一个组织节点"""
    org = Organization(
        org_name=org_name,
        org_type="floor" if parent else "building",
        parent_id=parent.id if parent else None,
    )
    db.add(org)
    await db.flush()
    await db.refresh(org)
    return org


async def create_device_type(db) -> DeviceType:
    """创建测试设备类型（幂等）"""
    dt = (await db.execute(
        select(DeviceType).where(DeviceType.type_code == "smoke_test")
    )).scalar_one_or_none()
    if dt is not None:
        return dt
    dt = DeviceType(
        type_code="smoke_test",
        type_name="测试烟感",
        category="detector",
        attribute_schema={},
    )
    db.add(dt)
    await db.flush()
    await db.refresh(dt)
    return dt


async def create_statistics_user(
    db,
    username: str = "statuser",
    perm_codes: list[str] | None = None,
    data_scope: str = "all",
    org: Organization | None = None,
) -> User:
    """创建带统计权限的用户"""
    role = Role(role_code=f"role_{username}", role_name=username, is_builtin=False)
    for code in perm_codes or STATISTICS_PERMS:
        # 幂等：已存在则复用
        perm = (await db.execute(
            select(Permission).where(Permission.perm_code == code)
        )).scalar_one_or_none()
        if perm is None:
            perm = Permission(perm_code=code, perm_name=code, perm_type="button")
            db.add(perm)
        role.permissions.append(perm)

    user = User(
        username=username,
        password_hash=get_password_hash("Stat1234"),
        real_name=username,
        status="active",
        data_scope=data_scope,
        org_id=org.id if org else None,
    )
    user.roles.append(role)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


def auth_headers(user: User) -> dict:
    """生成 Bearer 认证头"""
    token = create_access_token(data={"sub": str(user.id), "jti": f"jti-{user.id}"})
    return {"Authorization": f"Bearer {token}"}


async def create_device(
    db,
    org: Organization,
    device_type: DeviceType,
    code: str = "DEV-001",
    status: str = "normal",
) -> Device:
    """创建设备"""
    dev = Device(
        device_code=code,
        device_name=f"测试设备-{code}",
        type_id=device_type.id,
        org_id=org.id,
        status=status,
        is_deleted=False,
    )
    db.add(dev)
    await db.flush()
    await db.refresh(dev)
    return dev


async def create_alarm(
    db,
    device: Device,
    alarm_type: str = "fire",
    is_drill: bool = False,
    created_at: datetime | None = None,
) -> Alarm:
    """创建报警记录"""
    alarm = Alarm(
        device_id=device.id,
        org_id=device.org_id,
        device_code=device.device_code,
        alarm_type=alarm_type,
        status="pending",
        is_drill=is_drill,
    )
    if created_at:
        alarm.created_at = created_at
    db.add(alarm)
    await db.flush()
    await db.refresh(alarm)
    return alarm


async def create_repair_order(
    db,
    device: Device,
    status: str = "completed",
    order_no: str = "RO-001",
    completed_at: datetime | None = None,
) -> RepairOrder:
    """创建维修工单"""
    ro = RepairOrder(
        order_no=order_no,
        device_id=device.id,
        fault_desc="测试故障描述",
        status=status,
    )
    if completed_at:
        ro.completed_at = completed_at
    db.add(ro)
    await db.flush()
    await db.refresh(ro)
    return ro


async def create_inspection_plan(
    db,
    org: Organization,
    device_type: DeviceType,
    user: User,
) -> InspectionPlan:
    """创建巡检计划"""
    plan = InspectionPlan(
        plan_name="测试巡检计划",
        org_id=org.id,
        device_type_id=device_type.id,
        responsible_user_id=user.id,
        cycle_type="daily",
        start_date=date.today() - timedelta(days=30),
    )
    db.add(plan)
    await db.flush()
    await db.refresh(plan)
    return plan


async def create_inspection_task(
    db,
    plan: InspectionPlan,
    user: User,
    task_date: date,
    status: str = "completed",
) -> InspectionTask:
    """创建巡检任务"""
    task = InspectionTask(
        plan_id=plan.id,
        responsible_user_id=user.id,
        task_date=task_date,
        status=status,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task
