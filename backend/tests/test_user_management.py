"""
用户管理 API 测试
覆盖：用户列表、创建、更新、状态变更、角色分配、重置密码、删除、权限控制
"""

import pytest

from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.permission import Permission
from app.models.user import Role, User
from tests.auth_helpers import create_user_with_perms


async def _create_chief_user(db_session, with_user_perm: bool = True):
    """测试辅助：创建主管角色和用户，可选绑定 system:user 权限"""
    perm_user = Permission(
        perm_code="system:user",
        perm_name="用户管理",
        perm_type="menu",
        route_path="/system/user",
        component="views/system/User.vue",
        icon="User",
        sort_order=1,
    )
    perm_role = Permission(
        perm_code="system:role",
        perm_name="角色管理",
        perm_type="menu",
        route_path="/system/role",
        component="views/system/Role.vue",
        icon="Role",
        sort_order=2,
    )
    db_session.add(perm_user)
    db_session.add(perm_role)
    await db_session.commit()
    await db_session.refresh(perm_user)
    await db_session.refresh(perm_role)

    role = Role(role_code="chief", role_name="消防主管", is_builtin=True)
    if with_user_perm:
        role.permissions.append(perm_user)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user = User(
        username="chiefuser",
        password_hash=get_password_hash("Chief1234"),
        real_name="主管用户",
        status="active",
        data_scope="all",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return user


async def _auth_headers(user):
    """生成认证请求头"""
    token = create_access_token(data={"sub": str(user.id), "jti": "test-jti"})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_users_list_success(client, db_session):
    """主管可获取用户列表"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    response = await client.get("/api/v1/users", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert "items" in data["data"]
    assert "total" in data["data"]


@pytest.mark.asyncio
async def test_get_users_forbidden(client, db_session):
    """无 system:user 权限的用户不能访问用户列表"""
    chief = await _create_chief_user(db_session, with_user_perm=False)
    headers = await _auth_headers(chief)

    response = await client.get("/api/v1/users", headers=headers)
    assert response.status_code == 403
    data = response.json()
    assert data["code"] == 403


@pytest.mark.asyncio
async def test_create_user_success(client, db_session):
    """主管可创建用户"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    payload = {
        "username": "newuser",
        "password": "New123456",
        "real_name": "新用户",
        "phone": "13800138001",
        "email": "new@example.com",
        "data_scope": "dept",
        "role_ids": [],
    }
    response = await client.post("/api/v1/users", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["username"] == "newuser"
    assert data["data"]["real_name"] == "新用户"
    assert data["data"]["data_scope"] == "dept"


@pytest.mark.asyncio
async def test_create_user_duplicate_username(client, db_session):
    """创建用户时用户名已存在返回 400"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    # 先创建一个用户
    payload = {
        "username": "duplicate",
        "password": "Dup123456",
        "data_scope": "self",
    }
    await client.post("/api/v1/users", json=payload, headers=headers)

    # 再次创建同名用户
    response = await client.post("/api/v1/users", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 400
    assert "已存在" in data["message"]


@pytest.mark.asyncio
async def test_update_user_success(client, db_session):
    """更新用户基础信息"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    # 创建目标用户
    target = User(
        username="target",
        password_hash=get_password_hash("Target1234"),
        real_name="目标用户",
        status="active",
        data_scope="self",
    )
    db_session.add(target)
    await db_session.commit()
    await db_session.refresh(target)

    payload = {
        "real_name": "已更新",
        "data_scope": "all",
    }
    response = await client.put(f"/api/v1/users/{target.id}", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["real_name"] == "已更新"
    assert data["data"]["data_scope"] == "all"


@pytest.mark.asyncio
async def test_update_user_not_found(client, db_session):
    """更新不存在的用户返回 404"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    response = await client.put("/api/v1/users/9999", json={"real_name": "test"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 404


@pytest.mark.asyncio
async def test_disable_and_enable_user(client, db_session):
    """禁用并重新启用用户"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    target = User(
        username="target",
        password_hash=get_password_hash("Target1234"),
        status="active",
    )
    db_session.add(target)
    await db_session.commit()
    await db_session.refresh(target)

    # 禁用
    response = await client.put(
        f"/api/v1/users/{target.id}/status",
        json={"status": "disabled"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "disabled"

    # 启用
    response = await client.put(
        f"/api/v1/users/{target.id}/status",
        json={"status": "active"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "active"


@pytest.mark.asyncio
async def test_unlock_user_clears_lock(client, db_session):
    """解锁用户时清空 locked_until 和失败计数"""
    from datetime import datetime, timezone

    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    target = User(
        username="lockeduser",
        password_hash=get_password_hash("Locked1234"),
        status="locked",
        login_fail_count=5,
        locked_until=datetime.now(timezone.utc),
    )
    db_session.add(target)
    await db_session.commit()
    await db_session.refresh(target)

    response = await client.put(
        f"/api/v1/users/{target.id}/status",
        json={"status": "active"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["status"] == "active"


@pytest.mark.asyncio
async def test_cannot_self_disable(client, db_session):
    """不能禁用当前登录用户自己"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    response = await client.put(
        f"/api/v1/users/{chief.id}/status",
        json={"status": "disabled"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 400
    assert "当前登录用户" in data["message"]


@pytest.mark.asyncio
async def test_assign_roles_to_user(client, db_session):
    """分配角色给用户"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    role = Role(role_code="duty", role_name="值班员", is_builtin=False)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    target = User(
        username="roletest",
        password_hash=get_password_hash("Role1234"),
        status="active",
    )
    db_session.add(target)
    await db_session.commit()
    await db_session.refresh(target)

    response = await client.put(
        f"/api/v1/users/{target.id}/roles",
        json={"role_ids": [role.id]},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert len(data["data"]["roles"]) == 1
    assert data["data"]["roles"][0]["role_code"] == "duty"


@pytest.mark.asyncio
async def test_reset_password_success(client, db_session):
    """重置用户密码返回新密码并更新哈希"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    target = User(
        username="pwdtest",
        password_hash=get_password_hash("Old123456"),
        status="active",
    )
    db_session.add(target)
    await db_session.commit()
    await db_session.refresh(target)

    response = await client.put(f"/api/v1/users/{target.id}/reset-password", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    new_password = data["data"]["new_password"]
    assert len(new_password) >= 8

    # 验证密码哈希已更新
    await db_session.refresh(target)
    assert verify_password(new_password, target.password_hash)


@pytest.mark.asyncio
async def test_delete_user_success(client, db_session):
    """主管可删除用户"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    target = User(
        username="deleteme",
        password_hash=get_password_hash("Delete1234"),
        status="active",
    )
    db_session.add(target)
    await db_session.commit()
    await db_session.refresh(target)

    response = await client.delete(f"/api/v1/users/{target.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200

    # 确认已删除
    result = await db_session.get(User, target.id)
    assert result is None


@pytest.mark.asyncio
async def test_cannot_self_delete(client, db_session):
    """不能删除当前登录用户自己"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    response = await client.delete(f"/api/v1/users/{chief.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 400
    assert "当前登录用户" in data["message"]


@pytest.mark.asyncio
async def test_get_all_roles(client, db_session):
    """获取所有角色列表（用于分配角色弹窗）"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    role = Role(role_code="extra", role_name="额外角色", is_builtin=False)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    response = await client.get("/api/v1/users/roles/all", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert isinstance(data["data"], list)
    role_codes = [r["role_code"] for r in data["data"]]
    assert "chief" in role_codes
    assert "extra" in role_codes


@pytest.mark.asyncio
async def test_user_list_keyword_filter(client, db_session):
    """用户列表支持关键字搜索"""
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    target = User(
        username="searchme",
        password_hash=get_password_hash("Search1234"),
        real_name="搜索目标",
        phone="13800138002",
        status="active",
    )
    db_session.add(target)
    await db_session.commit()

    # 按真实姓名搜索
    response = await client.get("/api/v1/users", params={"keyword": "搜索目标"}, headers=headers)
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["real_name"] == "搜索目标"


@pytest.mark.asyncio
async def test_user_list_permission_filter(client, db_session):
    """
    TC-USER-006: 用户列表可按「是否持有某权限码」过滤。

    用途：派单弹窗只能列出真正能接手的人（持有 `repair:repair` 的用户）。
    不过滤的死结：主管可以把工单派给值班员（下拉框原先只筛 `status == "active"`），
    而值班员没有 `repair:repair`，「开始维修」和「完成维修」都会 403——
    工单被派出去就卡在那儿，谁也动不了。
    """
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    await create_user_with_perms(db_session, "pf_can", ["repair:repair"])
    await create_user_with_perms(db_session, "pf_cannot", ["repair:view"])

    response = await client.get(
        "/api/v1/users", params={"permission": "repair:repair"}, headers=headers
    )
    data = response.json()

    assert data["code"] == 200
    usernames = {item["username"] for item in data["data"]["items"]}
    assert "pf_can" in usernames
    assert "pf_cannot" not in usernames, "不持有 repair:repair 的人不该出现在可选维修人里"


@pytest.mark.asyncio
async def test_permission_filter_applies_to_total(client, db_session):
    """
    TC-USER-007: 权限过滤必须同时作用于 `total`，不能只筛 items。

    不修会怎样：items 已过滤、total 用未过滤的计数，前端分页条会显示
    「共 3 条」却只给出 1 行——巡检任务列表踩过同一个坑
    （count 与 items 用了两套条件）。
    """
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    await create_user_with_perms(db_session, "pf2_can", ["repair:repair"])
    await create_user_with_perms(db_session, "pf2_cannot", ["repair:view"])

    ref = await client.get("/api/v1/users", headers=headers)
    unmatched = ref.json()["data"]["total"]  # 不加过滤时的总数（3）

    response = await client.get(
        "/api/v1/users", params={"permission": "repair:repair"}, headers=headers
    )
    body = response.json()

    assert body["data"]["total"] == len(body["data"]["items"]) == 1
    assert body["data"]["total"] < unmatched, "过滤后 total 未收窄，说明计数没跟着筛"


@pytest.mark.asyncio
async def test_permission_filter_is_optional(client, db_session):
    """
    TC-USER-008: 省略 `permission` 参数时行为不变（向后兼容）。

    这个参数是**新增**的，既有调用方（用户管理页等）不传它，必须照旧拿到全量。
    """
    chief = await _create_chief_user(db_session)
    headers = await _auth_headers(chief)

    await create_user_with_perms(db_session, "pf3_can", ["repair:repair"])
    await create_user_with_perms(db_session, "pf3_cannot", ["repair:view"])

    response = await client.get("/api/v1/users", headers=headers)
    usernames = {item["username"] for item in response.json()["data"]["items"]}

    assert {"pf3_can", "pf3_cannot"} <= usernames
