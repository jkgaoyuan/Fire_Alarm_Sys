"""
设备档案 CRUD（FR-008）测试

覆盖：创建、详情、列表、更新、退役、逻辑删除、编码唯一性（含更新冲突）、
非法状态、retired 终态禁止编辑与重复退役、状态变更留痕。
"""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.device import Device, DeviceStatusLog
from tests.device_helpers import (
    ALL_DEVICE_PERMS,
    auth_headers,
    create_device_type,
    create_device_user,
    create_org,
    device_payload,
)


@pytest_asyncio.fixture
async def device_env(db_session):
    """准备区域 + 设备类型 + 拥有全部设备权限的主管账号"""
    org = await create_org(db_session, "总部大楼")
    device_type = await create_device_type(db_session)
    chief = await create_device_user(
        db_session, username="chief", perm_codes=ALL_DEVICE_PERMS, data_scope="all"
    )
    return {"org": org, "type": device_type, "user": chief}


async def _create(client, env, code="DEV-001"):
    resp = await client.post(
        "/api/v1/devices",
        headers=auth_headers(env["user"]),
        json=device_payload(env["type"].id, env["org"].id, code),
    )
    return resp


@pytest.mark.asyncio
async def test_create_device(client, device_env):
    """创建设备成功并回填类型/区域/创建人展示字段"""
    resp = await _create(client, device_env)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["device_code"] == "DEV-001"
    assert data["status"] == "normal"
    assert data["type_name"] == "烟感探测器"
    assert data["category"] == "detector"
    assert data["org_name"] == "总部大楼"
    assert data["creator_name"] == "chief"
    assert data["attributes"] == {"sensitivity": "高", "detection_area": 60}
    assert data["map_x"] == 120.5
    assert data["install_date"] == "2025-03-15"


@pytest.mark.asyncio
async def test_create_device_duplicate_code_rejected(client, device_env):
    """设备编码全库唯一，重复创建返回 400"""
    assert (await _create(client, device_env)).status_code == 200

    resp = await _create(client, device_env)
    assert resp.status_code == 400
    assert "设备编码已存在" in resp.json()["message"]


@pytest.mark.asyncio
async def test_create_device_invalid_attributes_rejected(client, device_env):
    """扩展属性不符合类型模板时拒绝创建"""
    payload = device_payload(device_env["type"].id, device_env["org"].id)
    payload["attributes"] = {"sensitivity": "超高"}

    resp = await client.post(
        "/api/v1/devices",
        headers=auth_headers(device_env["user"]),
        json=payload,
    )
    assert resp.status_code == 400
    assert "扩展属性校验失败" in resp.json()["message"]


@pytest.mark.asyncio
async def test_create_device_unknown_type_rejected(client, device_env):
    """type_id / org_id 指向不存在的记录时返回 400 而不是 500"""
    payload = device_payload(999999, device_env["org"].id)
    resp = await client.post(
        "/api/v1/devices",
        headers=auth_headers(device_env["user"]),
        json=payload,
    )
    assert resp.status_code == 400
    assert "设备类型不存在" in resp.json()["message"]


@pytest.mark.asyncio
async def test_create_device_invalid_status_rejected(client, device_env):
    """非法状态枚举由 Pydantic 拦截（422）"""
    payload = device_payload(device_env["type"].id, device_env["org"].id)
    payload["status"] = "broken"

    resp = await client.post(
        "/api/v1/devices",
        headers=auth_headers(device_env["user"]),
        json=payload,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_device_detail_and_404(client, device_env):
    """详情可查；不存在或已逻辑删除的设备返回 404"""
    created = (await _create(client, device_env)).json()["data"]

    resp = await client.get(
        f"/api/v1/devices/{created['id']}", headers=auth_headers(device_env["user"])
    )
    assert resp.json()["data"]["device_name"] == "1F大厅烟感A01"

    resp = await client.get("/api/v1/devices/424242", headers=auth_headers(device_env["user"]))
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_update_device(client, device_env):
    """更新基础字段与扩展属性生效"""
    device_id = (await _create(client, device_env)).json()["data"]["id"]
    headers = auth_headers(device_env["user"])

    resp = await client.put(
        f"/api/v1/devices/{device_id}",
        headers=headers,
        json={
            "device_name": "1F大厅烟感A02",
            "status": "fault",
            "attributes": {"sensitivity": "低", "detection_area": 45},
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["device_name"] == "1F大厅烟感A02"
    assert data["status"] == "fault"
    assert data["attributes"]["detection_area"] == 45


@pytest.mark.asyncio
async def test_update_device_code_conflict(client, device_env):
    """更新时改成他人已占用的编码应被拒绝；改自己的编码不算冲突"""
    headers = auth_headers(device_env["user"])
    first = (await _create(client, device_env, "DEV-001")).json()["data"]
    second = (await _create(client, device_env, "DEV-002")).json()["data"]

    resp = await client.put(
        f"/api/v1/devices/{second['id']}", headers=headers, json={"device_code": "DEV-001"}
    )
    assert resp.status_code == 400
    assert "设备编码已存在" in resp.json()["message"]

    resp = await client.put(
        f"/api/v1/devices/{first['id']}", headers=headers, json={"device_code": "DEV-001"}
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_device_rejects_retired_via_put(client, device_env):
    """退役必须走 /retire，PUT 直接改 status=retired 被拒绝"""
    headers = auth_headers(device_env["user"])
    device_id = (await _create(client, device_env)).json()["data"]["id"]

    resp = await client.put(
        f"/api/v1/devices/{device_id}", headers=headers, json={"status": "retired"}
    )
    assert resp.status_code == 400
    assert "退役请调用" in resp.json()["message"]


@pytest.mark.asyncio
async def test_retire_device_flow(client, device_env):
    """退役后置为 retired 且不可再编辑、不可重复退役"""
    headers = auth_headers(device_env["user"])
    device_id = (await _create(client, device_env)).json()["data"]["id"]

    resp = await client.post(
        f"/api/v1/devices/{device_id}/retire",
        headers=headers,
        json={"reason": "超过使用年限"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "retired"
    assert data["is_deleted"] is False

    resp = await client.put(
        f"/api/v1/devices/{device_id}", headers=headers, json={"device_name": "改名"}
    )
    assert resp.status_code == 400
    assert "已退役" in resp.json()["message"]

    resp = await client.post(
        f"/api/v1/devices/{device_id}/retire", headers=headers, json={"reason": "再退役"}
    )
    assert resp.status_code == 400
    assert "无需重复退役" in resp.json()["message"]


@pytest.mark.asyncio
async def test_retire_writes_status_log(client, device_env, db_session):
    """建档与退役都要留下状态变更日志"""
    headers = auth_headers(device_env["user"])
    device_id = (await _create(client, device_env)).json()["data"]["id"]
    await client.post(
        f"/api/v1/devices/{device_id}/retire", headers=headers, json={"reason": "超期"}
    )

    rows = (
        (
            await db_session.execute(
                select(DeviceStatusLog)
                .where(DeviceStatusLog.device_id == device_id)
                .order_by(DeviceStatusLog.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(r.old_status, r.new_status) for r in rows] == [
        (None, "normal"),
        ("normal", "retired"),
    ]
    assert rows[1].reason == "超期"


@pytest.mark.asyncio
async def test_delete_device_is_soft_delete(client, device_env, db_session):
    """删除为逻辑删除：行仍在库中但详情与列表都不可见"""
    headers = auth_headers(device_env["user"])
    device_id = (await _create(client, device_env)).json()["data"]["id"]

    resp = await client.delete(f"/api/v1/devices/{device_id}", headers=headers)
    assert resp.status_code == 200

    resp = await client.get(f"/api/v1/devices/{device_id}", headers=headers)
    assert resp.json()["code"] == 404

    resp = await client.get("/api/v1/devices?include_retired=true", headers=headers)
    assert resp.json()["data"]["total"] == 0

    row = (
        await db_session.execute(select(Device).where(Device.id == device_id))
    ).scalar_one()
    assert row.is_deleted is True


@pytest.mark.asyncio
async def test_create_with_deleted_code_reports_restore_entry(client, device_env):
    """编码被已删除档案占用时，错误文案应指明来源并提供恢复入口"""
    headers = auth_headers(device_env["user"])
    created = (await _create(client, device_env, "DEV-DEL-001")).json()["data"]

    await client.delete(f"/api/v1/devices/{created['id']}", headers=headers)

    resp = await _create(client, device_env, "DEV-DEL-001")
    assert resp.status_code == 400
    message = resp.json()["message"]
    assert "设备编码已被已删除档案占用" in message
    assert f"/api/v1/devices/{created['id']}/restore" in message


@pytest.mark.asyncio
async def test_restore_soft_deleted_device(client, device_env, db_session):
    """恢复已逻辑删除的设备后，该设备重新可见且可继续使用原编码"""
    headers = auth_headers(device_env["user"])
    created = (await _create(client, device_env, "DEV-RES-001")).json()["data"]
    device_id = created["id"]

    await client.delete(f"/api/v1/devices/{device_id}", headers=headers)

    resp = await client.post(f"/api/v1/devices/{device_id}/restore", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["is_deleted"] is False

    resp = await client.get(f"/api/v1/devices/{device_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["device_code"] == "DEV-RES-001"

    row = (
        await db_session.execute(select(Device).where(Device.id == device_id))
    ).scalar_one()
    assert row.is_deleted is False
