"""
监控大屏与地图查询 API（3.3 B-15 / FR-014、FR-015）测试

覆盖：dashboard 统计口径（online 与演练排除）、区域下钻与 dept 隔离、
TopN 未确认火警置顶、bbox 视口过滤与超限网格聚合。
"""

from datetime import datetime, timedelta

import pytest_asyncio

from tests.device_helpers import (
    auth_headers,
    create_device_type,
    create_device_user,
    create_org,
)
from tests.monitor_helpers import MONITOR_PERMS, create_alarm, create_device


@pytest_asyncio.fixture
async def monitor_env(db_session):
    org_a = await create_org(db_session, "A 栋")
    org_b = await create_org(db_session, "B 栋")
    device_type = await create_device_type(db_session)
    chief = await create_device_user(
        db_session, username="mon_chief", perm_codes=MONITOR_PERMS, data_scope="all"
    )
    officer_a = await create_device_user(
        db_session,
        username="mon_officer_a",
        perm_codes=MONITOR_PERMS,
        data_scope="dept",
        org=org_a,
    )
    return {
        "a": org_a,
        "b": org_b,
        "type": device_type,
        "chief": chief,
        "officer_a": officer_a,
    }


async def _dev(db, env, org, code, status="normal", **kwargs):
    return await create_device(db, org, env["type"], code, status=status, **kwargs)


async def _get(client, user, url, params=None):
    resp = await client.get(url, headers=auth_headers(user), params=params)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200, body
    return body["data"]


async def test_dashboard_status_scope_and_region_drill(db_session, client, monitor_env):
    """online = 总数 - offline - retired；报警计数排除演练；org 下钻与 dept 口径一致"""
    env = monitor_env
    a_alarm = await _dev(db_session, env, env["a"], "DA-ALM", "alarm")
    await _dev(db_session, env, env["a"], "DA-NRM")
    await _dev(db_session, env, env["a"], "DA-FLT", "fault")
    await _dev(db_session, env, env["a"], "DA-OFF", "offline")
    await _dev(db_session, env, env["a"], "DA-RET", "retired")
    b_alarm = await _dev(db_session, env, env["b"], "DB-ALM", "alarm")
    await _dev(db_session, env, env["b"], "DB-NRM")

    await create_alarm(db_session, a_alarm, "fire")
    await create_alarm(db_session, a_alarm, "fault")
    await create_alarm(db_session, b_alarm, "fire", is_drill=True)

    data = await _get(client, env["chief"], "/api/v1/monitor/dashboard")
    assert data["total"] == 7
    assert (data["offline"], data["retired"], data["online"]) == (1, 1, 5)
    assert (data["alarm"], data["fault"], data["normal"], data["shield"]) == (2, 1, 2, 0)
    assert data["pending_alarm"] == 2 and data["pending_fire"] == 1
    assert data["status_counts"]["retired"] == 1

    drill = await _get(
        client, env["chief"], "/api/v1/monitor/dashboard", {"org_id": env["a"].id}
    )
    assert (drill["total"], drill["online"], drill["pending_alarm"]) == (5, 3, 2)

    scoped = await _get(client, env["officer_a"], "/api/v1/monitor/dashboard")
    assert scoped["status_counts"] == drill["status_counts"]
    assert scoped["total"] == drill["total"]


async def test_recent_alarms_pins_unconfirmed_fire(db_session, client, monitor_env):
    """TopN：未确认火警强制置顶，其余按报警时间倒序；演练默认不出现"""
    env = monitor_env
    now = datetime.utcnow()
    device_a = await _dev(db_session, env, env["a"], "DR-A", "alarm")
    device_b = await _dev(db_session, env, env["b"], "DR-B", "alarm")

    pending_fire = await create_alarm(
        db_session, device_a, "fire", created_at=now - timedelta(hours=3)
    )
    drill_fire = await create_alarm(
        db_session,
        device_b,
        "fire",
        created_at=now - timedelta(hours=1),
        is_drill=True,
    )
    latest_pre = await create_alarm(
        db_session, device_b, "pre_fire", created_at=now - timedelta(hours=2)
    )
    confirmed = await create_alarm(
        db_session,
        device_a,
        "fault",
        status="confirmed",
        created_at=now - timedelta(minutes=30),
    )

    items = await _get(client, env["chief"], "/api/v1/monitor/alarms/recent", {"limit": 10})
    assert [i["alarm_id"] for i in items] == [
        pending_fire.id,
        confirmed.id,
        latest_pre.id,
    ]
    assert items[0]["status"] == "pending" and items[0]["alarm_level"] == "critical"

    with_drill = await _get(
        client,
        env["chief"],
        "/api/v1/monitor/alarms/recent",
        {"limit": 10, "include_drill": "true"},
    )
    assert [i["alarm_id"] for i in with_drill][:2] == [drill_fire.id, pending_fire.id]

    limited = await _get(
        client, env["officer_a"], "/api/v1/monitor/alarms/recent", {"limit": 1}
    )
    assert [i["alarm_id"] for i in limited] == [pending_fire.id]


async def test_map_devices_filters_by_viewport_and_scope(db_session, client, monitor_env):
    """bbox 按原图像素坐标裁剪视口；retired 与无坐标设备不渲染；越权区域返回空集"""
    env = monitor_env
    alarm_device = await _dev(
        db_session, env, env["a"], "DP-A1", "alarm", map_x=100, map_y=100
    )
    await _dev(db_session, env, env["a"], "DP-A2", map_x=800, map_y=800)
    await _dev(db_session, env, env["a"], "DP-A3", "offline", map_x=50, map_y=900)
    await _dev(db_session, env, env["a"], "DP-A4", "retired", map_x=60, map_y=60)
    await _dev(db_session, env, env["a"], "DP-A5")  # 未标注坐标 → 不上图
    await _dev(db_session, env, env["b"], "DP-B1", map_x=500, map_y=500)
    await create_alarm(db_session, alarm_device, "fire")

    viewport = await _get(
        client,
        env["chief"],
        "/api/v1/monitor/map/devices",
        {"bbox": "0,0,600,600"},
    )
    assert viewport["aggregated"] is False
    assert sorted(i["device_code"] for i in viewport["items"]) == ["DP-A1", "DP-B1"]
    assert viewport["bbox"] == [0.0, 0.0, 600.0, 600.0]

    point = next(i for i in viewport["items"] if i["device_code"] == "DP-A1")
    assert (point["has_active_alarm"], point["alarm_type"]) == (True, "fire")
    assert point["count"] == 1 and point["type_name"] == "烟感探测器"

    floor_only = await _get(
        client, env["chief"], "/api/v1/monitor/map/devices", {"org_id": env["a"].id}
    )
    assert sorted(i["device_code"] for i in floor_only["items"]) == [
        "DP-A1",
        "DP-A2",
        "DP-A3",
    ]

    denied = await _get(
        client, env["officer_a"], "/api/v1/monitor/map/devices", {"org_id": env["b"].id}
    )
    assert (denied["items"], denied["total"]) == ([], 0)

    mine = await _get(client, env["officer_a"], "/api/v1/monitor/map/devices")
    assert sorted(i["device_code"] for i in mine["items"]) == ["DP-A1", "DP-A2", "DP-A3"]


async def test_map_devices_excludes_drill_from_active_alarm(db_session, client, monitor_env):
    """
    TC-MON-020: 地图点位的 `has_active_alarm` 不认演练告警（FR-045 隔离）。

    大屏报警列表（`AlarmList.vue:75`）已把演练全滤掉。地图若照旧把演练算作
    「有活动报警」，就会出现**列表空着、地图红着**的自相矛盾——而大屏没有
    「含演练」开关，用户无从解释这个红点，也无从关掉它。
    `_active_alarm_map` 是这条标记的唯一来源，且只被 map/devices 使用。
    """
    env = monitor_env
    real = await _dev(db_session, env, env["a"], "DM-REAL", "alarm", map_x=100, map_y=100)
    drill = await _dev(db_session, env, env["a"], "DM-DRILL", "alarm", map_x=200, map_y=200)
    await create_alarm(db_session, real, "fire")
    await create_alarm(db_session, drill, "fire", is_drill=True)

    data = await _get(client, env["chief"], "/api/v1/monitor/map/devices")
    by_code = {p["device_code"]: p for p in data["items"]}

    assert by_code["DM-REAL"]["has_active_alarm"] is True
    assert by_code["DM-REAL"]["alarm_type"] == "fire"
    assert by_code["DM-DRILL"]["has_active_alarm"] is False, (
        "演练告警不该把地图点位标成活动报警"
    )
    assert by_code["DM-DRILL"]["alarm_type"] is None


async def test_map_devices_aggregates_when_over_limit(db_session, client, monitor_env):
    """点位数超过 limit 时切 10×10 网格聚合，桶内 count 之和等于 total"""
    env = monitor_env
    devices = []
    for index in range(4):
        devices.append(
            await _dev(
                db_session,
                env,
                env["a"],
                f"DAG-{index}",
                status="alarm" if index == 0 else "normal",
                map_x=index * 200 + 50,
                map_y=index * 200 + 50,
            )
        )
    await create_alarm(db_session, devices[0], "pre_fire")

    data = await _get(
        client,
        env["chief"],
        "/api/v1/monitor/map/devices",
        {"bbox": "0,0,1000,1000", "limit": 2},
    )
    assert data["aggregated"] is True and data["total"] == 4
    assert sum(i["count"] for i in data["items"]) == 4
    assert all(i["device_code"].startswith("cluster-") for i in data["items"])
