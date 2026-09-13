"""
3.6 设备巡检 - API 端点测试（使用现有 fixtures）
=======================================================
运行方式：pytest tests/test_inspection_api.py -v --tb=short
依赖主 conftest.py 中的 fixtures: client, test_user, test_client_with_user

断言口径遵循 testing-guidelines 第三节：统一走响应信封 `code` / `message` / `data`，
而不是只看 HTTP 状态。

HTTP 状态码与信封 `code` 是两件事：新建按 REST 约定返回 HTTP 201，但**信封 code 恒为 200**
（见 `docs/plan/API_RESPONSE_FORMAT_SPECIFICATION.md` 原则 1 与前端检查项「是否检查了
`res.code === 200`」）。曾经三条写接口的信封写成 `code=201, message="Created"`，
被下面的 `assert_ok` 以「兼容 200/201」的方式掩盖，最终导致前端 PUT 报 "Created" 错误——
守护用例见 TC-INS-015，本辅助函数不得再放宽回 `in (200, 201)`。
"""

from datetime import date

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.permission import Permission
from app.models.user import Role, User


# ==================== 辅助函数 ====================

def assert_ok(response):
    """
    断言请求成功并返回 data。

    HTTP 允许 200/201（新建按 REST 约定是 201），但**信封 code 必须严格是 200**——
    放宽成 `in (200, 201)` 会把「更新接口返回创建语义信封」这类契约缺陷洗成绿色。
    """
    assert response.status_code in (200, 201), response.text
    body = response.json()
    assert body["code"] == 200, body
    return body.get("data")


async def create_plan(client, user_id, **overrides):
    """创建巡检计划的测试辅助函数"""
    payload = {
        "plan_name": "测试计划",
        "cycle_type": "daily",
        "responsible_user_id": user_id,
        "start_date": date.today().isoformat(),
    }
    payload.update(overrides)
    response = await client.post("/api/v1/inspection-plans", json=payload)
    return assert_ok(response)


# ==================== 基础用例 ====================

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
async def test_create_valid_plan(test_client_with_user, test_user):
    """TC-INS-003: 创建有效巡检计划"""

    payload = {
        "plan_name": "每日消防巡检",
        "cycle_type": "daily",
        "responsible_user_id": test_user.id,
        "start_date": date.today().isoformat(),
    }

    response = await test_client_with_user.post(
        "/api/v1/inspection-plans",
        json=payload
    )

    data = assert_ok(response)
    assert data["plan_name"] == "每日消防巡检"
    assert data["cycle_type"] == "daily"


@pytest.mark.asyncio
async def test_invalid_cycle_type(test_client_with_user, test_user):
    """TC-INS-004: 无效周期类型应返回 422"""

    payload = {
        "plan_name": "测试计划",
        "cycle_type": "invalid",
        "responsible_user_id": test_user.id,
        "start_date": date.today().isoformat(),
    }

    response = await test_client_with_user.post(
        "/api/v1/inspection-plans",
        json=payload
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=False,
    reason="后端 InspectionPlanCreate.plan_name 只有 max_length 无 min_length，"
    "空字符串可通过校验（HTTP 201）；前端表单已强制必填，期望后端对齐返回 422",
)
async def test_empty_plan_name(test_client_with_user, test_user):
    """TC-INS-005: 空计划名应返回 422（当前后端未拦截，作为缺陷探针）"""

    payload = {
        "plan_name": "",
        "cycle_type": "daily",
        "responsible_user_id": test_user.id,
        "start_date": date.today().isoformat(),
    }

    response = await test_client_with_user.post(
        "/api/v1/inspection-plans",
        json=payload
    )

    assert response.status_code == 422


# ==================== 操作列功能测试 ====================

@pytest.mark.asyncio
async def test_get_plan_detail(test_client_with_user, test_user):
    """TC-INS-006: 获取计划详情，返回数据应包含统计字段"""
    plan = await create_plan(test_client_with_user, test_user.id, plan_name="详情测试计划")

    response = await test_client_with_user.get(f"/api/v1/inspection-plans/{plan['id']}")
    data = assert_ok(response)

    assert data["plan_name"] == "详情测试计划"
    assert "total_tasks" in data
    assert "completed_tasks" in data
    assert "completion_rate" in data


@pytest.mark.asyncio
async def test_update_plan(test_client_with_user, test_user):
    """TC-INS-007: 更新巡检计划名称"""
    plan = await create_plan(test_client_with_user, test_user.id, plan_name="更新前")

    response = await test_client_with_user.put(
        f"/api/v1/inspection-plans/{plan['id']}",
        json={"plan_name": "更新后"},
    )
    data = assert_ok(response)

    assert data["plan_name"] == "更新后"


@pytest.mark.asyncio
async def test_delete_disabled_plan(test_client_with_user, test_user):
    """TC-INS-008: 删除已停用计划应成功，再次获取应不可见"""
    plan = await create_plan(
        test_client_with_user, test_user.id, plan_name="待删除计划", is_enabled=False
    )

    # 先停用
    await test_client_with_user.post(
        f"/api/v1/inspection-plans/{plan['id']}/toggle",
        json={"is_enabled": False},
    )

    # 删除
    response = await test_client_with_user.delete(f"/api/v1/inspection-plans/{plan['id']}")
    assert_ok(response)

    # 再次获取：资源已不存在（业务 404 口径见 testing-guidelines 第六节第 1 条）
    get_resp = await test_client_with_user.get(f"/api/v1/inspection-plans/{plan['id']}")
    assert get_resp.status_code == 404 or get_resp.json()["code"] == 404


@pytest.mark.asyncio
async def test_delete_enabled_plan_fails(test_client_with_user, test_user):
    """TC-INS-009: 删除已启用计划应失败并提示先停用"""
    plan = await create_plan(
        test_client_with_user, test_user.id, plan_name="已启用计划"
    )

    response = await test_client_with_user.delete(f"/api/v1/inspection-plans/{plan['id']}")

    assert response.status_code == 400
    assert "请先停用" in response.json()["detail"]


@pytest.mark.asyncio
async def test_toggle_plan_status(test_client_with_user, test_user):
    """TC-INS-010: 启用/停用计划状态应正确翻转"""
    plan = await create_plan(
        test_client_with_user, test_user.id, plan_name="切换状态计划", is_enabled=True
    )
    assert plan["is_enabled"] is True

    # 停用
    resp = await test_client_with_user.post(
        f"/api/v1/inspection-plans/{plan['id']}/toggle",
        json={"is_enabled": False},
    )
    assert assert_ok(resp)["is_enabled"] is False

    # 再启用
    resp = await test_client_with_user.post(
        f"/api/v1/inspection-plans/{plan['id']}/toggle",
        json={"is_enabled": True},
    )
    assert assert_ok(resp)["is_enabled"] is True


@pytest.mark.asyncio
async def test_write_success_envelope_code_is_200(test_client_with_user, test_user):
    """
    TC-INS-015: 写接口成功时信封 code 必须是 200，不能沿用创建接口的 201/"Created"。

    不修会怎样：`PlanForm.vue` 的提交分支是 `if (result.code === 200)`。
    PUT 返回信封 code=201 时数据其实已落库，但前端判定为失败 →
    弹出一条文案为 "Created" 的错误提示，且不 emit success、不关闭弹窗、不刷新列表。
    `/toggle` 有同样的缺陷，只是 `Plan.vue` 恰好不读 code 才没暴露。
    """
    plan = await create_plan(
        test_client_with_user, test_user.id, plan_name="信封校验计划"
    )

    resp = await test_client_with_user.put(
        f"/api/v1/inspection-plans/{plan['id']}",
        json={"plan_name": "信封校验计划-改"},
    )
    body = resp.json()
    assert body["code"] == 200, f"PUT 信封 code 应为 200，实际 {body['code']}"
    assert body["message"] != "Created", "更新接口不应返回创建语义的 message"

    resp = await test_client_with_user.post(
        f"/api/v1/inspection-plans/{plan['id']}/toggle",
        json={"is_enabled": False},
    )
    body = resp.json()
    assert body["code"] == 200, f"/toggle 信封 code 应为 200，实际 {body['code']}"
    assert body["message"] != "Created", "状态切换不应返回创建语义的 message"


@pytest.mark.asyncio
async def test_generate_tasks_are_committed(test_client_with_user, test_user, db_session):
    """
    TC-INS-016: 生成的任务必须真正提交，rollback 之后仍应在库里。

    不修会怎样：`generate_tasks_for_plan` 只 `db.add()` + `flush()`，不 commit；
    而 `get_db` 在 finally 里只 close 不 commit → 事务被回滚。
    线上实测过：接口返回 7 条任务、`inspection_tasks` 表 0 行——
    前端弹「已生成 7 天的巡检任务」，任务页却是空的。

    为什么旧用例抓不到：测试的 client 与 db_session 共用同一个会话，
    未提交的行对同一个会话可见，于是 `total` 照样是对的。
    这里用 `rollback()` 主动丢弃未提交变更——提交过的行不受影响，只 flush 的会消失。
    """
    plan = await create_plan(
        test_client_with_user, test_user.id, plan_name="提交校验计划", is_enabled=True
    )

    resp = await test_client_with_user.post(
        f"/api/v1/inspection-plans/{plan['id']}/generate", json={"days": 3}
    )
    assert len(assert_ok(resp)) == 3

    # 丢弃该会话里一切未提交的变更；若上面没 commit，任务会就此消失
    await db_session.rollback()

    from sqlalchemy import func, select

    from app.models.inspection import InspectionTask

    total = (
        await db_session.execute(
            select(func.count()).select_from(InspectionTask).where(
                InspectionTask.plan_id == plan["id"]
            )
        )
    ).scalar_one()
    assert total == 3, f"生成后未提交：rollback 后只剩 {total} 条，期望 3 条"


@pytest.mark.asyncio
async def test_generate_tasks(test_client_with_user, test_user):
    """TC-INS-011: 手动生成巡检任务应返回任务列表"""
    plan = await create_plan(
        test_client_with_user,
        test_user.id,
        plan_name="生成任务计划",
        is_enabled=True,
    )

    response = await test_client_with_user.post(
        f"/api/v1/inspection-plans/{plan['id']}/generate",
        json={"days": 7},
    )
    data = assert_ok(response)

    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_generate_tasks_without_body(test_client_with_user, test_user):
    """TC-INS-013: 生成任务不带 body 时不应 422（回归：曾因 data: dict 必填而报 Field required）"""
    plan = await create_plan(
        test_client_with_user,
        test_user.id,
        plan_name="空 body 生成计划",
        is_enabled=True,
    )

    response = await test_client_with_user.post(
        f"/api/v1/inspection-plans/{plan['id']}/generate"
    )

    assert response.status_code != 422, response.text
    data = assert_ok(response)
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_toggle_without_body_flips_status(test_client_with_user, test_user):
    """TC-INS-014: 停用接口不带 body 时按取反处理，不应 422"""
    plan = await create_plan(
        test_client_with_user, test_user.id, plan_name="空 body 切换计划", is_enabled=True
    )

    response = await test_client_with_user.post(
        f"/api/v1/inspection-plans/{plan['id']}/toggle"
    )

    assert response.status_code != 422, response.text
    assert assert_ok(response)["is_enabled"] is False


@pytest.mark.asyncio
async def test_insufficient_permission_returns_403(client, db_session):
    """TC-INS-012: 仅拥有 view 权限的用户调用写操作应返回 403"""
    # 创建仅含 inspection:view 权限的用户
    # 注意：关联必须在 flush 之前完成，否则异步会话下会触发懒加载（MissingGreenlet）
    role = Role(role_code="viewer_only", role_name="Viewer Only", is_builtin=False)
    view_perm = Permission(perm_code="inspection:view", perm_name="View", perm_type="api")
    role.permissions.append(view_perm)
    db_session.add(role)
    await db_session.flush()

    viewer = User(
        username="viewer_only",
        password_hash=get_password_hash("Test1234"),
        real_name="Viewer",
        status="active",
        data_scope="all",
    )
    viewer.roles.append(role)
    db_session.add(viewer)
    await db_session.commit()
    await db_session.refresh(viewer, ["roles"])

    token = create_access_token(data={"sub": str(viewer.id), "jti": "test-jti-viewer"})
    headers = {"Authorization": f"Bearer {token}"}

    # 创建：403 且 message 含「缺少权限」（testing-guidelines 第六节第 2 条）
    resp = await client.post(
        "/api/v1/inspection-plans",
        headers=headers,
        json={
            "plan_name": "无权创建",
            "cycle_type": "daily",
            "responsible_user_id": viewer.id,
            "start_date": date.today().isoformat(),
        },
    )
    assert resp.status_code == 403
    assert "缺少权限" in resp.json()["message"]

    # 更新（权限检查先于资源存在性检查）
    resp = await client.put(
        "/api/v1/inspection-plans/99999",
        headers=headers,
        json={"plan_name": "无权更新"},
    )
    assert resp.status_code == 403
    assert "缺少权限" in resp.json()["message"]

    # 删除
    resp = await client.delete(
        "/api/v1/inspection-plans/99999",
        headers=headers,
    )
    assert resp.status_code == 403
    assert "缺少权限" in resp.json()["message"]
