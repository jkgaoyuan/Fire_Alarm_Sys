"""
用户模块单元测试
覆盖场景：获取当前用户信息、菜单树、权限码、未登录 401、无权限 403
"""

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.permission import Permission
from app.models.user import Role, User


@pytest.mark.asyncio
async def test_get_me_success(client, db_session):
    """获取当前用户信息（含角色）"""
    # 创建角色
    role = Role(role_code="chief", role_name="消防主管", is_builtin=True)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    # 创建用户并关联角色
    user = User(
        username="chiefuser",
        password_hash=get_password_hash("Chief1234"),
        real_name="主管用户",
        phone="13800138000",
        email="chief@example.com",
        status="active",
        data_scope="all",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 生成 Access Token
    token = create_access_token(data={"sub": str(user.id), "jti": "test-jti"})

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["username"] == "chiefuser"
    assert data["data"]["real_name"] == "主管用户"
    assert data["data"]["phone"] == "13800138000"
    assert data["data"]["email"] == "chief@example.com"
    assert data["data"]["data_scope"] == "all"
    assert len(data["data"]["roles"]) == 1
    assert data["data"]["roles"][0]["role_code"] == "chief"
    assert data["data"]["roles"][0]["role_name"] == "消防主管"


@pytest.mark.asyncio
async def test_get_me_unauthorized(client):
    """未登录访问返回 401"""
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == 401


@pytest.mark.asyncio
async def test_get_my_menus(client, db_session):
    """获取菜单树结构"""
    # 创建菜单权限
    perm_dashboard = Permission(
        perm_code="monitor:dashboard",
        perm_name="监控大屏",
        perm_type="menu",
        route_path="/monitor/dashboard",
        component="views/monitor/Dashboard.vue",
        icon="Monitor",
        sort_order=1,
    )
    perm_alarm = Permission(
        perm_code="alarm:center",
        perm_name="报警中心",
        perm_type="menu",
        route_path="/alarm/center",
        component="views/alarm/Center.vue",
        icon="Bell",
        sort_order=2,
    )
    db_session.add(perm_dashboard)
    db_session.add(perm_alarm)
    await db_session.commit()
    await db_session.refresh(perm_dashboard)
    await db_session.refresh(perm_alarm)

    # 创建角色并绑定权限
    role = Role(role_code="duty_officer", role_name="消防值班员", is_builtin=True)
    role.permissions.append(perm_dashboard)
    role.permissions.append(perm_alarm)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    # 创建用户
    user = User(
        username="duty01",
        password_hash=get_password_hash("Duty1234"),
        real_name="值班员01",
        status="active",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(data={"sub": str(user.id), "jti": "test-jti-2"})

    response = await client.get(
        "/api/v1/users/me/menus",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 2
    # 按 sort_order 排序，第一个是监控大屏
    assert data["data"][0]["name"] == "monitor:dashboard"
    assert data["data"][0]["path"] == "/monitor/dashboard"
    assert data["data"][0]["meta"]["title"] == "监控大屏"
    assert data["data"][0]["meta"]["icon"] == "Monitor"


@pytest.mark.asyncio
async def test_get_my_permissions(client, db_session):
    """获取权限码列表"""
    # 创建多种类型权限
    perm_view = Permission(
        perm_code="device:view",
        perm_name="查看设备",
        perm_type="button",
    )
    perm_create = Permission(
        perm_code="device:create",
        perm_name="新增设备",
        perm_type="button",
    )
    db_session.add(perm_view)
    db_session.add(perm_create)
    await db_session.commit()
    await db_session.refresh(perm_view)
    await db_session.refresh(perm_create)

    # 创建角色并绑定部分权限
    role = Role(role_code="maintainer", role_name="维保人员", is_builtin=True)
    role.permissions.append(perm_view)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    # 创建用户
    user = User(
        username="maint01",
        password_hash=get_password_hash("Maint1234"),
        real_name="维保人员01",
        status="active",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(data={"sub": str(user.id), "jti": "test-jti-3"})

    response = await client.get(
        "/api/v1/users/me/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert isinstance(data["data"], list)
    assert "device:view" in data["data"]
    assert "device:create" not in data["data"]


@pytest.mark.asyncio
async def test_get_permissions_tree_forbidden(client, db_session):
    """无权限访问权限树返回 403"""
    # 创建无 system:role 权限的角色
    role = Role(role_code="duty_officer", role_name="消防值班员", is_builtin=True)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user = User(
        username="noperms",
        password_hash=get_password_hash("Noperms1234"),
        status="active",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(data={"sub": str(user.id), "jti": "test-jti-4"})

    response = await client.get(
        "/api/v1/permissions/tree",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["code"] == 403


@pytest.mark.asyncio
async def test_get_permissions_tree_success(client, db_session):
    """主管角色可访问权限树"""
    # 创建 system:role 权限
    perm_role = Permission(
        perm_code="system:role",
        perm_name="角色管理",
        perm_type="menu",
        route_path="/system/role",
        component="views/system/Role.vue",
        icon="Role",
        sort_order=1,
    )
    db_session.add(perm_role)
    await db_session.commit()
    await db_session.refresh(perm_role)

    # 创建主管角色并绑定 system:role 权限
    role = Role(role_code="chief", role_name="消防主管", is_builtin=True)
    role.permissions.append(perm_role)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user = User(
        username="chief01",
        password_hash=get_password_hash("Chief1234"),
        status="active",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(data={"sub": str(user.id), "jti": "test-jti-5"})

    response = await client.get(
        "/api/v1/permissions/tree",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert isinstance(data["data"], list)
