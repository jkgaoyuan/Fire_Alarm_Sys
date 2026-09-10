"""
3.6 设备巡检 - API 端点测试（使用现有 fixtures）
=======================================================
运行方式：pytest backend/tests/test_inspection_api.py -v --tb=line
依赖主 conftest.py 中的 fixtures: client, test_user, test_client_with_user
"""

import pytest


@pytest.mark.asyncio
async def test_unauthorized_access(client):
    """TC-INS-001: 未认证请求应该返回 401"""
    
    # Create unauthenticated client
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as unauth_client:
        response = await unauth_client.get("/api/v1/inspection-plans")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_empty_plans(test_client_with_user):
    """TC-INS-002: 查询空计划列表"""
    
    response = await test_client_with_user.get("/api/v1/inspection-plans")
    
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 0
    assert len(data["items"]) == 0


@pytest.mark.asyncio
async def test_create_valid_plan(test_client_with_user):
    """TC-INS-003: 创建有效巡检计划"""
    
    payload = {
        "plan_name": "每日消防巡检",
        "cycle_type": "daily",
        "is_enabled": True,
    }
    
    response = await test_client_with_user.post(
        "/api/v1/inspection-plans",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["plan_name"] == "每日消防巡检"
    assert data["cycle_type"] == "daily"


@pytest.mark.asyncio
async def test_invalid_cycle_type(test_client_with_user):
    """TC-INS-004: 无效周期类型应返回 422"""
    
    payload = {
        "plan_name": "测试计划",
        "cycle_type": "invalid",
        "is_enabled": True,
    }
    
    response = await test_client_with_user.post(
        "/api/v1/inspection-plans",
        json=payload
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_empty_plan_name(test_client_with_user):
    """TC-INS-005: 空计划名应返回 422"""
    
    payload = {
        "plan_name": "",
        "cycle_type": "daily",
        "is_enabled": True,
    }
    
    response = await test_client_with_user.post(
        "/api/v1/inspection-plans",
        json=payload
    )
    
    assert response.status_code == 422
