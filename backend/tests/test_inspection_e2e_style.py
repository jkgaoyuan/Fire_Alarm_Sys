"""
3.6 设备巡检 - E2E 风格测试（仅测试 API 端点）
=======================================================
运行方式：pytest backend/tests/test_inspection_e2e_style.py -v --tb=line
仅验证 API 功能，不直接操作数据库 session
"""

import pytest


@pytest.mark.asyncio
async def test_unauthorized_access_to_inspection_plan(test_client):
    """TC-E2E-001: 未授权访问应返回 401"""
    
    response = await test_client.get("/api/v1/inspection-plans")
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_inspection_plans_empty(client, test_user):
    """TC-E2E-002: 已认证用户查询空列表"""
    
    # 生成 token
    from app.core.security import create_access_token
    token = create_access_token(
        data={"sub": str(test_user.id), "jti": "test-jti-list"}
    )
    
    response = await client.get(
        "/api/v1/inspection-plans",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, dict)
    assert data["total"] == 0
    assert "items" in data
    assert len(data["items"]) == 0


@pytest.mark.asyncio  
async def test_create_inspection_plan_valid(client, test_user):
    """TC-E2E-003: 创建有效的巡检计划"""
    
    # 生成 token
    from app.core.security import create_access_token
    token = create_access_token(
        data={"sub": str(test_user.id), "jti": "test-jti-create"}
    )
    
    # 准备请求数据
    payload = {
        "plan_name": "每日消防巡检",
        "cycle_type": "daily",
        "is_enabled": True,
    }
    
    # 发送 POST 请求
    response = await client.post(
        "/api/v1/inspection-plans",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["plan_name"] == "每日消防巡检"
    assert data["cycle_type"] == "daily"
    assert data["is_enabled"] == True


@pytest.mark.asyncio
async def test_invalid_cycle_type(client, test_user):
    """TC-E2E-004: 无效的周期类型应返回 422"""
    
    from app.core.security import create_access_token
    token = create_access_token(
        data={"sub": str(test_user.id), "jti": "test-jti-invalid-cycle"}
    )
    
    payload = {
        "plan_name": "无效周期计划",
        "cycle_type": "invalid_cycle",
        "is_enabled": True,
    }
    
    response = await client.post(
        "/api/v1/inspection-plans",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_empty_plan_name(client, test_user):
    """TC-E2E-005: 空计划名应返回 422"""
    
    from app.core.security import create_access_token
    token = create_access_token(
        data={"sub": str(test_user.id), "jti": "test-jti-empty-name"}
    )
    
    payload = {
        "plan_name": "",
        "cycle_type": "daily",
        "is_enabled": True,
    }
    
    response = await client.post(
        "/api/v1/inspection-plans",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    
    assert response.status_code == 422
