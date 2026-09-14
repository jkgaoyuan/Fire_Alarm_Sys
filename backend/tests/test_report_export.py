"""
报表导出（FR-052）API 测试

覆盖：创建导出任务、查询任务状态、下载文件、任务列表、权限校验
"""

import os

import pytest
import pytest_asyncio
from openpyxl import load_workbook

from fastapi import BackgroundTasks

from app.models.report_export import ReportExportTask
from app.services.report_export_service import (
    _background_export,
    create_export_task,
    execute_export_async,
    execute_export_sync,
)
from tests.conftest import TestingSessionLocal
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


# ==================== 持久化（回归） ====================


@pytest.mark.asyncio
async def test_export_task_survives_session_teardown(client, export_env, db_session):
    """
    TC-EXP-REG-001 导出任务必须真正落库 —— 请求会话拆除后仍能查到。

    生产的 `get_db` 在 `finally` 里 `close()` 会话（`autocommit=False`），
    未提交的事务会被回滚。本用例显式 `rollback()` 复现该语义：
    **只有 commit 过的行才活得下来。**

    ⚠️ 不能用「POST 之后在同一个 session 里查一下」来断言。
    `tests/conftest.py` 的 `client` 覆写了 `get_db`，让它 yield 同一个
    长期存活、请求之间**不关闭**的 `db_session`；于是「flush 了但没 commit」
    的行在测试里照样可见 —— 这个缺陷因此曾完全隐形（实测生产：接口返回
    task_id=19 而库里 0 行，磁盘上却已有 6 个导出文件）。
    """
    headers = auth_headers(export_env["chief"])

    # 夹具数据（用户/角色/组织）先落库，否则下面的 rollback 会一并丢掉
    await db_session.commit()

    resp = await client.post(
        "/api/v1/reports/export",
        headers=headers,
        json={"task_type": "alarm_trend", "params": {}, "data": [{"a": 1}]},
    )
    assert resp.status_code == 200

    # 复现生产环境的会话拆除
    await db_session.rollback()

    resp = await client.get("/api/v1/reports/export-tasks", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["total"] >= 1, "导出任务未提交，会话拆除后被回滚了"


# ==================== 后台导出（>1 万行） ====================


@pytest.mark.asyncio
async def test_background_export_completes_task(db_session, export_env, monkeypatch):
    """
    TC-EXP-REG-002 后台导出必须能真正跑完并把状态写回。

    覆盖此前**零覆盖**的 `_background_export`。它的会话工厂是函数内 import，
    曾误写为 `app.db.session` 中并不存在的 `async_session_maker` ——
    后台任务第一行就 ImportError，异常被后台任务机制吞掉，
    **任务永久停在 running，用户只看到「处理中...」转圈**。
    本用例同时钉住「工厂符号真实存在」与「状态被写回 completed」。
    """
    import app.db.session as session_module

    # 后台任务用的是独立 session；测试里指向同一个内存库
    monkeypatch.setattr(session_module, "AsyncSessionLocal", TestingSessionLocal)

    task = await create_export_task(db_session, "alarm_trend", {}, export_env["chief"].id)
    await db_session.commit()
    task_id = task.id

    await _background_export(task_id, [{"date": "2026-09-01", "count": 5}], "xlsx")

    db_session.expire_all()
    refreshed = await db_session.get(ReportExportTask, task_id)
    assert refreshed.status == "completed", (
        f"后台导出未完成，status={refreshed.status}，error={refreshed.error_message}"
    )
    assert refreshed.file_path


@pytest.mark.asyncio
async def test_async_export_task_committed_before_handoff(db_session, export_env):
    """
    TC-EXP-REG-003 异步导出必须在交接给后台任务**之前**提交。

    `_background_export` 用独立 session 靠 `db.get(task_id)` 取回本行；
    不提交的话它拿到 None 直接 return，任务永久停在 running。
    本用例不预先手动 commit，因此 rollback 后行还在 = 服务自己提交过。
    """
    task = await create_export_task(db_session, "alarm_trend", {}, export_env["chief"].id)
    task_id = task.id

    await execute_export_async(
        BackgroundTasks(), db_session, task, [{"a": 1}] * 10001, "xlsx"
    )

    # 模拟请求会话拆除
    await db_session.rollback()
    db_session.expire_all()

    row = await db_session.get(ReportExportTask, task_id)
    assert row is not None, "异步导出任务未提交，后台 session 将取不到该行"
    assert row.status == "running"


@pytest.mark.asyncio
async def test_same_type_same_day_exports_do_not_share_a_file(db_session, export_env):
    """
    TC-EXP-REG-004 同类型、同一天的两个导出任务不得共用同一个磁盘文件。

    `file_name` 只由「类型 + 日期」拼成，不含任务唯一标识，因此两个同类型
    同天的导出必然同名：后写的覆盖先写的，而两条 DB 记录都指向同一路径 ——
    下载先前的任务会**静默拿到后一次的内容**（不报任何错）。
    """
    created = []
    try:
        tasks = []
        for payload in (
            [{"date": "d1", "count": 1}],
            [{"date": "d2", "count": 2}, {"date": "d3", "count": 3}],
        ):
            t = await create_export_task(
                db_session, "alarm_trend", {}, export_env["chief"].id
            )
            await execute_export_sync(db_session, t, payload, "xlsx")
            tasks.append(t)
            created.append(t.file_path)

        first, second = tasks
        assert first.file_path != second.file_path, (
            "两个导出任务指向了同一个磁盘路径，后者会覆盖前者"
        )

        # 先前的任务必须仍保有**自己的**内容
        assert os.path.exists(first.file_path)
        assert load_workbook(first.file_path).active.max_row == 2, (
            "任务 1 的数据被任务 2 覆盖了"
        )
    finally:
        for path in created:
            if path and os.path.exists(path):
                os.remove(path)


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
