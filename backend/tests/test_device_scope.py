"""
单资源设备接口的数据权限范围（P1-007）

按 ID 的详情、更新、退役、删除、历史、轨迹/导出，均须复用 list_devices 的
all/dept/self 范围规则；越权时返回 404 而非 403，避免泄露存在性。
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
async def scope_env(db_session):
    """准备两棵独立组织树 + 设备类型 + 主管（all）与 self 用户"""
    building = await create_org(db_session, "总部大楼")
    floor1 = await create_org(db_session, "1号楼", parent=building)
    floor2 = await create_org(db_session, "2号楼", parent=building)
    other_building = await create_org(db_session, "外部大楼")

    device_type = await create_device_type(db_session)

    chief = await create_device_user(
        db_session,
        username="scope_chief",
        perm_codes=ALL_DEVICE_PERMS,
        data_scope="all",
        org=building,
    )
    self_user = await create_device_user(
        db_session,
        username="scope_self",
        perm_codes=ALL_DEVICE_PERMS,
        data_scope="self",
    )
    dept_user = await create_device_user(
        db_session,
        username="scope_dept",
        perm_codes=ALL_DEVICE_PERMS,
        data_scope="dept",
        org=floor1,
    )
    return {
        "building": building,
        "floor1": floor1,
        "floor2": floor2,
        "other_building": other_building,
        "type": device_type,
        "chief": chief,
        "self_user": self_user,
        "dept_user": dept_user,
    }


async def _create_device(client, env, user_key, org, code):
    resp = await client.post(
        "/api/v1/devices",
        headers=auth_headers(env[user_key]),
        json=device_payload(env["type"].id, org.id, code),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


@pytest.mark.asyncio
async def test_self_user_cannot_access_others_device_detail(client, scope_env):
    """self 范围用户用 ID 读取主管设备应 404"""
    device = await _create_device(client, scope_env, "chief", scope_env["floor1"], "SCOPE-SELF-DETAIL")
    resp = await client.get(
        f"/api/v1/devices/{device['id']}",
        headers=auth_headers(scope_env["self_user"]),
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_self_user_cannot_mutate_others_device(client, scope_env):
    """self 范围用户对主管设备的写操作（PUT/DELETE/retire）均 404"""
    device = await _create_device(client, scope_env, "chief", scope_env["floor1"], "SCOPE-SELF-MUTATE")
    headers = auth_headers(scope_env["self_user"])

    assert (
        await client.put(
            f"/api/v1/devices/{device['id']}",
            headers=headers,
            json={"device_name": "越权改名"},
        )
    ).json()["code"] == 404

    assert (
        await client.post(
            f"/api/v1/devices/{device['id']}/retire",
            headers=headers,
            json={"reason": "越权退役"},
        )
    ).json()["code"] == 404

    assert (await client.delete(f"/api/v1/devices/{device['id']}", headers=headers)).json()["code"] == 404


@pytest.mark.asyncio
async def test_self_user_can_access_own_device(client, scope_env):
    """self 范围用户可正常读写自己创建的设备"""
    device = await _create_device(client, scope_env, "self_user", scope_env["floor1"], "SCOPE-SELF-OWN")
    headers = auth_headers(scope_env["self_user"])

    resp = await client.get(f"/api/v1/devices/{device['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["device_code"] == "SCOPE-SELF-OWN"

    resp = await client.put(
        f"/api/v1/devices/{device['id']}",
        headers=headers,
        json={"device_name": "自己改名"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["device_name"] == "自己改名"


@pytest.mark.asyncio
async def test_dept_user_sees_same_org_not_sibling(client, scope_env):
    """dept 范围用户可见本部门及子部门设备，不可见同级/上级/外部设备"""
    own = await _create_device(client, scope_env, "chief", scope_env["floor1"], "SCOPE-DEPT-OWN")
    sibling = await _create_device(client, scope_env, "chief", scope_env["floor2"], "SCOPE-DEPT-SIBLING")
    external = await _create_device(
        client, scope_env, "chief", scope_env["other_building"], "SCOPE-DEPT-EXT"
    )
    headers = auth_headers(scope_env["dept_user"])

    assert (await client.get(f"/api/v1/devices/{own['id']}", headers=headers)).status_code == 200
    assert (
        await client.get(f"/api/v1/devices/{sibling['id']}", headers=headers)
    ).json()["code"] == 404
    assert (
        await client.get(f"/api/v1/devices/{external['id']}", headers=headers)
    ).json()["code"] == 404


@pytest.mark.asyncio
async def test_history_and_trajectory_respect_data_scope(client, scope_env):
    """历史记录与轨迹接口同样受数据范围限制"""
    device = await _create_device(client, scope_env, "chief", scope_env["floor1"], "SCOPE-HIS-TRAJ")
    headers = auth_headers(scope_env["self_user"])

    assert (
        await client.get(f"/api/v1/devices/{device['id']}/history", headers=headers)
    ).json()["code"] == 404

    assert (
        await client.get(f"/api/v1/devices/{device['id']}/trajectory", headers=headers)
    ).json()["code"] == 404

    export = await client.get(
        f"/api/v1/devices/{device['id']}/trajectory/export",
        headers=headers,
        params={"format": "csv"},
    )
    assert export.json()["code"] == 404


@pytest.mark.asyncio
async def test_all_scope_user_can_access_any_device(client, scope_env):
    """all 范围用户可跨部门访问设备"""
    external = await _create_device(
        client, scope_env, "chief", scope_env["other_building"], "SCOPE-ALL-EXT"
    )
    resp = await client.get(
        f"/api/v1/devices/{external['id']}",
        headers=auth_headers(scope_env["chief"]),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["device_code"] == "SCOPE-ALL-EXT"
