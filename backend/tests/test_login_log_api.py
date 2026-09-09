"""
登录日志 API 测试（P1-003）
覆盖场景：列表查询、分页、筛选、无权限 403
"""

from datetime import datetime, timedelta

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.permission import Permission
from app.models.user import LoginLog, Role, User


@pytest.fixture
async def log_viewer(client, db_session):
    """拥有 system:log:view 权限的测试用户"""
    role = Role(role_code="log_viewer", role_name="日志查看员", is_builtin=False)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    perm = Permission(
        perm_code="system:log:view",
        perm_name="查看登录日志",
        perm_type="button",
    )
    db_session.add(perm)
    await db_session.commit()
    await db_session.refresh(perm)

    await db_session.refresh(role, attribute_names=["permissions"])
    role.permissions.append(perm)

    user = User(
        username="logviewer",
        password_hash=get_password_hash("Log12345"),
        real_name="日志查看员",
        status="active",
        data_scope="all",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(data={"sub": str(user.id), "jti": "test-log-viewer"})
    return {"user": user, "token": token}


@pytest.fixture
async def sample_logs(db_session):
    """预置登录日志样本（秒级对齐，避免微秒截断导致时间范围断言抖动）"""
    now = datetime.utcnow().replace(microsecond=0)
    logs = [
        LoginLog(
            username="alice",
            login_type="password",
            ip_address="192.168.1.1",
            device_type="desktop",
            device_os="Windows",
            browser="Chrome",
            status="success",
            created_at=now - timedelta(minutes=10),
        ),
        LoginLog(
            username="bob",
            login_type="password",
            ip_address="192.168.1.2",
            device_type="mobile",
            device_os="iOS",
            browser="Safari",
            status="fail",
            fail_reason="密码错误",
            created_at=now - timedelta(minutes=5),
        ),
        LoginLog(
            username="alice",
            login_type="password",
            ip_address="192.168.1.3",
            status="locked",
            fail_reason="account_locked",
            created_at=now,
        ),
    ]
    for log in logs:
        db_session.add(log)
    await db_session.commit()
    return logs


@pytest.mark.asyncio
async def test_get_login_logs_success(client, log_viewer, sample_logs):
    """有权限用户可查询登录日志列表"""
    response = await client.get(
        "/api/v1/login-logs",
        headers={"Authorization": f"Bearer {log_viewer['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["total"] == 3
    assert len(data["data"]["items"]) == 3
    # 默认按时间倒序
    assert data["data"]["items"][0]["status"] == "locked"


@pytest.mark.asyncio
async def test_get_login_logs_pagination(client, log_viewer, sample_logs):
    """分页参数生效"""
    response = await client.get(
        "/api/v1/login-logs?page=1&page_size=2",
        headers={"Authorization": f"Bearer {log_viewer['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["total"] == 3
    assert len(data["data"]["items"]) == 2


@pytest.mark.asyncio
async def test_get_login_logs_filter_by_username(client, log_viewer, sample_logs):
    """按用户名模糊筛选"""
    response = await client.get(
        "/api/v1/login-logs?username=ali",
        headers={"Authorization": f"Bearer {log_viewer['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["total"] == 2
    assert all("ali" in (item["username"] or "") for item in data["data"]["items"])


@pytest.mark.asyncio
async def test_get_login_logs_filter_by_status(client, log_viewer, sample_logs):
    """按状态筛选"""
    response = await client.get(
        "/api/v1/login-logs?status=fail",
        headers={"Authorization": f"Bearer {log_viewer['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["status"] == "fail"


@pytest.mark.asyncio
async def test_get_login_logs_filter_by_time_range(client, log_viewer, sample_logs):
    """按时间范围筛选"""
    now = datetime.utcnow().replace(microsecond=0)
    start = (now - timedelta(minutes=6)).strftime("%Y-%m-%dT%H:%M:%S")
    end = now.strftime("%Y-%m-%dT%H:%M:%S")
    response = await client.get(
        f"/api/v1/login-logs?start_time={start}&end_time={end}",
        headers={"Authorization": f"Bearer {log_viewer['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["total"] == 2


@pytest.mark.asyncio
async def test_get_login_logs_forbidden(client, test_user):
    """无权限用户返回 403"""
    token = create_access_token(data={"sub": str(test_user.id), "jti": "test-no-perm"})
    response = await client.get(
        "/api/v1/login-logs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["code"] == 403
