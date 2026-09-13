"""
前后端契约缺陷回归守护
======================
本文件集中守护 2026-09-13 那轮「前端 API 契约比对」中确认并修复的缺陷。
每条用例都对应一个已修复的具体故障，docstring 写明「不修会怎样」。

约定：断言统一走响应信封 `code`（testing-guidelines 第三节）。
"""
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token, get_password_hash
from app.models.permission import Permission
from app.models.user import Role, User
from app.schemas.alarm import AlarmOut
from app.schemas.device import DeviceCreate
from app.schemas.report_export import ExportTaskOut


# ==================== 夹具 ====================

async def make_user_with_perms(db_session, username: str, perm_codes: list[str]) -> User:
    """
    建一个只持有指定权限码的用户。

    注意：角色与权限的关联必须在 flush 之前完成，否则异步会话下
    `role.permissions` 会触发懒加载并抛 MissingGreenlet。
    """
    role = Role(role_code=f"{username}_role", role_name=username, is_builtin=False)
    for code in perm_codes:
        role.permissions.append(
            Permission(perm_code=code, perm_name=code, perm_type="api")
        )
    db_session.add(role)
    await db_session.flush()

    user = User(
        username=username,
        password_hash=get_password_hash("Test1234"),
        real_name=username,
        status="active",
        data_scope="all",
    )
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user, ["roles"])
    return user


def auth_headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id), "jti": f"jti-{user.id}"})
    return {"Authorization": f"Bearer {token}"}


# ==================== 响应字段被 schema 丢弃 ====================

def test_alarm_out_exposes_reset_remark():
    """
    报警输出必须回显 reset_remark。

    不修会怎样：`AlarmOut.model_validate(...).model_dump()` 会丢掉该字段，
    报警详情页的「复位备注」永远显示 '-'，操作员填的备注石沉大海。
    """
    payload = {
        "id": 1,
        "device_id": 1,
        "alarm_type": "fire",
        "status": "reset",
        "is_drill": False,
        "created_at": "2026-09-13T10:00:00",
        "reset_by": 9,
        "reset_remark": "现场已确认恢复",
    }
    out = AlarmOut.model_validate(payload).model_dump()

    assert out["reset_remark"] == "现场已确认恢复"
    assert out["reset_by"] == 9


def test_export_task_out_exposes_params():
    """
    导出任务输出必须回显 params。

    不修会怎样：导出中心的「重试」把 row.params 原样回传，字段缺失使其恒为
    undefined → 请求体 params 为空 → 后端按 0 行同步导出，**静默产出空文件**。
    """
    payload = {
        "id": 1,
        "task_no": "EX-20260913-001",
        "task_type": "alarm_trend",
        "status": "completed",
        "created_at": "2026-09-13T10:00:00",
        "params": {"org_id": 21, "start": "2026-09-01"},
    }
    out = ExportTaskOut.model_validate(payload).model_dump()

    assert out["params"] == {"org_id": 21, "start": "2026-09-01"}


# ==================== 路由注册顺序 ====================

def _route_paths() -> list[str]:
    from app.main import app

    return [getattr(r, "path", "") for r in app.routes]


def test_export_route_registered_before_log_id_route():
    """
    `/alarm-linkage-logs/export` 必须在 `/{log_id}` 之前注册。

    不修会怎样：Starlette 按注册顺序匹配，`{log_id}` 段无正则约束会把
    字面量 "export" 当成 log_id 捕获 → int 解析失败 → 导出恒定 422。
    """
    paths = _route_paths()
    export_idx = paths.index("/api/v1/alarm-linkage-logs/export")
    detail_idx = paths.index("/api/v1/alarm-linkage-logs/{log_id}")

    assert export_idx < detail_idx, "export 路由被 /{log_id} 遮蔽，请求会 422"


def test_vestigial_linkage_plans_logs_routes_removed():
    """
    `linkage_plans.py` 里那三条 `/logs*` 副本已删除。

    不修会怎样：它们被 `/{plan_id}` 遮蔽而永久不可达，同时与
    `/alarm-linkage-logs/*` 完全重复，形成两套做同一件事的接口。
    """
    paths = _route_paths()

    assert "/api/v1/linkage-plans/logs" not in paths
    assert "/api/v1/linkage-plans/logs/{log_id}" not in paths
    assert "/api/v1/linkage-plans/logs/export" not in paths
    # 功能由独立模块承接，不应一并删掉
    assert "/api/v1/alarm-linkage-logs" in paths


# ==================== 写接口 body 可省略 ====================

@pytest.mark.asyncio
async def test_linkage_toggle_accepts_explicit_state(client, db_session):
    """
    `/linkage-plans/{id}/toggle` 应按 body 里的 is_enabled 设置目标状态。

    不修会怎样：前端第二参数被丢弃、后端盲取反，`el-switch` 双击会
    让界面显示与库中状态永久相反。
    """
    from app.models.linkage import LinkagePlan

    user = await make_user_with_perms(db_session, "lg_chief", ["linkage:update"])

    plan = LinkagePlan(
        plan_name="联动预案",
        org_id=1,
        fire_type="fire",
        is_enabled=True,
        created_by=user.id,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)

    resp = await client.post(
        f"/api/v1/linkage-plans/{plan.id}/toggle",
        json={"is_enabled": False},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["is_enabled"] is False

    # 再显式传 False（而非取反），状态应保持 False
    resp = await client.post(
        f"/api/v1/linkage-plans/{plan.id}/toggle",
        json={"is_enabled": False},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_enabled"] is False, "显式设置被当成了取反"


# ==================== 设备回收站 ====================

@pytest.mark.asyncio
async def test_devices_include_deleted_and_restore(client, db_session):
    """
    回收站视图能列出已删除档案，并能恢复。

    不修会怎样：软删设备在任何列表都不可见，而后端冲突提示却让用户去调
    `POST /devices/{id}/restore`——一个没有任何 UI 入口的接口，编码被永久占死。
    """
    from app.models.device_type import DeviceType
    from app.models.organization import Organization
    from app.services import device_service

    user = await make_user_with_perms(
        db_session, "dev_admin", ["device:view", "device:create", "device:delete"]
    )

    org = Organization(org_name="总部大楼", org_type="building")
    dtype = DeviceType(type_code="smoke", type_name="烟感探测器", category="detector")
    db_session.add_all([org, dtype])
    await db_session.commit()
    await db_session.refresh(org)
    await db_session.refresh(dtype)

    created = await device_service.create_device(
        db_session,
        DeviceCreate(
            device_code="REG-001",
            device_name="回收站用例设备",
            type_id=dtype.id,
            org_id=org.id,
            install_date=date(2026, 9, 1),
        ),
        user,
    )
    device_id = created.id
    await device_service.delete_device(db_session, device_id, user)

    headers = auth_headers(user)

    # 默认视图看不到
    resp = await client.get("/api/v1/devices", headers=headers)
    assert resp.json()["data"]["total"] == 0

    # 回收站视图能看到
    resp = await client.get(
        "/api/v1/devices", params={"include_deleted": True}, headers=headers
    )
    items = resp.json()["data"]["items"]
    assert [d["id"] for d in items] == [device_id]
    assert items[0]["is_deleted"] is True

    # 恢复后回到默认视图
    resp = await client.post(f"/api/v1/devices/{device_id}/restore", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["code"] == 200

    resp = await client.get("/api/v1/devices", headers=headers)
    assert resp.json()["data"]["total"] == 1


# ==================== 角色关键字搜索 ====================

@pytest.mark.asyncio
async def test_roles_keyword_filter_actually_filters(client, db_session):
    """
    `GET /roles?keyword=` 应同时匹配角色编码与角色名称。

    不修会怎样：前端角色管理页只有一个搜索框并传 `keyword`，而后端没有该参数，
    FastAPI 静默忽略未知 query → 搜索框看似可用，实际**永远返回全量列表**。
    """
    user = await make_user_with_perms(db_session, "sys_admin", ["system:role"])

    db_session.add_all(
        [
            Role(role_code="fire_chief", role_name="消防主管", is_builtin=True),
            Role(role_code="duty_officer", role_name="消防值班员", is_builtin=True),
        ]
    )
    await db_session.commit()

    headers = auth_headers(user)

    # 不带 keyword 时应能看到全部种子角色（夹具用户自身的角色也会出现在列表里，
    # 故断言「包含」而不是精确总数）
    resp = await client.get("/api/v1/roles", headers=headers)
    codes = {r["role_code"] for r in resp.json()["data"]["items"]}
    assert {"fire_chief", "duty_officer"} <= codes

    # 按名称模糊匹配
    resp = await client.get("/api/v1/roles", params={"keyword": "主管"}, headers=headers)
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["role_code"] == "fire_chief"

    # 按编码模糊匹配
    resp = await client.get("/api/v1/roles", params={"keyword": "duty"}, headers=headers)
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["role_name"] == "消防值班员"
