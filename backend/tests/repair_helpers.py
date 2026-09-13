"""
维修域测试构造器（testing-guidelines 第三节：域内构造器放 tests/<域>_helpers.py）

不要在用例里手写 RepairOrder(...) 字面量，字段一多必然与模型漂移。
组织与设备类型复用 `tests/device_helpers.py`，那些是跨域共用的。
"""

from uuid import uuid4

from app.models.device import Device
from app.models.repair import RepairOrder
from tests.auth_helpers import auth_headers, create_user_with_perms  # noqa: F401
from tests.device_helpers import create_org  # noqa: F401


async def make_device(db, *, org_id: int, device_code: str | None = None) -> Device:
    """建一台设备（绕过 API 直接落库，只为给工单提供 device_id）"""
    device = Device(
        device_code=device_code or f"DEV-{uuid4().hex[:8].upper()}",
        device_name="测试设备",
        org_id=org_id,
        status="normal",
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


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
