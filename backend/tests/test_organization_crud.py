"""
组织架构 CRUD 接口测试（P2-010）

覆盖：创建/更新/删除组织节点、org_type 校验、关联数据保护、权限控制。
"""

import pytest

from tests.device_helpers import auth_headers, create_org, create_device_user


@pytest.mark.asyncio
async def test_create_org(client, db_session):
    """有权限用户可以创建组织节点"""
    user = await create_device_user(db_session, "org_admin", perm_codes=["system:org:create"])

    resp = await client.post(
        "/api/v1/organizations",
        json={"org_name": "A 栋", "org_type": "building", "sort_order": 1},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert data["data"]["org_name"] == "A 栋"
    assert data["data"]["org_type"] == "building"
    assert data["data"]["parent_id"] is None


@pytest.mark.asyncio
async def test_create_org_with_parent(client, db_session):
    """创建子节点时 parent_id 正确关联"""
    user = await create_device_user(db_session, "org_admin2", perm_codes=["system:org:create"])
    root = await create_org(db_session, "消防中心")

    resp = await client.post(
        "/api/v1/organizations",
        json={"org_name": "1F", "org_type": "floor", "parent_id": root.id},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["parent_id"] == root.id
    assert data["org_type"] == "floor"


@pytest.mark.asyncio
async def test_create_org_invalid_type(client, db_session):
    """org_type 不在 building/floor/zone 范围内返回 422"""
    user = await create_device_user(db_session, "org_bad", perm_codes=["system:org:create"])

    resp = await client.post(
        "/api/v1/organizations",
        json={"org_name": "测试", "org_type": "invalid_type"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_org_invalid_parent(client, db_session):
    """parent_id 指向不存在的节点返回 400"""
    user = await create_device_user(db_session, "org_bad2", perm_codes=["system:org:create"])

    resp = await client.post(
        "/api/v1/organizations",
        json={"org_name": "测试", "org_type": "floor", "parent_id": 999999},
        headers=auth_headers(user),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_org(client, db_session):
    """更新组织节点名称和排序"""
    user = await create_device_user(db_session, "org_upd", perm_codes=["system:org:update"])
    org = await create_org(db_session, "旧名称")

    resp = await client.put(
        f"/api/v1/organizations/{org.id}",
        json={"org_name": "新名称", "sort_order": 5},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["org_name"] == "新名称"


@pytest.mark.asyncio
async def test_update_org_not_found(client, db_session):
    """更新不存在的节点返回 404"""
    user = await create_device_user(db_session, "org_nf", perm_codes=["system:org:update"])

    resp = await client.put(
        "/api/v1/organizations/999999",
        json={"org_name": "测试"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_delete_org(client, db_session):
    """删除无关联的叶子节点"""
    user = await create_device_user(db_session, "org_del", perm_codes=["system:org:delete"])
    org = await create_org(db_session, "待删除")

    resp = await client.delete(
        f"/api/v1/organizations/{org.id}",
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 200


@pytest.mark.asyncio
async def test_delete_org_with_children(client, db_session):
    """有子节点时拒绝删除"""
    user = await create_device_user(db_session, "org_del2", perm_codes=["system:org:delete"])
    root = await create_org(db_session, "父节点")
    await create_org(db_session, "子节点", parent=root)

    resp = await client.delete(
        f"/api/v1/organizations/{root.id}",
        headers=auth_headers(user),
    )
    assert resp.status_code == 400
    assert "子节点" in resp.json()["message"]


@pytest.mark.asyncio
async def test_create_org_without_permission(client, db_session):
    """无 system:org:create 权限返回 403"""
    user = await create_device_user(db_session, "org_noperm", perm_codes=[])

    resp = await client.post(
        "/api/v1/organizations",
        json={"org_name": "测试", "org_type": "building"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_org_requires_login(client):
    """未登录返回 401"""
    resp = await client.post(
        "/api/v1/organizations",
        json={"org_name": "测试", "org_type": "building"},
    )
    assert resp.status_code == 401
