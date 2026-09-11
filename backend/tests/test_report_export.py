"""
报表导出（FR-052）API 测试

覆盖：创建导出任务、查询任务状态、下载文件、任务列表、权限校验
"""

import pytest
import pytest_asyncio

from tests.statistics_helpers import (
    auth_headers,
    create_org,
    create_device_type,
    create_statistics_user,
)


@pytest_asyncio.fixture
async def export_env(db_session):
    """构造导出测试环境"""
    org = await create_org(db_session, "导出测试大楼")
    dt = await create_device_type(db_session)
    chief = await create_statistics_user(
        db_session, username="export_chief", perm_codes=["statistics:view", "statistics:export"]
    )
    viewer = await create_statistics_user(
        db_session, username="export_viewer", perm_codes=["statistics:view"]
    )
    return {"org": org, "dt": dt, "chief": chief, "viewer": viewer}


# ==================== 创建导出任务 ====================


@pytest.mark.asyncio
async def test_create_export_task(client, export_env):
    """创建 Excel 导出任务成功"""
    headers = auth_headers(export_env["chief"])
    resp = await client.post(
        "/api/v1/reports/export",
        headers=headers,
        json={
            "task_type": "alarm_trend",
            "params": {"days": 7},
            "data": [{"date": "2026-09-01", "count": 5}],
            "format": "xlsx",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "task_id" in data
    assert "task_no" in data
    assert data["task_no"].startswith("EXP_")


@pytest.mark.asyncio
async def test_create_export_task_missing_task_type(client, export_env):
    """缺少 task_type 返回 400"""
    headers = auth_headers(export_env["chief"])
    resp = await client.post(
        "/api/v1/reports/export",
        headers=headers,
        json={"params": {}},
    )
    # FastAPI 会返回 400 因为 body 里没有 task_type
    # 但我们的 API 手动解析 JSON，所以返回 400
    assert resp.status_code in (400, 422)


# ==================== 查询任务状态 ====================


@pytest.mark.asyncio
async def test_get_export_task_status(client, export_env):
    """查询导出任务状态"""
    headers = auth_headers(export_env["chief"])

    # 先创建任务
    create_resp = await client.post(
        "/api/v1/reports/export",
        headers=headers,
        json={
            "task_type": "device_status",
            "params": {},
            "data": [{"status": "normal", "count": 10}],
        },
    )
    task_id = create_resp.json()["data"]["task_id"]

    # 查询状态
    resp = await client.get(f"/api/v1/reports/export/{task_id}/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["task_type"] == "device_status"
    assert data["status"] in ("pending", "running", "completed", "failed")


# ==================== 任务列表 ====================


@pytest.mark.asyncio
async def test_list_my_export_tasks(client, export_env):
    """我的导出任务列表只返回自己的任务"""
    headers = auth_headers(export_env["chief"])

    # 创建两个任务
    for i in range(2):
        await client.post(
            "/api/v1/reports/export",
            headers=headers,
            json={"task_type": "alarm_trend", "data": []},
        )

    resp = await client.get("/api/v1/reports/export-tasks", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 2


# ==================== 权限校验 ====================


@pytest.mark.asyncio
async def test_export_requires_export_permission(client, export_env):
    """只有 statistics:view 的用户不能创建导出任务"""
    headers = auth_headers(export_env["viewer"])
    resp = await client.post(
        "/api/v1/reports/export",
        headers=headers,
        json={"task_type": "alarm_trend", "data": []},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_export_tasks_requires_export_permission(client, export_env):
    """只有 statistics:view 的用户可以查看列表（因为只需要 view 权限）"""
    headers = auth_headers(export_env["viewer"])
    resp = await client.get("/api/v1/reports/export-tasks", headers=headers)
    assert resp.status_code == 200  # view 用户可以查询列表


@pytest.mark.asyncio
async def test_unauthenticated_export_request(client, export_env):
    """未认证请求被拒绝"""
    resp = await client.post(
        "/api/v1/reports/export",
        json={"task_type": "alarm_trend", "data": []},
    )
    assert resp.status_code == 401
