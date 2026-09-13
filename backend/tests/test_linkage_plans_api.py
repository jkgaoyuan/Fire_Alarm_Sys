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


# ==================== 响应信封 ====================

async def _view_user(db_session, name="lp_env"):
    return await create_user_with_perms(db_session, name, ["linkage:view"])


@pytest.mark.asyncio
async def test_list_returns_envelope(client, db_session):
    """
    TC-LP-005: 列表按统一信封返回 `{code, message, data}`。

    不修会怎样：此前返回裸 `LinkagePlanPagination`。前端拦截器对两种形状都
    放行，组件读 `res.data.items` 拿到 undefined 后被兜底成空表——**不报错**。
    3.4 当时的选择是改成 `if (res && Array.isArray(res.items))` 去适配违规后端
    （CLAUDE.md「教训 1」把这个当成了修复），偏离因此一路固化。
    """
    user = await _view_user(db_session)

    resp = await client.get(LIST_URL, headers=auth_headers(user))
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["message"] == "success"
    assert set(body["data"]) >= {"items", "total", "page", "page_size"}
    assert "items" not in body, "裸字段又漏到顶层了"


@pytest.mark.asyncio
async def test_detail_not_found_keeps_404(client, db_session):
    """TC-LP-006: 信封改造不得把「资源不存在」的 404 吞成 200"""
    user = await _view_user(db_session, "lp_env2")

    resp = await client.get(f"{LIST_URL}/999999", headers=auth_headers(user))

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_returns_envelope(db_session, client):
    """TC-LP-007: 创建预案走信封，且内层业务字段落在 data 里"""
    user = await create_user_with_perms(
        db_session, "lp_creator", ["linkage:view", "linkage:create"]
    )

    resp = await client.post(
        LIST_URL,
        json={
            "plan_name": "信封校验预案",
            "org_id": 1,
            "fire_type": "fire",
            "actions": [{"action_type": "start_exhaust", "params": {}}],
        },
        headers=auth_headers(user),
    )
    body = resp.json()

    assert resp.status_code in (200, 201), resp.text
    assert body["code"] == 200
    assert body["data"]["plan_name"] == "信封校验预案"
    assert "plan_name" not in body, "裸字段又漏到顶层了"


@pytest.mark.asyncio
async def test_execute_requires_plan_id(client, db_session):
    """
    TC-LP-009: `/execute` 必须能拿到 plan_id——它此前用了一个 schema 里不存在的字段。

    不修会怎样：端点内部取 `data.plan_id`，而 `LinkageManualExecute` 只有
    alarm_id / is_simulation / remark，没有 plan_id。**每次调用都抛
    AttributeError → HTTP 500**，实测报错：
      {"code":500,"message":"服务器内部错误: 'LinkageManualExecute' object
       has no attribute 'plan_id'"}
    该端点因此从未可用；又因为前端 `executeManualLinkage` 没有任何视图调用，
    这个 100% 失败率一直没被发现。

    这里先钉住「不带 plan_id 时是 422 参数校验失败，而不是 500 内部错误」，
    把契约固定成 schema 层的显式约束。
    """
    user = await create_user_with_perms(
        db_session, "lp_exec_missing", ["linkage:view", "linkage:execute"]
    )

    resp = await client.post(
        f"{LIST_URL}/execute",
        json={"is_simulation": True},  # 故意不带 plan_id
        headers=auth_headers(user),
    )

    assert resp.status_code == 422, (
        f"缺 plan_id 应是 422 参数校验失败，实际 {resp.status_code}：{resp.text[:200]}"
    )


@pytest.mark.asyncio
async def test_execute_works_with_plan_id(client, db_session):
    """TC-LP-009: 带 plan_id 时能正常执行，不再 500"""
    user = await create_user_with_perms(
        db_session, "lp_exec_ok", ["linkage:view", "linkage:create", "linkage:execute"]
    )
    headers = auth_headers(user)

    created = await client.post(
        LIST_URL,
        json={
            "plan_name": "可执行预案",
            "org_id": 1,
            "fire_type": "fire",
            "actions": [{"action_type": "start_exhaust", "params": {}}],
        },
        headers=headers,
    )
    plan_id = created.json()["data"]["id"]

    resp = await client.post(
        f"{LIST_URL}/execute",
        json={"plan_id": plan_id, "is_simulation": True},
        headers=headers,
    )

    assert resp.status_code == 200, f"仍然失败：{resp.text[:300]}"
    assert resp.json()["data"]["message"].startswith("成功执行")


@pytest.mark.asyncio
async def test_execute_result_is_nested_not_flattened(client, db_session):
    """
    TC-LP-008: `/execute` 的返回体里也有一个 `message` 字段，必须收进 data。

    不修会怎样：端点原样返回裸 dict `{message: "成功执行 N 个动作", logs: [...]}`，
    与外层信封的 `message` 撞名。若简单地把该 dict 摊到信封顶层，
    「执行了几个动作」这条业务信息就会被信封的 "success" 覆盖掉——
    调用方永远读不到真实结果。
    """
    user = await create_user_with_perms(
        db_session, "lp_exec", ["linkage:view", "linkage:create", "linkage:execute"]
    )
    headers = auth_headers(user)

    created = await client.post(
        LIST_URL,
        json={
            "plan_name": "执行用预案",
            "org_id": 1,
            "fire_type": "fire",
            "actions": [{"action_type": "start_exhaust", "params": {}}],
        },
        headers=headers,
    )
    plan_id = created.json()["data"]["id"]

    resp = await client.post(
        f"{LIST_URL}/execute",
        json={"plan_id": plan_id, "is_simulation": True},
        headers=headers,
    )
    body = resp.json()

    assert resp.status_code == 200, resp.text
    assert body["message"] == "success"  # 信封自己的 message
    assert body["data"]["message"].startswith("成功执行")  # 业务 message 在 data 里
    assert isinstance(body["data"]["logs"], list)
