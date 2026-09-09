"""
设备列表筛选（FR-012）测试

覆盖：关键字、类型+区域+状态组合筛选、分页边界、已退役默认隐藏。
"""

import pytest
import pytest_asyncio

from tests.device_helpers import (
    ALL_DEVICE_PERMS,
    auth_headers,
    create_device_type,
    create_device_user,
    create_org,
    device_payload,
)


@pytest_asyncio.fixture
async def filter_env(db_session):
    """两个区域 + 两种类型 + 6 台设备（其中 1 台已退役）"""
    org_a = await create_org(db_session, "A 栋")
    org_b = await create_org(db_session, "B 栋")
    smoke = await create_device_type(db_session, "smoke_detector", "烟感探测器")
    hydrant = await create_device_type(
        db_session, "hydrant", "消火栓", {"outlet_count": {"label": "水带数量", "type": "number"}}
    )
    user = await create_device_user(
        username="chief", perm_codes=ALL_DEVICE_PERMS, data_scope="all", db=db_session
    )
    return {"org_a": org_a, "org_b": org_b, "smoke": smoke, "hydrant": hydrant, "user": user}


async def _seed(client, env):
    """按 (编码, 名称, 类型, 区域, 状态) 批量建档"""
    headers = auth_headers(env["user"])
    rows = [
        ("DEV-S-001", "一层大厅烟感", env["smoke"], env["org_a"], "normal"),
        ("DEV-S-002", "二层走廊烟感", env["smoke"], env["org_a"], "fault"),
        ("DEV-S-003", "三层机房烟感", env["smoke"], env["org_b"], "alarm"),
        ("DEV-H-001", "一层消火栓", env["hydrant"], env["org_a"], "normal"),
        ("DEV-H-002", "二层消火栓", env["hydrant"], env["org_b"], "offline"),
        ("DEV-H-003", "退役消火栓", env["hydrant"], env["org_b"], "normal"),
    ]
    retired_id = None
    for code, name, device_type, org, status in rows:
        payload = device_payload(device_type.id, org.id, code)
        payload["device_name"] = name
        payload["status"] = status
        payload["attributes"] = {}
        resp = await client.post("/api/v1/devices", headers=headers, json=payload)
        assert resp.status_code == 200, resp.text
        if code == "DEV-H-003":
            retired_id = resp.json()["data"]["id"]

    resp = await client.post(
        f"/api/v1/devices/{retired_id}/retire", headers=headers, json={"reason": "超期"}
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_keyword_matches_code_and_name(client, filter_env):
    """关键字同时命中编码与名称"""
    await _seed(client, filter_env)
    headers = auth_headers(filter_env["user"])

    resp = await client.get("/api/v1/devices?keyword=DEV-S-", headers=headers)
    assert resp.json()["data"]["total"] == 3

    resp = await client.get("/api/v1/devices?keyword=消火栓", headers=headers)
    codes = {d["device_code"] for d in resp.json()["data"]["items"]}
    assert codes == {"DEV-H-001", "DEV-H-002"}


@pytest.mark.asyncio
async def test_combined_filters(client, filter_env):
    """类型 + 区域 + 状态组合筛选取交集"""
    await _seed(client, filter_env)
    headers = auth_headers(filter_env["user"])

    resp = await client.get(
        f"/api/v1/devices?type_id={filter_env['smoke'].id}"
        f"&org_id={filter_env['org_a'].id}&status=normal,fault",
        headers=headers,
    )
    data = resp.json()["data"]
    assert data["total"] == 2
    assert {d["device_code"] for d in data["items"]} == {"DEV-S-001", "DEV-S-002"}

    resp = await client.get(
        f"/api/v1/devices?org_id={filter_env['org_b'].id}&type_id={filter_env['hydrant'].id}",
        headers=headers,
    )
    assert {d["device_code"] for d in resp.json()["data"]["items"]} == {"DEV-H-002"}


@pytest.mark.asyncio
async def test_pagination_bounds(client, filter_env):
    """分页切片正确且 total 不随页码变化"""
    await _seed(client, filter_env)
    headers = auth_headers(filter_env["user"])

    resp = await client.get("/api/v1/devices?page=1&page_size=2", headers=headers)
    data = resp.json()["data"]
    assert data["total"] == 5
    assert len(data["items"]) == 2

    resp = await client.get("/api/v1/devices?page=3&page_size=2", headers=headers)
    data = resp.json()["data"]
    assert data["total"] == 5
    assert len(data["items"]) == 1

    resp = await client.get("/api/v1/devices?page=99&page_size=20", headers=headers)
    assert resp.json()["data"]["items"] == []

    resp = await client.get("/api/v1/devices?page_size=101", headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_retired_hidden_by_default(client, filter_env):
    """默认隐藏已退役；include_retired 或显式按 retired 状态筛选时可见"""
    await _seed(client, filter_env)
    headers = auth_headers(filter_env["user"])

    resp = await client.get("/api/v1/devices", headers=headers)
    assert "DEV-H-003" not in {d["device_code"] for d in resp.json()["data"]["items"]}

    resp = await client.get("/api/v1/devices?include_retired=true", headers=headers)
    assert resp.json()["data"]["total"] == 6

    resp = await client.get("/api/v1/devices?status=retired", headers=headers)
    items = resp.json()["data"]["items"]
    assert [d["device_code"] for d in items] == ["DEV-H-003"]
    assert items[0]["status"] == "retired"
