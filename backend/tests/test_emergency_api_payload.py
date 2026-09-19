"""
应急事件 API 载荷序列化测试

`GET /emergency/events` 等端点把 **ORM 对象直接塞进 dict 返回**，而路由声明的是
`response_model=dict` —— Pydantic 不会代为转换，于是
`PydanticSerializationError: Unable to serialize unknown type: EmergencyEvent` → **500**。

这个缺陷在事件表为空时永远不会暴露：`items` 是空列表，没有任何对象需要序列化。
所以它与「确认不建事件」是同一枚硬币的两面 —— 事件一旦真的建出来，列表页立刻 500，
用户依旧「在应急处置里看不到任何事件」。

P1-013 把 emergency 域从「零覆盖」恢复成可测之后，这类"空表掩盖的缺陷"才第一次可被钉住。
"""

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.emergency import EmergencyEvent, EmergencyTimeline
from app.services.emergency_service import create_emergency_event
from tests.device_helpers import create_device_type, create_device_user, create_org
from tests.monitor_helpers import create_alarm, create_device


@pytest.fixture
async def seeded(db_session):
    """一个报警 + 一条真实火警产生的事件（含 2 个时间轴节点）"""
    org = await create_org(db_session, "应急载荷大楼")
    device_type = await create_device_type(db_session)
    device = await create_device(db_session, org, device_type, "DEV-EV-001")
    user = await create_device_user(
        db_session,
        username="emergency_viewer",
        perm_codes=[
            "emergency:view",
            "emergency:resolve",
            "emergency:close",
            "emergency:timeline",
        ],
        data_scope="all",
    )
    alarm = await create_alarm(db_session, device, "fire", status="confirmed")
    event = await create_emergency_event(db_session, alarm.id, user.id)
    await db_session.commit()

    token = create_access_token(data={"sub": str(user.id), "jti": "jti-emergency-payload"})
    return {"event": event, "alarm": alarm, "user": user, "headers": {"Authorization": f"Bearer {token}"}}


async def test_event_list_serializes_orm_rows(client, seeded):
    """列表端点必须把 ORM 行转成可序列化载荷 —— 否则有数据即 500"""
    resp = await client.get("/api/v1/emergency/events", headers=seeded["headers"])

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    items = body["data"]["items"]
    assert len(items) == 1
    assert items[0]["event_no"] == seeded["event"].event_no
    # 前端表格读这两个字段，缺了页面就是空白列
    assert items[0]["status"] == "processing"
    assert items[0]["created_at"] is not None


async def test_event_detail_serializes_nested_orm(client, seeded):
    """详情端点的 event / alarm / timelines / creator 全是 ORM，逐个都要转"""
    resp = await client.get(
        f"/api/v1/emergency/events/{seeded['event'].id}", headers=seeded["headers"]
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["event"]["event_no"] == seeded["event"].event_no
    # 关联报警复用 alarm_service.alarm_payload（计划 3.2 帧载荷，主键字段名为 alarm_id）
    assert data["alarm"]["alarm_id"] == seeded["alarm"].id
    assert data["alarm"]["device_name"] is not None
    assert [node["node_type"] for node in data["timelines"]] == ["alarm", "confirm"]
    assert data["creator"]["id"] == seeded["user"].id


async def test_event_timeline_list_serializes_orm(client, seeded):
    resp = await client.get(
        f"/api/v1/emergency/events/{seeded['event'].id}/timelines", headers=seeded["headers"]
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["total"] == 2
    assert body["data"]["items"][0]["node_type"] == "alarm"


async def test_event_resolve_serializes_orm(client, seeded):
    """
    resolve 也返回 ORM 事件对象，同样在 500 名单里。

    除了序列化，`updated_at`（onupdate 列）在 flush 后取值会触发**同步**懒加载 →
    `MissingGreenlet` 500 —— 容器实测正是这条（`emergency_events.py:210`
    → `emergency_service.py` 的 event_payload）。
    """
    resp = await client.post(
        f"/api/v1/emergency/events/{seeded['event'].id}/resolve",
        json={"summary": "现场已处置完毕"},
        headers=seeded["headers"],
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "resolved"


async def test_event_resolve_actually_persists(client, seeded, db_session):
    """
    写操作必须落库。

    service 层只 `flush()`，而 `get_db` 既不 commit 也不做别的提交 ——
    端点不显式 commit，请求结束会话关闭时整个事务被回滚，
    于是「提示处置完成、库里纹丝不动」。
    """
    event_id = seeded["event"].id
    resp = await client.post(
        f"/api/v1/emergency/events/{event_id}/resolve",
        json={"summary": "现场已处置完毕"},
        headers=seeded["headers"],
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    rows = list(
        (
            await db_session.execute(
                select(EmergencyEvent).where(EmergencyEvent.id == event_id)
            )
        ).scalars().all()
    )
    assert rows[0].status == "resolved"
    assert rows[0].resolved_at is not None

    # 处置完成节点也要落库
    nodes = list(
        (
            await db_session.execute(
                select(EmergencyTimeline).where(EmergencyTimeline.event_id == event_id)
            )
        ).scalars().all()
    )
    assert "complete" in [node.node_type for node in nodes]


async def test_add_timeline_node_persists(client, seeded, db_session):
    """添加时间轴节点同样只 flush 不 commit，必须由端点补上"""
    event_id = seeded["event"].id
    resp = await client.post(
        f"/api/v1/emergency/events/{event_id}/timelines",
        json={"node_type": "check_in", "node_title": "到场签到", "description": "已到现场"},
        headers=seeded["headers"],
    )
    # 该端点把异常吞成 HTTP 200 + code=400，只看 status_code 会漏掉
    body = resp.json()
    assert body.get("code") == 200, body.get("message")
    assert body["data"]["node_type"] == "check_in"

    db_session.expire_all()
    nodes = list(
        (
            await db_session.execute(
                select(EmergencyTimeline).where(EmergencyTimeline.event_id == event_id)
            )
        ).scalars().all()
    )
    assert "check_in" in [node.node_type for node in nodes]


async def test_event_close_persists(client, seeded, db_session):
    """强制关闭走同一条写路径"""
    event_id = seeded["event"].id
    # expire_all() 会让 seeded 里的 ORM 对象也过期，之后在断言里读它的属性
    # 会在同步栈上触发懒加载 → MissingGreenlet。先把要用的值取出来。
    closer_id = seeded["user"].id
    resp = await client.post(
        f"/api/v1/emergency/events/{event_id}/close",
        headers=seeded["headers"],
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    rows = list(
        (
            await db_session.execute(
                select(EmergencyEvent).where(EmergencyEvent.id == event_id)
            )
        ).scalars().all()
    )
    assert rows[0].status == "closed"
    assert rows[0].closed_by == closer_id
