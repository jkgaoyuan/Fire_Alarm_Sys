"""
联动引擎端到端（3.4-B2）
========================

**在这之前，全仓库没有任何一条用例真正跑过 `linkage_engine.on_alarm_created`。**
既有的 `tests/test_linkage_engine.py` 名不副实——它只单测 `execute_action` 的
返回值，以及一个内存字典的形状，引擎的匹配/执行/广播三段全都没覆盖。

于是下面这个缺陷活到了现在：`linkage_engine_service.py` 里两处广播调用
`await settings.get_redis()`，而 `Settings` **根本没有这个方法**（全仓库只有
这两处这么写，其余一律用 `app/db/redis.py` 的 `get_redis_pool()`）。广播调用
位于 `_execute_log` 的 `try` 内，于是**执行成功的动作被 except 改写成失败**：

    status='failed'  msg="执行异常：'Settings' object has no attribute 'get_redis'"

`execute_action` 有 90% 成功率，但库里永远只有失败——**每一次真实火警的联动
动作在日志里都显示失败**，而「失败」本该触发的次级告警也是坏的
（`_create_secondary_alarm` 传 `device=None` 且 `alarm_type="linkage_failed"`
不在 `ALARM_TYPE_PROFILE` 里，双重异常被 `except` 吞掉），所以失败之后
连带的那条告警也不存在。整条链路是「静默地什么都不对」。

本文件的用例把这条链路的行为钉死。
"""

import pytest
from sqlalchemy import select

from app.models.alarm import Alarm
from app.models.linkage import AlarmLinkageLog, LinkagePlan
from app.services.linkage_engine_service import linkage_engine
from tests.device_helpers import create_org, make_device

ENGINE = "app.services.linkage_engine_service"


async def _plan(db, org_id, actions=None, **kwargs):
    plan = LinkagePlan(
        plan_name=kwargs.pop("plan_name", "引擎用例预案"),
        org_id=org_id,
        actions=actions if actions is not None else [
            {"action_type": "start_exhaust", "params": {}}
        ],
        is_enabled=True,
        created_by=1,
        **kwargs,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


async def _fire_alarm(db, device):
    """走真实入口建一条火警（与设备上报同一条路）"""
    from app.services.alarm_service import raise_alarm

    alarm, created = await raise_alarm(db, device, "fire")
    await db.commit()
    assert created, "测试前提：应是新建的报警"
    return alarm


def _stub_execute(monkeypatch, status, message):
    """把动作执行固定成确定结果——真实的 execute_action 有 0.1 随机失败率"""
    async def fake(action, log, failure_rate=0.1):
        return status, message

    monkeypatch.setattr(f"{ENGINE}.execute_action", fake)


async def _logs(db):
    result = await db.execute(select(AlarmLinkageLog))
    return list(result.scalars().all())


# ==================== 成功路径 ====================

@pytest.mark.asyncio
async def test_successful_action_stays_success(db_session, monkeypatch):
    """
    TC-LE-001: 动作执行成功时，日志状态必须是 success。

    **这条是本次最关键的回归护栏。** 修前：`_broadcast_executed` 调
    `settings.get_redis()` 抛 AttributeError，被 `_execute_log` 的 except 捕获，
    把刚写好的 `status="success"` 覆盖成 `"failed"`，`result_message` 里
    留下那句 AttributeError。动作明明执行了，日志却说没执行。

    修法是广播改用 `alarm_service.publish`（它接受 redis 句柄、自己吞异常，
    是仓库里既有的模式——推送失败绝不能回滚已提交的消防业务数据）。
    """
    org = await create_org(db_session, "引擎成功区")
    device = await make_device(db_session, org_id=org.id)
    await _plan(db_session, org.id)
    alarm = await _fire_alarm(db_session, device)

    _stub_execute(monkeypatch, "success", "排烟风机已启动")
    await linkage_engine.on_alarm_created(db_session, alarm)

    logs = await _logs(db_session)
    assert len(logs) == 1, f"应产生 1 条联动日志，实际 {len(logs)}"

    log = logs[0]
    assert log.status == "success", (
        f"动作已成功执行，日志却是 {log.status!r}：{log.result_message!r}"
    )
    assert "get_redis" not in (log.result_message or ""), (
        f"广播的内部错误污染了执行结果：{log.result_message!r}"
    )
    assert log.alarm_id == alarm.id


@pytest.mark.asyncio
async def test_broadcast_failure_does_not_flip_status(db_session, monkeypatch):
    """
    TC-LE-002: 广播通道不可用时，也不得把执行成功改成失败。

    把取 redis 的入口打成一个必炸的函数，模拟推送侧故障。
    执行结果的判定依据应是「动作跑没跑」，不该被推送链路连坐。
    """
    org = await create_org(db_session, "引擎广播故障区")
    device = await make_device(db_session, org_id=org.id)
    await _plan(db_session, org.id, plan_name="广播故障预案")
    alarm = await _fire_alarm(db_session, device)

    async def boom():
        raise RuntimeError("redis 不可达")

    monkeypatch.setattr(f"{ENGINE}.get_redis_pool", boom)
    _stub_execute(monkeypatch, "success", "排烟风机已启动")

    await linkage_engine.on_alarm_created(db_session, alarm)

    logs = await _logs(db_session)
    assert logs[0].status == "success", (
        f"推送故障把执行结果连坐了：{logs[0].status!r} {logs[0].result_message!r}"
    )


# ==================== 失败路径 ====================

@pytest.mark.asyncio
async def test_failed_action_creates_secondary_alarm(db_session, monkeypatch):
    """
    TC-LE-003: 动作执行失败时，必须真的生成次级告警。

    修前：`_create_secondary_alarm` 调用
    `raise_alarm(db, device=None, alarm_type="linkage_failed", ...)`——
    `device` 是必填且函数第一步就取 `device.id`，会 AttributeError；
    而 `alarm_type="linkage_failed"` 也不在 `ALARM_TYPE_PROFILE` 里，
    本来就会 400。两个错误都被 `except Exception: return None` 吞掉，
    于是「联动失败产生次级告警」这条设计**从未生效过**，且不留任何痕迹。
    """
    org = await create_org(db_session, "引擎失败区")
    device = await make_device(db_session, org_id=org.id)
    await _plan(db_session, org.id, plan_name="失败预案")
    alarm = await _fire_alarm(db_session, device)

    _stub_execute(monkeypatch, "failed", "设备无响应")
    await linkage_engine.on_alarm_created(db_session, alarm)

    logs = await _logs(db_session)
    assert logs[0].status == "failed"

    result = await db_session.execute(
        select(Alarm).where(Alarm.id != alarm.id)
    )
    secondary = list(result.scalars().all())
    assert len(secondary) == 1, (
        f"联动失败应产生 1 条次级告警，实际 {len(secondary)} 条"
    )
    assert "失败预案" in (secondary[0].location_description or ""), (
        f"次级告警未说明来源预案：{secondary[0].location_description!r}"
    )


# ==================== 匹配规则 ====================

@pytest.mark.asyncio
async def test_plan_in_other_org_does_not_match(db_session, monkeypatch):
    """TC-LE-004: 区域对不上的预案不得被触发（匹配的第一道闸）"""
    org_a = await create_org(db_session, "甲区")
    org_b = await create_org(db_session, "乙区")
    device = await make_device(db_session, org_id=org_a.id)
    await _plan(db_session, org_b.id, plan_name="乙区预案")
    alarm = await _fire_alarm(db_session, device)

    _stub_execute(monkeypatch, "success", "ok")
    await linkage_engine.on_alarm_created(db_session, alarm)

    assert await _logs(db_session) == []


# ==================== 「允许模拟测试」开关 ====================

async def _drill_alarm(db, device):
    """建一条演练告警（模拟测试走的入口）"""
    from app.services.alarm_service import raise_alarm

    alarm, created = await raise_alarm(db, device, "fire", is_drill=True)
    await db.commit()
    assert created, "测试前提：应是新建的演练告警"
    return alarm


@pytest.mark.asyncio
async def test_drill_alarm_skips_plan_with_simulation_disabled(db_session, monkeypatch):
    """
    TC-LE-005: 关了「允许模拟测试」的预案，不得被演练告警触发。

    开关必须在这里生效而不是只在入口挡一下：否则在甲预案上关掉开关、
    去点乙预案的「模拟测试」，甲预案照样会被这条演练告警带响——
    那样开关就只是装饰。
    """
    org = await create_org(db_session, "开关区")
    device = await make_device(db_session, org_id=org.id)
    await _plan(db_session, org.id, plan_name="禁模拟预案", is_simulation_allowed=False)
    alarm = await _drill_alarm(db_session, device)

    _stub_execute(monkeypatch, "success", "ok")
    await linkage_engine.on_alarm_created(db_session, alarm)

    assert await _logs(db_session) == [], "禁用了模拟的预案被演练告警触发了"


@pytest.mark.asyncio
async def test_drill_alarm_still_fires_enabled_plan(db_session, monkeypatch):
    """TC-LE-006: 开关为真（默认）时，演练告警照常触发——别把开关做成永远拦"""
    org = await create_org(db_session, "开关放行区")
    device = await make_device(db_session, org_id=org.id)
    await _plan(db_session, org.id, plan_name="允许模拟预案", is_simulation_allowed=True)
    alarm = await _drill_alarm(db_session, device)

    _stub_execute(monkeypatch, "success", "ok")
    await linkage_engine.on_alarm_created(db_session, alarm)

    logs = await _logs(db_session)
    assert len(logs) == 1
    assert logs[0].status == "success"


@pytest.mark.asyncio
async def test_real_alarm_ignores_simulation_switch(db_session, monkeypatch):
    """
    TC-LE-007: 真实火警不受该开关影响。

    开关管的是「模拟测试」，不是「这条预案要不要联动」——真实火警该触发就得触发，
    否则关掉开关等于静默停用了一条消防联动预案，那是很危险的误用。
    """
    org = await create_org(db_session, "真实报警区")
    device = await make_device(db_session, org_id=org.id)
    await _plan(db_session, org.id, plan_name="禁模拟但仍联动", is_simulation_allowed=False)
    alarm = await _fire_alarm(db_session, device)

    _stub_execute(monkeypatch, "success", "ok")
    await linkage_engine.on_alarm_created(db_session, alarm)

    logs = await _logs(db_session)
    assert len(logs) == 1, "真实火警被「允许模拟测试」开关误拦了"
    assert logs[0].status == "success"
