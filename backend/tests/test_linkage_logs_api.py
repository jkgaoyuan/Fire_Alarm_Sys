"""
联动日志 HTTP 端点契约（3.4-B5）
================================

`tests/test_linkage_logs.py` 测的是 CRUD 层（mock db），**完全不碰 HTTP**，
所以这个文件里的端点级缺陷一直没人看得见：

- 列表端点曾**整个漏掉鉴权**：不带 token 就返回 200 + 数据
  （同文件的 `/{log_id}` 与 `/export` 都要求 `linkage:view`）
- 三个端点的响应形状不一致（已在后续提交统一为信封）

本文件走真实 ASGI 调用，覆盖「鉴权」与「响应信封」两件事。
"""

import pytest

from tests.auth_helpers import auth_headers, create_user_with_perms


async def make_linkage_user(db_session, username: str, perm_codes: list[str]):
    """建一个只持有指定权限码的用户（通用构造器见 tests/auth_helpers.py）"""
    return await create_user_with_perms(db_session, username, perm_codes)


def headers_for(user) -> dict:
    return auth_headers(user)


# ==================== 鉴权 ====================

@pytest.mark.asyncio
async def test_list_requires_authentication(client):
    """
    TC-LOG-001: 未认证访问联动日志列表必须 401。

    不修会怎样：该端点曾无任何鉴权依赖，未带 token 直接返回 200 + 数据。
    日志含 alarm_id / plan_id / target_device_id / result_message，
    等于把跨组织的业务数据对外公开——而同文件的详情与导出端点都是 401。
    """
    resp = await client.get("/api/v1/alarm-linkage-logs")

    assert resp.status_code == 401, f"未认证却拿到 {resp.status_code}"


@pytest.mark.asyncio
async def test_list_requires_view_permission(client, db_session):
    """TC-LOG-002: 已登录但缺 linkage:view 仍是 403，不是 401"""
    user = await make_linkage_user(db_session, "lg_noperm", ["device:view"])

    resp = await client.get(
        "/api/v1/alarm-linkage-logs", headers=headers_for(user)
    )

    assert resp.status_code == 403
    assert "缺少权限" in resp.json()["message"]


@pytest.mark.asyncio
async def test_sibling_endpoints_keep_their_auth(client):
    """
    TC-LOG-003: 同文件的详情与导出端点鉴权不得被顺手改掉（回归护栏）。

    列表端点漏鉴权很可能就是「复制同文件代码时删掉了 dependencies」，
    所以固定住另外两个，防止修复时反向踩踏。
    """
    assert (await client.get("/api/v1/alarm-linkage-logs/1")).status_code == 401
    assert (await client.get("/api/v1/alarm-linkage-logs/export")).status_code == 401


# ==================== 响应信封 ====================

@pytest.mark.asyncio
async def test_list_returns_envelope(client, db_session):
    """
    TC-LOG-004: 列表按统一信封返回 {code, message, data}。

    不修会怎样：此前返回裸 {items,total,page,page_size}。前端拦截器两种形状
    都放行，组件按 res.data.items 读会拿到 undefined，被 `|| {}` 兜底后
    页面显示空表——**不报错**。维修统计页全 0 就是同一类问题。
    """
    user = await make_linkage_user(db_session, "lg_view", ["linkage:view"])

    resp = await client.get("/api/v1/alarm-linkage-logs", headers=headers_for(user))
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["message"] == "success"
    # 分页字段必须落在 data 里，而不是顶层
    assert set(body["data"]) >= {"items", "total", "page", "page_size"}
    assert "items" not in body, "裸字段又漏到顶层了"


@pytest.mark.asyncio
async def test_detail_returns_envelope(client, db_session):
    """TC-LOG-005: 详情同样走信封；资源不存在时是 404 而非 200 空体"""
    user = await make_linkage_user(db_session, "lg_view2", ["linkage:view"])
    headers = headers_for(user)

    resp = await client.get("/api/v1/alarm-linkage-logs/999999", headers=headers)
    assert resp.status_code == 404


# ==================== 展示字段（预案名 / 设备名 / 是否演练） ====================
#
# 前端「联动日志」页此前根本不存在，所以这些字段一直没被要求过；页面补上后
# 只有 plan_id / target_device_id 是不够的（还得再查一次才能显示名字），
# 而「这条联动是真火警跑的、还是模拟测试跑的」更是必须能分辨。

@pytest.mark.asyncio
async def test_list_carries_display_fields(client, db_session):
    """TC-LOG-006: 列表带出预案名与目标设备名"""
    from app.models.linkage import AlarmLinkageLog, LinkagePlan
    from app.models.organization import Organization
    from tests.device_helpers import make_device

    org = Organization(org_name="日志区", org_type="zone")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    device = await make_device(db_session, org_id=org.id, device_name="排烟风机-01")
    plan = LinkagePlan(
        plan_name="一层疏散预案", org_id=org.id, actions=[], is_enabled=True, created_by=1
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)

    db_session.add(AlarmLinkageLog(
        plan_id=plan.id,
        target_device_id=device.id,
        action_type="start_exhaust",
        status="success",
        is_simulation=False,
    ))
    await db_session.commit()

    user = await make_linkage_user(db_session, "lg_fields", ["linkage:view"])
    resp = await client.get("/api/v1/alarm-linkage-logs", headers=headers_for(user))
    item = resp.json()["data"]["items"][0]

    assert item["plan_name"] == "一层疏散预案"
    assert item["target_device_name"] == "排烟风机-01"
    assert item["is_drill"] is False


@pytest.mark.asyncio
async def test_list_marks_drill_logs(client, db_session):
    """
    TC-LOG-007: 演练告警产生的日志要标出来。

    日志表没有 is_drill，取自关联告警。不标的话，模拟测试跑出来的记录
    跟真实火警产生的长得一模一样，事后回看根本分不清——而这正是这个页面
    存在的意义。
    """
    from app.models.alarm import Alarm
    from app.models.linkage import AlarmLinkageLog, LinkagePlan
    from app.models.organization import Organization
    from tests.device_helpers import make_device

    org = Organization(org_name="演练日志区", org_type="zone")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    device = await make_device(db_session, org_id=org.id)
    plan = LinkagePlan(
        plan_name="演练来源预案", org_id=org.id, actions=[], is_enabled=True, created_by=1
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)

    alarm = Alarm(
        device_id=device.id, org_id=org.id, alarm_type="fire",
        status="pending", is_drill=True,
    )
    db_session.add(alarm)
    await db_session.commit()
    await db_session.refresh(alarm)

    db_session.add(AlarmLinkageLog(
        alarm_id=alarm.id, plan_id=plan.id, action_type="start_exhaust",
        status="success", is_simulation=False,
    ))
    await db_session.commit()

    user = await make_linkage_user(db_session, "lg_drill", ["linkage:view"])
    resp = await client.get("/api/v1/alarm-linkage-logs", headers=headers_for(user))
    item = resp.json()["data"]["items"][0]

    assert item["is_drill"] is True, "演练告警产生的日志没被标记"


@pytest.mark.asyncio
async def test_detail_carries_display_fields(client, db_session):
    """TC-LOG-008: 详情同样带出展示字段（详情页不能比列表少信息）"""
    from app.models.linkage import AlarmLinkageLog, LinkagePlan
    from app.models.organization import Organization

    org = Organization(org_name="详情区", org_type="zone")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    plan = LinkagePlan(
        plan_name="详情预案", org_id=org.id, actions=[], is_enabled=True, created_by=1
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)

    log = AlarmLinkageLog(
        plan_id=plan.id, action_type="broadcast", status="failed",
        result_message="设备无响应", is_simulation=False,
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)

    user = await make_linkage_user(db_session, "lg_detail", ["linkage:view"])
    resp = await client.get(f"/api/v1/alarm-linkage-logs/{log.id}", headers=headers_for(user))
    data = resp.json()["data"]

    assert data["plan_name"] == "详情预案"
    assert data["result_message"] == "设备无响应"
    assert data["is_drill"] is False
