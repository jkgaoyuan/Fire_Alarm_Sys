"""
联动日志 HTTP 端点契约（3.4-B5）
================================

`tests/test_linkage_logs.py` 测的是 CRUD 层（mock db），**完全不碰 HTTP**，
所以这个文件里的端点级缺陷一直没人看得见：

- 列表端点曾**整个漏掉鉴权**：不带 token 就返回 200 + 数据
  （同文件的 `/{log_id}` 与 `/export` 都要求 `linkage:view`）
- 三个端点的响应形状不一致（已在后续提交统一为信封）

本文件走真实 ASGI 调用，覆盖「鉴权」与「响应信封」两件事。
"""

import pytest

from tests.auth_helpers import auth_headers, create_user_with_perms


async def make_linkage_user(db_session, username: str, perm_codes: list[str]):
    """建一个只持有指定权限码的用户（通用构造器见 tests/auth_helpers.py）"""
    return await create_user_with_perms(db_session, username, perm_codes)


def headers_for(user) -> dict:
    return auth_headers(user)


# ==================== 鉴权 ====================

@pytest.mark.asyncio
async def test_list_requires_authentication(client):
    """
    TC-LOG-001: 未认证访问联动日志列表必须 401。

    不修会怎样：该端点曾无任何鉴权依赖，未带 token 直接返回 200 + 数据。
    日志含 alarm_id / plan_id / target_device_id / result_message，
    等于把跨组织的业务数据对外公开——而同文件的详情与导出端点都是 401。
    """
    resp = await client.get("/api/v1/alarm-linkage-logs")

    assert resp.status_code == 401, f"未认证却拿到 {resp.status_code}"


@pytest.mark.asyncio
async def test_list_requires_view_permission(client, db_session):
    """TC-LOG-002: 已登录但缺 linkage:view 仍是 403，不是 401"""
    user = await make_linkage_user(db_session, "lg_noperm", ["device:view"])

    resp = await client.get(
        "/api/v1/alarm-linkage-logs", headers=headers_for(user)
    )

    assert resp.status_code == 403
    assert "缺少权限" in resp.json()["message"]


@pytest.mark.asyncio
async def test_sibling_endpoints_keep_their_auth(client):
    """
    TC-LOG-003: 同文件的详情与导出端点鉴权不得被顺手改掉（回归护栏）。

    列表端点漏鉴权很可能就是「复制同文件代码时删掉了 dependencies」，
    所以固定住另外两个，防止修复时反向踩踏。
    """
    assert (await client.get("/api/v1/alarm-linkage-logs/1")).status_code == 401
    assert (await client.get("/api/v1/alarm-linkage-logs/export")).status_code == 401


# ==================== 响应信封 ====================

@pytest.mark.asyncio
async def test_list_returns_envelope(client, db_session):
    """
    TC-LOG-004: 列表按统一信封返回 {code, message, data}。

    不修会怎样：此前返回裸 {items,total,page,page_size}。前端拦截器两种形状
    都放行，组件按 res.data.items 读会拿到 undefined，被 `|| {}` 兜底后
    页面显示空表——**不报错**。维修统计页全 0 就是同一类问题。
    """
    user = await make_linkage_user(db_session, "lg_view", ["linkage:view"])

    resp = await client.get("/api/v1/alarm-linkage-logs", headers=headers_for(user))
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["message"] == "success"
    # 分页字段必须落在 data 里，而不是顶层
    assert set(body["data"]) >= {"items", "total", "page", "page_size"}
    assert "items" not in body, "裸字段又漏到顶层了"


@pytest.mark.asyncio
async def test_detail_returns_envelope(client, db_session):
    """TC-LOG-005: 详情同样走信封；资源不存在时是 404 而非 200 空体"""
    user = await make_linkage_user(db_session, "lg_view2", ["linkage:view"])
    headers = headers_for(user)

    resp = await client.get("/api/v1/alarm-linkage-logs/999999", headers=headers)
    assert resp.status_code == 404
