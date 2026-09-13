"""
维修工单的数据权限范围（3.7 FR-042）
====================================

**刻意不复用 `user_service.apply_data_scope`**：那个函数对 `self` 锚 `created_by`、
对 `dept` 锚模型自身的 `org_id`，而 `RepairOrder` 只有 `created_by`、**没有 `org_id`**
（组织要经 `device_id → Device.org_id` 折算）。`apply_data_scope` 用 `hasattr`
守卫，缺属性时**原样返回查询**——调用看起来生效，实际谁都能看全部，
比不调更危险。同样的坑在 `InspectionTask` 上踩过一次。

工单的口径：
- `all`  -> 不过滤
- `self` -> 与我有关的工单：我报的、我修的、我验收的、我建的
           （工单是多方协作的对象，只按 `created_by` 过滤会让维修人看不到
            派给自己的单——这正是要避免的）
- `dept` -> 设备所在区域属于本部门及子部门的工单
"""

from typing import Optional

from sqlalchemy import false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.device import Device
from app.models.organization import Organization
from app.models.repair import RepairOrder
from app.models.user import User


async def repair_scope_condition(
    user: User, db: AsyncSession
) -> Optional[ColumnElement]:
    """
    返回该用户可见工单的过滤条件；`None` 表示不受限（data_scope='all'）。

    条件是**单个表达式**，调用方把它拼进既有的 where 里即可——
    列表的 count 与 items 必须用同一个条件，否则会出现「总数 2、只回 1 条」。
    """
    if user.data_scope == "all":
        return None

    if user.data_scope == "dept":
        if user.org_id is None:
            return false()

        # 递归 CTE 取本部门及全部子部门（口径与 P1-007 对 devices 一致）
        cte = (
            select(Organization.id)
            .where(Organization.id == user.org_id)
            .cte(recursive=True)
        )
        cte = cte.union_all(
            select(Organization.id).where(Organization.parent_id == cte.c.id)
        )
        org_ids = [row[0] for row in (await db.execute(select(cte.c.id))).all()]
        if not org_ids:
            return false()

        device_ids = select(Device.id).where(Device.org_id.in_(org_ids))
        return RepairOrder.device_id.in_(device_ids)

    # self（含未识别的取值，取最小可见权限）
    return or_(
        RepairOrder.created_by == user.id,
        RepairOrder.reporter_id == user.id,
        RepairOrder.repairer_id == user.id,
        RepairOrder.acceptor_id == user.id,
    )
