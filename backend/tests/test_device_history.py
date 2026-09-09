"""
设备历史记录（FR-011 / B-11）测试

覆盖：状态变更时间轴聚合与倒序、无历史记录时的返回、不存在设备 404。
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio

from app.models.alarm import Alarm
from app.models.device import Device
from tests.device_helpers import (
    ALL_DEVICE_PERMS,
    auth_headers,
    create_device_type,
    create_device_user,
    create_org,
    device_payload,
)


@pytest_asyncio.fixture
async def history_env(db_session):
    org = await create_org(db_session, "总部大楼")
    device_type = await create_device_type(db_session)
    chief = await create_device_user(
        db_session, username="chief", perm_codes=ALL_DEVICE_PERMS, data_scope="all"
    )
    return {"org": org, "type": device_type, "user": chief}


async def _create(client, env, code="DEV-H-001"):
    payload = device_payload(env["type"].id, env["org"].id, code)
    resp = await client.post(
        "/api/v1/devices", headers=auth_headers(env["user"]), json=payload
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


@pytest.mark.asyncio
async def test_history_aggregates_status_changes(client, history_env):
    """建档 + 故障 + 退役按时间倒序输出，含操作人与原因"""
    env = history_env
    headers = auth_headers(env["user"])
    device_id = await _create(client, env)

    await client.put(
        f"/api/v1/devices/{device_id}", headers=headers, json={"status": "fault"}
    )
    await client.post(
        f"/api/v1/devices/{device_id}/retire", headers=headers, json={"reason": "超过使用年限"}
    )

    resp = await client.get(f"/api/v1/devices/{device_id}/history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["device_code"] == "DEV-H-001"
    assert data["total"] == 3
    assert [item["title"] for item in data["items"]] == [
        "状态变更：故障 → 已退役",
        "状态变更：正常 → 故障",
        "建档：正常",
    ]
    assert data["items"][0]["detail"] == "超过使用年限"
    assert {item["operator"] for item in data["items"]} == {"chief"}
    assert {item["category"] for item in data["items"]} == {"status_change"}


@pytest.mark.asyncio
async def test_history_declares_unavailable_sources(client, history_env):
    """3.3 后报警已可聚合，仅剩维修/巡检未上线，必须显式告知而不是伪装成空"""
    env = history_env
    device_id = await _create(client, env)

    data = (
        await client.get(
            f"/api/v1/devices/{device_id}/history", headers=auth_headers(env["user"])
        )
    ).json()["data"]
    assert data["unavailable_sources"] == ["inspection", "repair"]


@pytest.mark.asyncio
async def test_history_merges_alarms(client, history_env, db_session):
    """报警入库后与状态变更同轴展示（FR-011 跨类别聚合）"""
    env = history_env
    device_id = await _create(client, env)
    db_session.add(
        Alarm(
            device_id=device_id,
            org_id=env["org"].id,
            device_code="DEV-H-001",
            alarm_type="fire",
            alarm_level="critical",
            status="pending",
            location_description="3 层东侧",
            created_at=datetime.utcnow() + timedelta(seconds=1),
        )
    )
    await db_session.commit()

    data = (
        await client.get(
            f"/api/v1/devices/{device_id}/history", headers=auth_headers(env["user"])
        )
    ).json()["data"]
    assert data["total"] == 2
    assert [(i["category"], i["title"]) for i in data["items"]] == [
        ("alarm", "报警：火警"),
        ("status_change", "建档：正常"),
    ]
    assert data["items"][0]["detail"] == "3 层东侧"


@pytest.mark.asyncio
async def test_history_empty_and_not_found(client, history_env, db_session):
    """无状态变更日志时返回空时间轴；设备不存在或已逻辑删除返回 404"""
    env = history_env
    headers = auth_headers(env["user"])

    device = Device(
        device_code="DEV-RAW-001",
        device_name="直接落库无日志",
        type_id=env["type"].id,
        org_id=env["org"].id,
        status="normal",
        attributes={},
        created_by=env["user"].id,
    )
    db_session.add(device)
    await db_session.commit()

    data = (
        await client.get(f"/api/v1/devices/{device.id}/history", headers=headers)
    ).json()["data"]
    assert data["total"] == 0
    assert data["items"] == []

    assert (
        await client.get("/api/v1/devices/424242/history", headers=headers)
    ).json()["code"] == 404

    device_id = await _create(client, env)
    await client.delete(f"/api/v1/devices/{device_id}", headers=headers)
    assert (
        await client.get(f"/api/v1/devices/{device_id}/history", headers=headers)
    ).json()["code"] == 404
