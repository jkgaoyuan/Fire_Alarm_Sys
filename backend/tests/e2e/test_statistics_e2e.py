"""
3.9 统计报表模块端到端测试 (E2E)

测试场景：
1. 完整导出流程 - 创建任务 → 轮询状态 → 下载文件
2. 权限验证 - 无 export 权限的用户无法创建导出
3. 注意：本测试使用 FastAPI ASGI transport 运行，不依赖外部服务器
"""
import pytest
from httpx import AsyncClient
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_e2e_export_workflow(client: AsyncClient, auth_headers):
    """
    E2E 测试：完整的报表导出流程
    1. 创建导出任务
    2. 轮询任务状态直到完成
    3. 下载文件
    4. 验证文件存在
    """
    # 步骤 1: 创建导出任务
    create_resp = await client.post(
        "/api/v1/reports/export",
        headers=auth_headers,
        json={
            "task_type": "device_status",
            "params": {"include_drill": False},
            "data": [
                {"status": "normal", "count": 450},
                {"status": "alarm", "count": 20},
                {"status": "fault", "count": 15}
            ],
            "format": "xlsx"
        }
    )
    
    assert create_resp.status_code == 200, f"创建任务失败：{create_resp.text}"
    task_data = create_resp.json()["data"]
    task_id = task_data["task_id"]
    task_no = task_data["task_no"]
    
    # 验证任务编号格式
    assert task_no.startswith("EXP_"), "任务编号应以前缀 EXP_开头"
    
    # 步骤 2: 轮询任务状态（最多轮询 10 次，每次间隔 1 秒）
    import asyncio
    
    max_polling_attempts = 10
    polling_interval = 1.0
    
    for attempt in range(max_polling_attempts):
        status_resp = await client.get(
            f"/api/v1/reports/export/{task_id}/status",
            headers=auth_headers
        )
        
        assert status_resp.status_code == 200
        
        status_data = status_resp.json()["data"]
        status = status_data["status"]
        
        if status == "completed":
            break
        elif status == "failed":
            pytest.fail(f"任务执行失败：{status_data.get('error_message', '未知错误')}")
        elif status == "running":
            if attempt < max_polling_attempts - 1:
                await asyncio.sleep(polling_interval)
            continue
        else:
            pytest.fail(f"无效的状态：{status}")
    
    # 步骤 3: 下载文件
    download_resp = await client.get(
        f"/api/v1/reports/export/{task_id}/download",
        headers=auth_headers
    )
    
    assert download_resp.status_code == 200, f"下载失败：{download_resp.text}"
    assert b".xlsx" in download_resp.content or b"PK" in download_resp.content[:2], \
        "文件应为 Excel 格式 (.xlsx)"
    
    # 步骤 4: 验证返回的数据大小（应该有实际内容）
    assert len(download_resp.content) > 0, "下载的文件为空"
    
    print("✅ E2E 导出流程测试通过")


@pytest.mark.asyncio
async def test_e2e_permission_denial(client: AsyncClient, viewer_auth_headers):
    """
    E2E 测试：权限验证
    只有 statistics:view 权限的用户（无 export）应该被拒绝创建导出任务
    """
    # 尝试创建导出任务
    resp = await client.post(
        "/api/v1/reports/export",
        headers=viewer_auth_headers,
        json={
            "task_type": "alarm_trend",
            "params": {"days": 7},
            "data": [],
            "format": "xlsx"
        }
    )
    
    assert resp.status_code == 403, f"应该被拒绝访问，但得到 {resp.status_code}"
    
    error_detail = resp.json().get("message", "")
    assert "statistics:export" in error_detail or "权限" in error_detail, \
        f"错误信息应该提到缺少的权限：{error_detail}"
    
    print("✅ E2E 权限验证测试通过")


@pytest.mark.asyncio
async def test_e2e_task_pagination(client: AsyncClient, auth_headers):
    """
    E2E 测试：任务列表分页查询
    创建多个任务并验证分页参数正常工作
    """
    # 创建 5 个任务
    for i in range(5):
        resp = await client.post(
            "/api/v1/reports/export",
            headers=auth_headers,
            json={
                "task_type": "fault_top10",
                "params": {},
                "data": [{"device_id": i}],
                "format": "csv"
            }
        )
        assert resp.status_code == 200
    
    # 查询第一页
    page1_resp = await client.get(
        "/api/v1/reports/export-tasks?page=1&page_size=2",
        headers=auth_headers
    )
    
    assert page1_resp.status_code == 200
    page1_data = page1_resp.json()["data"]
    assert page1_data["total"] >= 5, "总任务数应≥5"
    assert len(page1_data["items"]) == 2, "第一页应有 2 条记录"
    assert page1_data["page"] == 1
    assert page1_data["page_size"] == 2
    
    # 查询第二页
    page2_resp = await client.get(
        "/api/v1/reports/export-tasks?page=2&page_size=2",
        headers=auth_headers
    )
    
    assert page2_resp.status_code == 200
    page2_data = page2_resp.json()["data"]
    assert page2_data["page"] == 2
    assert len(page2_data["items"]) <= 2
    
    print("✅ E2E 任务分页测试通过")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
