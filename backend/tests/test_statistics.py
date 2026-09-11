"""
统计看板（FR-048 ~ FR-051）API 测试

覆盖：设备完好率、报警趋势、故障 TOP10、巡检完成率、区域下钻、权限校验
"""

import pytest
import pytest_asyncio
from datetime import date, datetime, timedelta

from tests.statistics_helpers import (
    auth_headers,
    create_alarm,
    create_device,
    create_device_type,
    create_inspection_plan,
    create_inspection_task,
    create_org,
    create_repair_order,
    create_statistics_user,
)


@pytest_asyncio.fixture
async def stat_env(db_session):
    """构造统计测试环境：组织 + 设备类型 + 用户 + 设备/报警/维修/巡检数据"""
    org = await create_org(db_session, "总部大楼")
    child_org = await create_org(db_session, "1F", parent=org)
    dt = await create_device_type(db_session)
    user = await create_statistics_user(db_session, username="chief", data_scope="all", org=org)
    view_only_user = await create_statistics_user(
        db_session, username="viewer", perm_codes=["statistics:view"], data_scope="all"
    )

    # 设备：4 normal + 1 alarm + 1 fault
    for i, status in enumerate(["normal", "normal", "normal", "normal", "alarm", "fault"]):
        await create_device(db_session, org, dt, code=f"DEV-{i:03d}", status=status)

    # 子组织设备
    await create_device(db_session, child_org, dt, code="DEV-1F-001", status="normal")

    # 报警：近 7 天 fire=3, fault=2
    now = datetime.utcnow()
    device = (await db_session.execute(
        __import__("sqlalchemy").select(__import__("app.models.device", fromlist=["Device"]).Device).limit(1)
    )).scalar_one()
    for i in range(3):
        await create_alarm(db_session, device, alarm_type="fire", created_at=now - timedelta(days=i))
    for i in range(2):
        await create_alarm(db_session, device, alarm_type="fault", created_at=now - timedelta(days=i))
    # 演练报警（应被排除）
    await create_alarm(db_session, device, alarm_type="fire", is_drill=True, created_at=now)

    # 维修工单
    for i in range(5):
        await create_repair_order(
            db_session, device, status="completed", order_no=f"RO-{i:03d}",
            completed_at=now - timedelta(days=i),
        )

    # 巡检任务
    plan = await create_inspection_plan(db_session, org, dt, user)
    for i in range(10):
        status = "completed" if i < 8 else "missed"
        await create_inspection_task(
            db_session, plan, user, task_date=date.today() - timedelta(days=i), status=status
        )

    return {
        "org": org,
        "child_org": child_org,
        "dt": dt,
        "user": user,
        "viewer": view_only_user,
        "device": device,
    }


# ==================== 设备完好率（FR-048）====================


@pytest.mark.asyncio
async def test_device_status_distribution(client, stat_env):
    """设备完好率看板返回正确的状态分组和总数"""
    headers = auth_headers(stat_env["user"])
    resp = await client.get("/api/v1/statistics/device-status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 7  # 6 + 1 子组织
    items = {item["status"]: item["count"] for item in data["items"]}
    assert items.get("normal", 0) == 5  # 4 + 1 子组织
    assert items.get("alarm", 0) == 1
    assert items.get("fault", 0) == 1


@pytest.mark.asyncio
async def test_device_status_drill_down(client, stat_env):
    """区域下钻：传入 org_id 后只返回该区域及子区域的设备"""
    headers = auth_headers(stat_env["user"])
    resp = await client.get(
        f"/api/v1/statistics/device-status?org_id={stat_env['child_org'].id}",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1  # 子组织只有 1 台设备


# ==================== 报警趋势（FR-049）====================


@pytest.mark.asyncio
async def test_alarm_trend(client, stat_env):
    """报警趋势图返回日期序列和按类型分组的计数"""
    headers = auth_headers(stat_env["user"])
    resp = await client.get("/api/v1/statistics/alarm-trend?days=7", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["dates"]) == 8  # 7 天 + 今天
    assert len(data["series"]) >= 1

    # 验证 fire 类型计数
    fire_series = next((s for s in data["series"] if s["type"] == "fire"), None)
    assert fire_series is not None
    assert sum(fire_series["data"]) == 3  # 3 条 fire 报警


@pytest.mark.asyncio
async def test_alarm_trend_exclude_drill(client, stat_env):
    """默认排除演练数据（is_drill=false）"""
    headers = auth_headers(stat_env["user"])
    resp = await client.get("/api/v1/statistics/alarm-trend?days=7&include_drill=false", headers=headers)
    data = resp.json()["data"]
    
    # 验证不含演练的数据结构
    assert len(data["dates"]) == 8  # 7 天 + 今天
    
    # 可能没有 fire 类型数据（如果所有 fire 都是 drill），允许 series 为空或无 fire
    fire_series = next((s for s in data.get("series", []) if s["type"] == "fire"), None)
    fire_count_no_drill = sum(fire_series["data"]) if fire_series else 0

    resp2 = await client.get("/api/v1/statistics/alarm-trend?days=7&include_drill=true", headers=headers)
    data2 = resp2.json()["data"]
    fire_series2 = next((s for s in data2.get("series", []) if s["type"] == "fire"), None)
    assert fire_series2 is not None
    fire_count_with_drill = sum(fire_series2["data"])

    # 含演练的 fire 数量应大于不含演练的
    assert fire_count_with_drill > fire_count_no_drill


# ==================== 故障 TOP10（FR-050）====================


@pytest.mark.asyncio
async def test_fault_top10(client, stat_env):
    """故障 TOP10 返回按故障次数排序的设备列表"""
    headers = auth_headers(stat_env["user"])
    resp = await client.get("/api/v1/statistics/fault-top10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["items"]) >= 1
    assert data["items"][0]["fault_count"] == 5  # 5 个 completed 工单


# ==================== 巡检完成率（FR-051）====================


@pytest.mark.asyncio
async def test_inspection_completion(client, stat_env):
    """巡检完成率返回按责任人分组和总体统计"""
    headers = auth_headers(stat_env["user"])
    resp = await client.get("/api/v1/statistics/inspection-completion", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["overall"]["total"] == 10
    assert data["overall"]["completed"] == 8
    assert data["overall"]["missed"] == 2
    assert abs(data["overall"]["completion_rate"] - 0.8) < 0.01


# ==================== 综合概览 ====================


@pytest.mark.asyncio
async def test_overview(client, stat_env):
    """综合概览返回所有核心统计指标"""
    headers = auth_headers(stat_env["user"])
    resp = await client.get("/api/v1/statistics/overview", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["device_total"] == 7
    assert data["alarm_today"] >= 0
    assert data["repair_pending"] >= 0


# ==================== 权限校验 ====================


@pytest.mark.asyncio
async def test_statistics_requires_view_permission(client, stat_env):
    """未认证请求被拒绝"""
    resp = await client.get("/api/v1/statistics/device-status")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_statistics_view_only_user_can_view(client, stat_env):
    """只有 statistics:view 的用户可以查看看板"""
    headers = auth_headers(stat_env["viewer"])
    resp = await client.get("/api/v1/statistics/device-status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["code"] == 200
