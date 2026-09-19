"""
超时升级扫描（FR-025 / 3.5-B3）验证

计划口径：待确认报警超过 5 分钟未确认 → 升级通知主管。

**结论：该链路当前完全不通，且有两个互相独立的原因。** 两条都以 xfail 记录，
`strict=True` 意味着将来有人修好时这两条会 XPASS 并让套件变红，
提醒移除标记 —— 避免"修好了但没人知道"。

成因一：`alarm.emergency_event` 在 async 会话里被**同步**读取
    （emergency_service.py:177 的 `if alarm.emergency_event:`），
    触发懒加载 → MissingGreenlet。该异常被 EmergencyEscalationTask.scan_loop
    的 try/except 吞掉，只打一行 "[EmergencyEscalation] Scan error"，
    所以生产上表现为"每 60 秒静默失败一次"。

成因二：即便成因一修掉，闸门依旧是空的 —— 扫描只取 `status == "pending"` 的报警，
    而应急事件只在**确认**（pending → confirmed）时创建，
    于是 `alarm.emergency_event` 对扫描到的每一条都恒为 None，
    `escalated_event_ids` 永远为空，函数在 return 0 处结束。
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.emergency import EmergencyEvent, Notification
from app.models.user import Role, User
from app.services.emergency_service import scan_pending_alarms_for_escalation
from tests.device_helpers import create_device_type, create_org
from tests.monitor_helpers import create_alarm, create_device


async def _seed(db, *, with_event: bool):
    org = await create_org(db, "升级大楼")
    device_type = await create_device_type(db)
    device = await create_device(db, org, device_type, "DEV-ESC-001")

    role = Role(role_code="chief", role_name="主管", is_builtin=False)
    db.add(role)
    await db.flush()
    chief = User(
        username="escalation_chief",
        password_hash="x",
        real_name="主管甲",
        status="active",
        data_scope="all",
    )
    chief.roles.append(role)
    db.add(chief)

    overdue = datetime.now() - timedelta(minutes=10)
    alarm = await create_alarm(db, device, "fire", status="pending", pending_since=overdue)
    await db.commit()

    if with_event:
        db.add(
            EmergencyEvent(
                alarm_id=alarm.id, event_no="EV-ESC-001", status="processing", created_by=chief.id
            )
        )
        await db.commit()

    return {"alarm": alarm, "chief": chief}


async def _alarm_has_event(db, alarm_id: int) -> bool:
    """走查询而不是 `alarm.emergency_event`——后者在 async 下会懒加载报错"""
    stmt = select(EmergencyEvent).where(EmergencyEvent.alarm_id == alarm_id)
    return (await db.execute(stmt)).scalars().first() is not None


@pytest.mark.xfail(strict=True, reason="升级扫描在 emergency_service.py:177 懒加载崩溃（成因一）")
async def test_overdue_pending_alarm_notifies_chief(db_session):
    """FR-025 期望行为：超时未确认 → 主管收到一条升级通知"""
    env = await _seed(db_session, with_event=True)

    created = await scan_pending_alarms_for_escalation(db_session)
    await db_session.commit()

    assert created > 0
    rows = list(
        (
            await db_session.execute(
                select(Notification).where(Notification.user_id == env["chief"].id)
            )
        ).scalars().all()
    )
    assert len(rows) == 1
    assert rows[0].module == "emergency"


@pytest.mark.xfail(strict=True, reason="升级扫描在 emergency_service.py:177 懒加载崩溃（成因一）")
async def test_scanner_does_not_raise_on_overdue_alarm(db_session):
    """扫描器至少要先跑得完 —— 现在的表现是被后台任务的 try/except 静默吞掉"""
    await _seed(db_session, with_event=False)

    assert await scan_pending_alarms_for_escalation(db_session) == 0


async def test_pending_alarm_never_has_an_event_in_the_real_flow(db_session):
    """
    成因二（这条**不是**生产缺陷的复现，而是把它的前提钉住）：

    扫描只取 pending 报警，而事件只在确认时创建 —— 二者互斥，
    所以"给待确认超时报警的处置事件发升级通知"这个设计本身走不通。
    """
    env = await _seed(db_session, with_event=False)

    assert env["alarm"].status == "pending"
    assert await _alarm_has_event(db_session, env["alarm"].id) is False
