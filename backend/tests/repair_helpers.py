"""
维修域测试构造器（testing-guidelines 第三节：域内构造器放 tests/<域>_helpers.py）

不要在用例里手写 RepairOrder(...) 字面量，字段一多必然与模型漂移。
组织与设备类型复用 `tests/device_helpers.py`，那些是跨域共用的。
"""

from uuid import uuid4

from app.models.repair import RepairOrder
from tests.auth_helpers import auth_headers, create_user_with_perms  # noqa: F401
from tests.device_helpers import create_org, make_device  # noqa: F401


async def make_repair_order(
    db,
    *,
    device_id: int,
    created_by: int | None = None,
    reporter_id: int | None = None,
    repairer_id: int | None = None,
    acceptor_id: int | None = None,
    status: str = "pending",
) -> RepairOrder:
    """
    建一条维修工单。

    `order_no` 有唯一约束，故用随机后缀——跨用例复用固定编号会撞。
    """
    order = RepairOrder(
        order_no=f"RO-{uuid4().hex[:10].upper()}",
        device_id=device_id,
        fault_desc="测试故障描述",
        status=status,
        reporter_id=reporter_id if reporter_id is not None else created_by,
        repairer_id=repairer_id,
        acceptor_id=acceptor_id,
        created_by=created_by,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order
