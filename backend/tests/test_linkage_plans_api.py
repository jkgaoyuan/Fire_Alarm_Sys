"""
联动预案 HTTP 端点契约（3.4-B4）
================================

覆盖两件事：

1. **鉴权**：`GET /linkage-plans` 此前没有任何鉴权依赖，代码里只留了一行
   `# TODO: 添加权限验证`，实测未带 token 即返回 200 + 预案数据
   （含 actions 动作配置），而同文件的 `/{plan_id}` 是 401。
2. **响应信封**：7 个端点返回裸模型/裸 dict，前端只得用
   `if (res && Array.isArray(res.items))` 这种「猜形状」的写法去适配
   （CLAUDE.md「教训 1」正是记录此事——当时把前端迁就违规后端当成了修复）。

既有的 `tests/test_linkage_engine.py` 测引擎逻辑，不经过 ASGI，看不到这两类问题。
"""

import pytest

from tests.auth_helpers import auth_headers, create_user_with_perms

LIST_URL = "/api/v1/linkage-plans"


# ==================== 鉴权 ====================

@pytest.mark.asyncio
async def test_list_requires_authentication(client):
    """
    TC-LP-001: 未认证访问预案列表必须 401。

    不修会怎样：该端点无任何鉴权依赖，未带 token 直接返回 200 + 数据。
    预案含 actions 动作配置（联动哪些设备、什么动作），属可操作情报，
    泄露后可被用于摸清消防联动策略。
    """
    resp = await client.get(LIST_URL)

    assert resp.status_code == 401, f"未认证却拿到 {resp.status_code}"


@pytest.mark.asyncio
async def test_list_requires_view_permission(client, db_session):
    """TC-LP-002: 已登录但缺 linkage:view 应是 403，不是 401"""
    user = await create_user_with_perms(db_session, "lp_noperm", ["device:view"])

    resp = await client.get(LIST_URL, headers=auth_headers(user))

    assert resp.status_code == 403
    assert "缺少权限" in resp.json()["message"]


@pytest.mark.asyncio
async def test_list_accessible_with_view_permission(client, db_session):
    """TC-LP-003: 有 linkage:view 的正常可读（值班员的实际权限组合）"""
    user = await create_user_with_perms(
        db_session, "lp_view", ["linkage:view", "linkage:execute"]
    )

    resp = await client.get(LIST_URL, headers=auth_headers(user))

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_sibling_endpoints_keep_their_auth(client):
    """
    TC-LP-004: 同文件其它端点的鉴权不得被顺手改掉（回归护栏）。

    列表端点漏鉴权很可能就是「复制同文件代码时删掉了 dependencies」，
    固定住其余端点，防止修复时反向踩踏。
    """
    assert (await client.get(f"{LIST_URL}/1")).status_code == 401
    assert (await client.post(f"{LIST_URL}/1/toggle")).status_code == 401
    assert (await client.post(f"{LIST_URL}/execute")).status_code == 401
