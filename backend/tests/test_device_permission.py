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
async def test_data_scope_self_falls_back_to_dept(client, scope_env):
    """
    self：设备域**降级为 dept** —— 本部门及子部门，不再按建档人过滤。

    ⚠️ 本条断言在 2026-09-14 被**有意改写**（原名
    `test_data_scope_self_limits_to_creator`，断言「self 即便同区域也只能看到
    自己建档的设备」）。原因见 `device_service.apply_device_data_scope`：
    设备是**组织的资产**，不是录入人的私产，`created_by` 是「谁录的档案」，
    与「谁该看/该修这台设备」无关。按建档人过滤的实测后果是维保员
    （`data_scope='self'`）设备档案页 **0 台**、详情/历史/轨迹全 404，
    而设备维保恰是他的本职。

    改写后仍然钉住「self 不是不受限」：同部门内的**他人建档**设备可见了，
    但**别的部门**的设备依然不可见。
    """
    env = scope_env
    await _add(client, env, env["chief"], "DEV-BY-CHIEF", env["building_b"])
    await _add(client, env, env["self_user"], "DEV-BY-SELF", env["building_b"])
    # 另一个部门（A 栋）的设备：不得因为 self 降级而漏出去
    await _add(client, env, env["chief"], "DEV-A1", env["building_a"])

    assert await _codes(client, auth_headers(env["self_user"])) == {
        "DEV-BY-CHIEF",
        "DEV-BY-SELF",
    }


@pytest.mark.asyncio
async def test_self_scope_can_open_device_detail(client, db_session, scope_env):
    """
    self 用户必须能打开**本部门内他人建档**设备的详情。

    列表可见但详情 404 是最难察觉的一种不一致：界面上能看到这一行，
    点进去说「设备不存在」。列表与详情用的是同一个口径函数，
    这里把「两处一起改」钉住。
    """
    env = scope_env
    device_id = await _add(client, env, env["chief"], "DEV-BY-CHIEF", env["building_b"])
    headers = auth_headers(env["self_user"])

    resp = await client.get(f"/api/v1/devices/{device_id}", headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 200, resp.json()


@pytest.mark.asyncio
async def test_user_without_org_sees_nothing(client, db_session, scope_env):
    """
    未分配部门的 self/dept 用户：**看不到任何设备**，而不是看到全部。

    `users.org_id` 可空，所以这是真实可达的配置。设备范围是「本部门及子部门」，
    没有部门就是空集 —— 一旦这里漏成「不过滤」，一个连部门都没配的账号
    就能读到全公司的设备档案。

    这条钉住的是**行为**，不是某一行实现：`apply_device_data_scope` 里
    「org_id 为空」与「子树为空」是两道**冗余**保险，实测单独删掉任意一道
    本用例都不会红（另一道仍然兜住）。这是刻意的纵深防御，不是覆盖缺口。
    """
    env = scope_env
    await _add(client, env, env["chief"], "DEV-A1", env["building_a"])
    orphan = await create_device_user(
        db_session,
        username="no_org",
        perm_codes=["device:view"],
        data_scope="self",
    )
    assert orphan.org_id is None, "用例前提：该账号没有部门"

    assert await _codes(client, auth_headers(orphan)) == set()


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
