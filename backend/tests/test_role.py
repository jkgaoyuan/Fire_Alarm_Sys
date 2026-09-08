"""
角色管理模块单元测试
覆盖场景：列表分页、创建、更新、删除、权限校验
"""

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.permission import Permission
from app.models.user import Role, User


# ---------------------------------------------------------------------------
# Helper: 创建拥有 system:role 权限的用户
# ---------------------------------------------------------------------------
async def _create_chief_user(db_session, perm_codes=None):
    """创建主管用户（拥有指定权限，默认 system:role）"""
    if perm_codes is None:
        perm_codes = ["system:role"]

    perms = []
    for code in perm_codes:
        perm = Permission(perm_code=code, perm_name=code, perm_type="button")
        db_session.add(perm)
        perms.append(perm)
    await db_session.commit()
    for p in perms:
        await db_session.refresh(p)

    role = Role(role_code="chief", role_name="消防主管", is_builtin=True)
    for p in perms:
        role.permissions.append(p)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user = User(
        username="chief_test",
        password_hash=get_password_hash("Chief1234"),
        real_name="主管测试",
        status="active",
        data_scope="all",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_get_roles_pagination(client, db_session):
    """角色列表分页查询"""
    chief = await _create_chief_user(db_session)
    token = create_access_token(data={"sub": str(chief.id), "jti": "role-test-1"})

    # 预置两个自定义角色
    role_a = Role(role_code="custom_a", role_name="自定义A", is_builtin=False)
    role_b = Role(role_code="custom_b", role_name="自定义B", is_builtin=False)
    db_session.add(role_a)
    db_session.add(role_b)
    await db_session.commit()

    response = await client.get(
        "/api/v1/roles?page=1&page_size=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert "items" in data["data"]
    assert data["data"]["total"] >= 2
    assert data["data"]["page"] == 1
    assert data["data"]["page_size"] == 10


@pytest.mark.asyncio
async def test_get_roles_filter_by_role_code(client, db_session):
    """按 role_code 过滤角色列表"""
    chief = await _create_chief_user(db_session)
    token = create_access_token(data={"sub": str(chief.id), "jti": "role-test-2"})

    role = Role(role_code="filter_me", role_name="过滤角色", is_builtin=False)
    db_session.add(role)
    await db_session.commit()

    response = await client.get(
        "/api/v1/roles?role_code=filter_me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert len(data["data"]["items"]) == 1
    assert data["data"]["items"][0]["role_code"] == "filter_me"


@pytest.mark.asyncio
async def test_get_roles_filter_by_role_name(client, db_session):
    """按 role_name 模糊搜索角色列表"""
    chief = await _create_chief_user(db_session)
    token = create_access_token(data={"sub": str(chief.id), "jti": "role-test-3"})

    role = Role(role_code="search_test", role_name="搜索测试角色", is_builtin=False)
    db_session.add(role)
    await db_session.commit()

    response = await client.get(
        "/api/v1/roles?role_name=搜索测试",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert len(data["data"]["items"]) == 1
    assert data["data"]["items"][0]["role_name"] == "搜索测试角色"


@pytest.mark.asyncio
async def test_create_role_with_permissions(client, db_session):
    """创建角色并绑定权限"""
    chief = await _create_chief_user(db_session)
    token = create_access_token(data={"sub": str(chief.id), "jti": "role-test-4"})

    # 先创建两个权限
    perm1 = Permission(perm_code="test:perm1", perm_name="测试权限1", perm_type="button")
    perm2 = Permission(perm_code="test:perm2", perm_name="测试权限2", perm_type="button")
    db_session.add(perm1)
    db_session.add(perm2)
    await db_session.commit()
    await db_session.refresh(perm1)
    await db_session.refresh(perm2)

    response = await client.post(
        "/api/v1/roles",
        json={
            "role_name": "新建角色",
            "description": "这是一个测试角色",
            "perm_ids": [perm1.id, perm2.id],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["role_name"] == "新建角色"
    assert data["data"]["description"] == "这是一个测试角色"
    assert data["data"]["is_builtin"] is False
    assert set(data["data"]["perm_ids"]) == {perm1.id, perm2.id}


@pytest.mark.asyncio
async def test_update_role_and_rebind_permissions(client, db_session):
    """更新角色并重新绑定权限"""
    chief = await _create_chief_user(db_session)
    token = create_access_token(data={"sub": str(chief.id), "jti": "role-test-5"})

    perm1 = Permission(perm_code="up:perm1", perm_name="更新权限1", perm_type="button")
    perm2 = Permission(perm_code="up:perm2", perm_name="更新权限2", perm_type="button")
    db_session.add(perm1)
    db_session.add(perm2)
    await db_session.commit()
    await db_session.refresh(perm1)
    await db_session.refresh(perm2)

    role = Role(role_code="update_role", role_name="待更新角色", is_builtin=False)
    role.permissions.append(perm1)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    # 更新：修改名称、描述，并重新绑定权限（仅保留 perm2）
    response = await client.put(
        f"/api/v1/roles/{role.id}",
        json={
            "role_name": "已更新角色",
            "description": "描述已更新",
            "perm_ids": [perm2.id],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["role_name"] == "已更新角色"
    assert data["data"]["description"] == "描述已更新"
    assert data["data"]["perm_ids"] == [perm2.id]


@pytest.mark.asyncio
async def test_delete_role_success(client, db_session):
    """删除自定义角色成功"""
    chief = await _create_chief_user(db_session)
    token = create_access_token(data={"sub": str(chief.id), "jti": "role-test-6"})

    role = Role(role_code="to_delete", role_name="待删除角色", is_builtin=False)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    response = await client.delete(
        f"/api/v1/roles/{role.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["message"] == "删除成功"


@pytest.mark.asyncio
async def test_delete_builtin_role_forbidden(client, db_session):
    """删除内置角色失败"""
    chief = await _create_chief_user(db_session)
    token = create_access_token(data={"sub": str(chief.id), "jti": "role-test-7"})

    role = Role(role_code="builtin_role", role_name="内置角色", is_builtin=True)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    response = await client.delete(
        f"/api/v1/roles/{role.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 400
    assert "内置角色" in data["message"]


@pytest.mark.asyncio
async def test_delete_role_with_users_forbidden(client, db_session):
    """删除已关联用户的角色失败"""
    chief = await _create_chief_user(db_session)
    token = create_access_token(data={"sub": str(chief.id), "jti": "role-test-8"})

    role = Role(role_code="has_users", role_name="有用户的角色", is_builtin=False)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user = User(
        username="linked_user",
        password_hash=get_password_hash("Linked1234"),
        status="active",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()

    response = await client.delete(
        f"/api/v1/roles/{role.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 400
    assert "关联用户" in data["message"]


@pytest.mark.asyncio
async def test_get_role_permissions_list(client, db_session):
    """获取角色已绑定权限 ID 列表"""
    chief = await _create_chief_user(db_session)
    token = create_access_token(data={"sub": str(chief.id), "jti": "role-test-9"})

    perm = Permission(perm_code="rp:perm1", perm_name="权限1", perm_type="button")
    db_session.add(perm)
    await db_session.commit()
    await db_session.refresh(perm)

    role = Role(role_code="rp_role", role_name="权限角色", is_builtin=False)
    role.permissions.append(perm)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    response = await client.get(
        f"/api/v1/roles/{role.id}/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"] == [perm.id]


@pytest.mark.asyncio
async def test_role_api_permission_denied(client, db_session):
    """无 system:role 权限访问角色接口返回 403"""
    # 创建无权限角色
    role = Role(role_code="no_perm", role_name="无权限角色", is_builtin=False)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user = User(
        username="no_perm_user",
        password_hash=get_password_hash("NoPerm1234"),
        status="active",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(data={"sub": str(user.id), "jti": "role-test-10"})

    response = await client.get(
        "/api/v1/roles",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["code"] == 403
