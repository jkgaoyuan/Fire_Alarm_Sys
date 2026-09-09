"""
设备档案权限与数据范围测试

覆盖：data_scope=all/dept/self 三档隔离、缺少权限码被拒、值班员调用写接口 403。
"""

import pytest
import pytest_asyncio

from tests.device_helpers import (
    auth_headers,
    create_device_type,
    create_device_user,
    create_org,
    device_payload,
)


@pytest_asyncio.fixture
async def scope_env(db_session):
    """三级组织树 + 一种设备类型 + 分别持有 all/dept/self 的账号"""
    root = await create_org(db_session, "消防监控中心")
    building_a = await create_org(db_session, "A 栋", parent=root)
    floor_a1 = await create_org(db_session, "A 栋 1F", parent=building_a)
    building_b = await create_org(db_session, "B 栋", parent=root)

    device_type = await create_device_type(db_session)
    chief = await create_device_user(
        db_session,
        username="chief",
        perm_codes=["device:view", "device:create"],
        data_scope="all",
    )
    dept_user = await create_device_user(
        db_session,
        username="duty_a",
        perm_codes=["device:view"],
        data_scope="dept",
        org=building_a,
    )
    self_user = await create_device_user(
        db_session,
        username="maintainer",
        perm_codes=["device:view", "device:create"],
        data_scope="self",
        org=building_b,
    )
    return {
        "root": root,
        "building_a": building_a,
        "floor_a1": floor_a1,
        "building_b": building_b,
        "type": device_type,
        "chief": chief,
        "dept_user": dept_user,
        "self_user": self_user,
    }


async def _add(client, env, user, code, org):
    payload = device_payload(env["type"].id, org.id, code)
    payload["attributes"] = {}
    resp = await client.post(
        "/api/v1/devices", headers=auth_headers(user), json=payload
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


async def _codes(client, headers):
    resp = await client.get("/api/v1/devices?page_size=100", headers=headers)
    assert resp.status_code == 200, resp.text
    return {d["device_code"] for d in resp.json()["data"]["items"]}


@pytest.mark.asyncio
async def test_data_scope_all_sees_everything(client, scope_env):
    """all：不受区域限制"""
    env = scope_env
    await _add(client, env, env["chief"], "DEV-A1", env["floor_a1"])
    await _add(client, env, env["chief"], "DEV-B1", env["building_b"])

    assert await _codes(client, auth_headers(env["chief"])) == {"DEV-A1", "DEV-B1"}


@pytest.mark.asyncio
async def test_data_scope_dept_limits_to_subtree(client, scope_env):
    """dept：只能看到本部门及其子部门的设备"""
    env = scope_env
    await _add(client, env, env["chief"], "DEV-A1", env["floor_a1"])
    await _add(client, env, env["chief"], "DEV-A0", env["building_a"])
    await _add(client, env, env["chief"], "DEV-B1", env["building_b"])
    await _add(client, env, env["chief"], "DEV-ROOT", env["root"])

    assert await _codes(client, auth_headers(env["dept_user"])) == {"DEV-A1", "DEV-A0"}


@pytest.mark.asyncio
async def test_data_scope_self_limits_to_creator(client, scope_env):
    """self：即便同区域，也只能看到自己建档的设备"""
    env = scope_env
    await _add(client, env, env["chief"], "DEV-BY-CHIEF", env["building_b"])
    await _add(client, env, env["self_user"], "DEV-BY-SELF", env["building_b"])

    assert await _codes(client, auth_headers(env["self_user"])) == {"DEV-BY-SELF"}


@pytest.mark.asyncio
async def test_missing_permission_rejected(client, db_session, scope_env):
    """无任何 device 权限码时列表与详情均 403"""
    env = scope_env
    device_id = await _add(client, env, env["chief"], "DEV-A1", env["floor_a1"])
    outsider = await create_device_user(
        db_session, username="outsider", perm_codes=["inspection:view"]
    )
    headers = auth_headers(outsider)

    assert (await client.get("/api/v1/devices", headers=headers)).status_code == 403
    assert (
        await client.get(f"/api/v1/devices/{device_id}", headers=headers)
    ).status_code == 403


@pytest.mark.asyncio
async def test_duty_officer_cannot_write(client, db_session, scope_env):
    """值班员只有 device:view —— 退役/新增/删除都必须 403"""
    env = scope_env
    device_id = await _add(client, env, env["chief"], "DEV-A1", env["floor_a1"])
    headers = auth_headers(env["dept_user"])

    assert (
        await client.post(
            f"/api/v1/devices/{device_id}/retire", headers=headers, json={"reason": "超期"}
        )
    ).status_code == 403
    assert (
        await client.put(
            f"/api/v1/devices/{device_id}", headers=headers, json={"device_name": "改名"}
        )
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/devices/{device_id}", headers=headers)
    ).status_code == 403

    payload = device_payload(env["type"].id, env["floor_a1"].id, "DEV-NEW")
    payload["attributes"] = {}
    assert (
        await client.post("/api/v1/devices", headers=headers, json=payload)
    ).status_code == 403

    # 写接口被拒后设备保持原状
    detail = (
        await client.get(f"/api/v1/devices/{device_id}", headers=auth_headers(env["chief"]))
    ).json()["data"]
    assert detail["status"] == "normal"
    assert detail["device_name"] == "1F大厅烟感A01"
