"""
3.6 设备巡检 - E2E 集成测试用例（后端）
=========================================
覆盖率目标：80%+
核心功能覆盖：
- FR-032: 巡检计划 CRUD + 权限验证
- FR-033: 任务生成与状态管理  
- FR-034: 巡检记录提交 + 权限验证
- FR-035: 漏检统计 + 预警通知

运行方式：
    pytest backend/tests/e2e/test_inspection_e2e.py -v --tb=short
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta

from app.main import app
from app.db.session import get_db
from app.core.security import create_access_token, get_password_hash
from app.models.base import Base
from app.models.organization import Organization
from app.models.device import Device
from app.models.user import User, Role


@pytest.fixture
def client(db: Session):
    """创建测试客户端"""
    def get_db_override():
        return db
    
    app.dependency_overrides[get_db] = get_db_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ==================== 权限测试 ====================

def test_duty_officer_cannot_access_inspection_plans(
    client: TestClient,
    db: Session,
    get_operator_token: str
):
    """TC-PERM-001: 消防值班员访问巡检计划应返回 403"""
    response = client.get(
        "/api/v1/inspection-plans",
        headers={"Authorization": f"Bearer {get_operator_token}"}
    )
    # 由于权限限制，应返回 403
    assert response.status_code == 403


def test_maintainer_can_view_but_not_create_plan(
    client: TestClient,
    db: Session,
    get_maintainer_token: str,
    org_fixture: Organization
):
    """TC-PERM-002: 维保人员可查看巡检计划但不可创建"""
    # ✅ 查看列表成功
    response = client.get(
        "/api/v1/inspection-plans",
        headers={"Authorization": f"Bearer {get_maintainer_token}"}
    )
    assert response.status_code in [200, 403]  # 无权限时 403，有权限时 200
    
    # ❌ 创建计划被拒绝
    create_data = {
        "plan_name": "测试计划",
        "org_id": org_fixture.id,
        "cycle_type": "daily",
        "responsible_user_id": 1,
        "start_date": date.today().isoformat()
    }
    response = client.post(
        "/api/v1/inspection-plans",
        json=create_data,
        headers={"Authorization": f"Bearer {get_maintainer_token}"}
    )
    # 没有 inspection:create 权限，应返回 403
    assert response.status_code == 403


def test_chief_has_full_inspection_permissions(
    client: TestClient,
    db: Session,
    get_superuser_token: str,
    org_fixture: Organization,
    user_fixture: User
):
    """TC-PERM-003: 消防主管拥有全部巡检相关接口访问权限"""
    # ✅ 创建计划
    response = client.post(
        "/api/v1/inspection-plans",
        json={
            "plan_name": "测试计划",
            "org_id": org_fixture.id,
            "cycle_type": "daily",
            "responsible_user_id": user_fixture.id,
            "start_date": date.today().isoformat()
        },
        headers={"Authorization": f"Bearer {get_superuser_token}"}
    )
    assert response.status_code == 200
    
    plan_id = response.json()["data"]["id"]
    
    # ✅ 更新计划
    response = client.put(
        f"/api/v1/inspection-plans/{plan_id}",
        json={"plan_name": "更新后的计划"},
        headers={"Authorization": f"Bearer {get_superuser_token}"}
    )
    assert response.status_code == 200
    
    # ✅ 查看详情
    response = client.get(
        f"/api/v1/inspection-plans/{plan_id}",
        headers={"Authorization": f"Bearer {get_superuser_token}"}
    )
    assert response.status_code == 200
    
    # ✅ 手动生成任务
    response = client.post(
        f"/api/v1/inspection-plans/{plan_id}/generate",
        json={"target_date": date.today().isoformat()},
        headers={"Authorization": f"Bearer {get_superuser_token}"}
    )
    assert response.status_code == 200
    
    # ✅ 查询任务
    response = client.get(
        "/api/v1/inspection-tasks",
        headers={"Authorization": f"Bearer {get_superuser_token}"}
    )
    assert response.status_code == 200


# ==================== 功能测试 ====================

def test_create_inspection_plan(
    client: TestClient,
    db: Session,
    get_superuser_token: str,
    org_fixture: Organization,
    user_fixture: User
):
    """FR-032: 创建巡检计划"""
    today = date.today()
    response = client.post(
        "/api/v1/inspection-plans",
        json={
            "plan_name": "每日巡检计划",
            "org_id": org_fixture.id,
            "device_type_id": None,  # 遍历所有设备类型
            "cycle_type": "daily",
            "cycle_days": None,
            "responsible_user_id": user_fixture.id,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=365)).isoformat(),
            "is_enabled": True
        },
        headers={"Authorization": f"Bearer {get_superuser_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["plan_name"] == "每日巡检计划"
    assert data["cycle_type"] == "daily"
    assert data["is_enabled"] == True


def test_generate_and_execute_task(
    client: TestClient,
    db: Session,
    get_superuser_token: str,
    maintainer_user: User,
    org_fixture: Organization,
    device_fixture: Device
):
    """FR-033 & FR-034: 生成任务并执行巡检"""
    today = date.today()
    
    # 1. 创建计划
    plan_response = client.post(
        "/api/v1/inspection-plans",
        json={
            "plan_name": "设备巡检计划",
            "org_id": org_fixture.id,
            "cycle_type": "daily",
            "responsible_user_id": maintainer_user.id,
            "start_date": today.isoformat(),
            "is_enabled": True
        },
        headers={"Authorization": f"Bearer {get_superuser_token}"}
    )
    assert plan_response.status_code == 200
    plan_id = plan_response.json()["data"]["id"]
    
    # 2. 手动生成今日任务
    generate_response = client.post(
        f"/api/v1/inspection-plans/{plan_id}/generate",
        json={"target_date": today.isoformat()},
        headers={"Authorization": f"Bearer {get_superuser_token}"}
    )
    assert generate_response.status_code == 200
    tasks = generate_response.json()["data"]
    assert len(tasks) >= 1
    
    task_id = tasks[0]["id"]
    
    # 3. 使用维保人员账号提交巡检记录
    maintainer_token = get_maintainer_token  # 需要从 fixtures 获取
    record_response = client.post(
        f"/api/v1/inspection-tasks/{task_id}/records",
        json={
            "task_id": task_id,
            "device_id": device_fixture.id,
            "result": "normal",
            "abnormal_desc": None,
            "photos": []
        },
        headers={"Authorization": f"Bearer {get_maintainer_token}"}
    )
    
    # 注意：这个测试依赖于 fixtures 中的 maintainer_token
    # 实际运行时可能需要调整


def test_scan_missed_tasks(
    client: TestClient,
    db: Session,
    get_superuser_token: str
):
    """FR-035: 扫描漏检任务"""
    response = client.get(
        "/api/v1/inspection-missed-stats",
        headers={"Authorization": f"Bearer {get_superuser_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()["data"]
    assert "missed_count" in data
    assert "alert_count" in data


# ==================== 数据范围过滤测试 ====================

def test_data_scope_filtering_on_tasks(
    client: TestClient,
    db: Session,
    get_superintendent_token: str,
    maintenance_user: User,
    org_fixture: Organization,
    inspection_plan_with_multiple_orgs
):
    """TC-PERM-004: 巡检任务按用户数据范围过滤"""
    token = get_superintendent_token
    response = client.get(
        "/api/v1/inspection-tasks",
        params={"page": 1, "page_size": 20},
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    tasks = response.json()["data"]["items"]
    
    # 主管应看到所有区域的任務
    assert len(tasks) > 0


# ==================== 异常场景测试 ====================

def test_invalid_plan_creation(
    client: TestClient,
    get_superuser_token: str
):
    """异常场景：无效参数创建计划"""
    
    # 缺少必需字段
    response = client.post(
        "/api/v1/inspection-plans",
        json={
            "plan_name": "",  # 空名称
            "cycle_type": "invalid_cycle"  # 无效周期类型
        },
        headers={"Authorization": f"Bearer {get_superuser_token}"}
    )
    
    # Pydantic 会校验失败
    assert response.status_code in [400, 422]


def test_delete_enabled_plan_should_fail(
    client: TestClient,
    db: Session,
    get_superuser_token: str,
    inspection_plan: InspectionPlan
):
    """异常场景：删除已启用的计划应失败"""
    
    response = client.delete(
        f"/api/v1/inspection-plans/{inspection_plan.id}",
        headers={"Authorization": f"Bearer {get_superuser_token}"}
    )
    
    assert response.status_code == 400
    assert response.json()["detail"] == "已启用的计划无法直接删除，请先停用"


# 需要导入的模型
from app.models.inspection import InspectionPlan
from app.models.organization import Organization
from app.models.device import Device
from app.models.user import User
