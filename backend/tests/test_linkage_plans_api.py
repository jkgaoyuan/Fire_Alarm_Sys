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

from app.models.organization import Organization
from app.services import event_stream
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


# ==================== 关联区域名（org_name） ====================

async def _org(db_session, name="1F 大厅"):
    """建一个真实区域，用于断言响应里带出的是它的名字"""
    org = Organization(org_name=name, org_type="zone")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


async def _org_user(db_session, name="lp_orgname"):
    return await create_user_with_perms(
        db_session,
        name,
        ["linkage:view", "linkage:create", "linkage:update"],
    )


@pytest.mark.asyncio
async def test_list_returns_org_name(client, db_session):
    """
    TC-LP-010: 预案列表必须带出关联区域名。

    不修会怎样：`LinkagePlanOut` 只有 `org_id`，而前端 `Plan.vue:50` 读的是
    `row.organization?.org_name` —— 字段对不上，取到 undefined 被 `|| '-'`
    兜底，**「关联区域」列恒为 `-` 且不报错**。用户配置了也看不见。
    """
    org = await _org(db_session)
    user = await _org_user(db_session)
    headers = auth_headers(user)

    await client.post(
        LIST_URL,
        json={"plan_name": "带区域预案", "org_id": org.id, "actions": []},
        headers=headers,
    )

    resp = await client.get(LIST_URL, headers=headers)
    item = resp.json()["data"]["items"][0]

    assert item["org_id"] == org.id
    assert item["org_name"] == "1F 大厅", f"区域名没带出来：{item}"


@pytest.mark.asyncio
async def test_detail_returns_org_name(client, db_session):
    """TC-LP-011: 详情（抽屉里那行）同样要带区域名"""
    org = await _org(db_session, "2F 走廊")
    user = await _org_user(db_session, "lp_orgname2")
    headers = auth_headers(user)

    created = await client.post(
        LIST_URL,
        json={"plan_name": "详情预案", "org_id": org.id, "actions": []},
        headers=headers,
    )
    plan_id = created.json()["data"]["id"]

    resp = await client.get(f"{LIST_URL}/{plan_id}", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["org_name"] == "2F 走廊"


@pytest.mark.asyncio
async def test_create_returns_org_name_immediately(client, db_session):
    """
    TC-LP-012: 创建/更新/切换状态三个端点也返回 `LinkagePlanOut`，
    提交后前端拿它刷新行；若只有查询端点带 org_name，保存后那一行会闪回 `-`。

    不修会怎样：新建后 `db.refresh(plan)` 只刷新了列，`organization` 关系未加载，
    org_name 取不到。
    """
    org = await _org(db_session, "3F 机房")
    user = await _org_user(db_session, "lp_orgname3")
    headers = auth_headers(user)

    created = await client.post(
        LIST_URL,
        json={"plan_name": "创建预案", "org_id": org.id, "actions": []},
        headers=headers,
    )
    plan_id = created.json()["data"]["id"]
    assert created.json()["data"]["org_name"] == "3F 机房"

    updated = await client.put(
        f"{LIST_URL}/{plan_id}",
        json={"plan_name": "改过名"},
        headers=headers,
    )
    assert updated.json()["data"]["org_name"] == "3F 机房"

    toggled = await client.post(
        f"{LIST_URL}/{plan_id}/toggle",
        json={"is_enabled": False},
        headers=headers,
    )
    assert toggled.json()["data"]["org_name"] == "3F 机房"


@pytest.mark.asyncio
async def test_org_name_is_null_when_org_missing(client, db_session):
    """
    TC-LP-013: 区域被删/查不到时 org_name 为 null，而不是 500。

    SQLite 测试库不校验外键，可以直接写入悬空的 org_id——生产库删组织时
    也可能留下引用，端点不能因此炸掉。
    """
    user = await _org_user(db_session, "lp_orgname4")
    headers = auth_headers(user)

    await client.post(
        LIST_URL,
        json={"plan_name": "悬空区域预案", "org_id": 987654, "actions": []},
        headers=headers,
    )

    resp = await client.get(LIST_URL, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["items"][0]["org_name"] is None


# ==================== 模拟测试（走全链路） ====================
#
# 旧实现直接拿预案的 actions 循环执行，绕开 `_matches_alarm`，所以
# 「这条预案会不会被触发」这个问题它答不了；且不建告警、不广播。
# 现在改为生成演练告警交给引擎，下面钉住新的行为契约。

SIM_PERMS = [
    "linkage:view",
    "linkage:create",
    "linkage:update",
    "linkage:simulate",
    "alarm:view",  # TC-LP-015 要从报警中心确认演练告警的可见性
]

ALARM_TYPE = "fire"  # execute_action 会随机失败，统一打桩成确定结果
ENGINE = "app.services.linkage_engine_service"


def _stub_execute(monkeypatch, status="success", message="排烟风机已启动"):
    async def fake(action, log, failure_rate=0.1):
        return status, message

    monkeypatch.setattr(f"{ENGINE}.execute_action", fake)


async def _sim_env(client, db_session, name, *, with_device=True, plan_body=None):
    """
    建区域（+设备）+ 预案 + 授权用户，返回 (headers, plan_id, org, device)。

    `with_device=False` 用于构造「本区域没有设备」这个分支。
    """
    from tests.device_helpers import make_device

    org = await _org(db_session, f"模拟区-{name}")
    device = await make_device(db_session, org_id=org.id) if with_device else None

    user = await create_user_with_perms(db_session, name, SIM_PERMS)
    headers = auth_headers(user)

    body = {
        "plan_name": f"模拟预案-{name}",
        "org_id": org.id,
        "actions": [{"action_type": "start_exhaust", "params": {}}],
    }
    body.update(plan_body or {})

    resp = await client.post(LIST_URL, json=body, headers=headers)
    assert resp.status_code in (200, 201), resp.text
    return headers, resp.json()["data"]["id"], org, device


@pytest.mark.asyncio
async def test_simulate_creates_drill_alarm_through_engine(client, db_session, monkeypatch):
    """
    TC-LP-014: 模拟测试生成演练告警，并按真实规则跑通引擎。

    旧实现不建告警、不匹配、不广播，只把预案的动作跑一遍就报成功——
    连 `org_id` 配错都发现不了。新实现必须满足：
    产出一条 `is_drill=True` 的告警、`included_self` 为真、日志状态是成功。
    """
    _stub_execute(monkeypatch)
    headers, plan_id, _org_obj, device = await _sim_env(client, db_session, "basic")

    resp = await client.post(f"{LIST_URL}/{plan_id}/simulate", headers=headers)
    body = resp.json()

    assert resp.status_code == 200, resp.text
    data = body["data"]
    assert data["is_drill"] is True
    assert data["alarm_type"] == "fire"
    assert data["device_id"] == device.id
    assert data["included_self"] is True, (
        f"模拟了这条预案本身，它却没在命中列表里：{data['matched_plan_ids']}"
    )
    assert plan_id in data["matched_plan_ids"]
    assert len(data["logs"]) == 1
    assert data["logs"][0]["status"] == "success", (
        f"动作成功却被记成 {data['logs'][0]['status']}：{data['logs'][0]['result_message']}"
    )


@pytest.mark.asyncio
async def test_simulate_alarm_is_visible_as_drill(client, db_session, monkeypatch):
    """
    TC-LP-015: 演练告警确实落到了 alarms 表，且按既有约定只在「含演练」时可见。

    进统计与应急升级由既有代码保证（`statistics_service` / `emergency_service`
    都过滤 `is_drill`），这里只钉住「报警中心按约定隐藏 / 开筛选可见」，
    以及它带着 `is_drill` 标记，前端据此显示「演练」标签。
    """
    _stub_execute(monkeypatch)
    headers, plan_id, _org_obj, _device = await _sim_env(client, db_session, "visible")

    sim = await client.post(f"{LIST_URL}/{plan_id}/simulate", headers=headers)
    alarm_id = sim.json()["data"]["alarm_id"]

    hidden = await client.get("/api/v1/alarms", headers=headers)
    assert alarm_id not in [a["id"] for a in hidden.json()["data"]["items"]], (
        "演练告警不该出现在默认的报警列表里"
    )

    shown = await client.get("/api/v1/alarms?include_drill=true", headers=headers)
    item = next(a for a in shown.json()["data"]["items"] if a["id"] == alarm_id)
    assert item["is_drill"] is True


@pytest.mark.asyncio
async def test_simulate_broadcasts_alarm_new_frame(
    client, db_session, fake_redis, monkeypatch
):
    """
    TC-LP-020: 演练告警必须广播 `alarm_new`，否则报警中心开着也看不见它。

    报警中心（`Center.vue`）把 WS 帧与 REST 结果合并，再按「含演练」开关决定显隐；
    `alarm_payload` 带 `is_drill`（`alarm_service.py:99`）正是为了让消费端能过滤。
    不广播的后果是：**唯一被设计成能看演练告警的界面，反而要靠手动刷新**。
    真实上报路径（`device_report_service.py:144`）与联动引擎次级告警都广播，
    只有模拟端点漏了——af3a8e88 的提交信息把「不广播」列为要修的毛病，
    重写时补了告警与联动，却漏了这一截。

    演练不改设备状态，所以这里**只该有一条帧**：多出 `device_status`
    说明有代码顺手翻了 `devices.status`（那会把演练混进设备真实状态）。
    """
    _stub_execute(monkeypatch)
    headers, plan_id, _org_obj, _device = await _sim_env(client, db_session, "broadcast")

    resp = await client.post(f"{LIST_URL}/{plan_id}/simulate", headers=headers)
    assert resp.status_code == 200, resp.text

    frames = await event_stream.read_after(fake_redis, "0-1", 100)
    assert [f["type"] for f in frames] == ["alarm_new"], (
        f"期望恰好一条 alarm_new，实际 {[f['type'] for f in frames]}"
    )
    assert frames[0]["data"]["alarm_id"] == resp.json()["data"]["alarm_id"]
    assert frames[0]["data"]["is_drill"] is True


@pytest.mark.asyncio
async def test_simulate_repeat_does_not_rebroadcast(
    client, db_session, fake_redis, monkeypatch
):
    """
    TC-LP-021: 重复点模拟复用既有演练告警，不再重复广播。

    与上报路径同口径（`device_report_service.py:144` 只在 `alarm_created` 时广播）：
    第二次模拟走的是 `raise_alarm` 的去重分支，没有新告警产生，
    再广播一次会让报警中心把同一条演练告警当成新的推送两遍。
    """
    _stub_execute(monkeypatch)
    headers, plan_id, _org_obj, _device = await _sim_env(client, db_session, "rebroadcast")

    first = await client.post(f"{LIST_URL}/{plan_id}/simulate", headers=headers)
    second = await client.post(f"{LIST_URL}/{plan_id}/simulate", headers=headers)
    assert (
        first.json()["data"]["alarm_id"] == second.json()["data"]["alarm_id"]
    ), "第二次模拟应当复用同一条演练告警"

    frames = await event_stream.read_after(fake_redis, "0-1", 100)
    assert [f["type"] for f in frames] == ["alarm_new"], (
        f"幂等复用不该再广播，实际 {[f['type'] for f in frames]}"
    )


@pytest.mark.asyncio
async def test_simulate_rejected_when_plan_disabled(client, db_session, monkeypatch):
    """TC-LP-016: 预案关了「允许模拟测试」时，点它自己的模拟按钮要被明确拒绝"""
    _stub_execute(monkeypatch)
    headers, plan_id, _org_obj, _device = await _sim_env(client, db_session, "disabled")

    await client.put(
        f"{LIST_URL}/{plan_id}", json={"is_simulation_allowed": False}, headers=headers
    )

    resp = await client.post(f"{LIST_URL}/{plan_id}/simulate", headers=headers)

    assert resp.status_code == 400
    assert "模拟测试" in resp.json()["message"]


@pytest.mark.asyncio
async def test_simulation_switch_persists(client, db_session):
    """
    TC-LP-017: 「允许模拟测试」开关必须能存能读。

    该字段此前既不在 ORM 模型也不在 schema 里 —— 前端开关提交后被 Pydantic
    静默丢弃，列表也从不返回它，开关从落地起就是死的。
    """
    headers, plan_id, _org_obj, _device = await _sim_env(client, db_session, "persist")

    listed = await client.get(LIST_URL, headers=headers)
    item = next(p for p in listed.json()["data"]["items"] if p["id"] == plan_id)
    assert item["is_simulation_allowed"] is True, "默认应为允许"

    await client.put(
        f"{LIST_URL}/{plan_id}", json={"is_simulation_allowed": False}, headers=headers
    )

    listed = await client.get(LIST_URL, headers=headers)
    item = next(p for p in listed.json()["data"]["items"] if p["id"] == plan_id)
    assert item["is_simulation_allowed"] is False, "关掉后必须读得回来"


@pytest.mark.asyncio
async def test_simulate_rejected_without_device_in_org(client, db_session, monkeypatch):
    """
    TC-LP-018: 区域内没有设备时明确报错，而不是静默什么都不发生。

    演练告警必须挂在真实设备上（`raise_alarm` 的 device 必填，且 org_id 从它
    快照），而预案匹配比的正是 `alarm.org_id == plan.org_id`。
    """
    _stub_execute(monkeypatch)
    headers, plan_id, _org_obj, _device = await _sim_env(
        client, db_session, "nodevice", with_device=False
    )

    resp = await client.post(f"{LIST_URL}/{plan_id}/simulate", headers=headers)

    assert resp.status_code == 400
    assert "设备" in resp.json()["message"]


@pytest.mark.asyncio
async def test_simulate_refuses_to_reuse_real_alarm(client, db_session, monkeypatch):
    """
    TC-LP-019: 设备上已有未处理的真实告警时，必须 409 而不是拿它当演练跑。

    `raise_alarm` 按 (device_id, alarm_type, 未收敛状态) 去重，**不看 is_drill**。
    若不显式处理这个分支，模拟会复用那条真实火警，等于对着真火警做演练。
    """
    from app.services.alarm_service import raise_alarm

    _stub_execute(monkeypatch)
    headers, plan_id, _org_obj, device = await _sim_env(client, db_session, "realalarm")

    real, created = await raise_alarm(db_session, device, ALARM_TYPE)
    await db_session.commit()
    assert created

    resp = await client.post(f"{LIST_URL}/{plan_id}/simulate", headers=headers)

    assert resp.status_code == 409, resp.text
    assert str(real.id) in resp.json()["message"]


@pytest.mark.asyncio
async def test_simulate_is_idempotent_on_repeat(client, db_session, monkeypatch):
    """TC-LP-020: 重复点击复用同一演练告警，不会堆出一串告警行"""
    _stub_execute(monkeypatch)
    headers, plan_id, _org_obj, _device = await _sim_env(client, db_session, "repeat")

    first = await client.post(f"{LIST_URL}/{plan_id}/simulate", headers=headers)
    second = await client.post(f"{LIST_URL}/{plan_id}/simulate", headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["alarm_id"] == second.json()["data"]["alarm_id"]
    # 第二轮只回报本次新产生的日志，不复述上一轮的
    assert len(second.json()["data"]["logs"]) == 1


@pytest.mark.asyncio
async def test_simulate_rejects_unmatchable_trigger_type(client, db_session, monkeypatch):
    """
    TC-LP-021: 触发类型为 fault/shield 的预案，模拟时明确报错。

    引擎入口只对 fire/pre_fire 启动（`linkage_engine_service.py`），但表单的
    「触发报警类型」允许选「故障」「屏蔽」——这类预案是死配置，永远不会被触发。
    旧实现会开开心心地跑一遍动作并报成功，用户根本发现不了。
    """
    _stub_execute(monkeypatch)
    headers, plan_id, _org_obj, _device = await _sim_env(
        client, db_session, "faulttype", plan_body={"trigger_alarm_type": "fault"}
    )

    resp = await client.post(f"{LIST_URL}/{plan_id}/simulate", headers=headers)

    assert resp.status_code == 400
    assert "fault" in resp.json()["message"]


@pytest.mark.asyncio
async def test_simulate_rejects_contradictory_trigger_config(client, db_session, monkeypatch):
    """
    TC-LP-022: 「火灾类型」与「触发报警类型」互相矛盾时明确报错。

    匹配要求两者**同时**等于 alarm_type，所以 fire_type=fire +
    trigger_alarm_type=pre_fire 这类配置没有任何报警能同时满足。
    """
    _stub_execute(monkeypatch)
    headers, plan_id, _org_obj, _device = await _sim_env(
        client,
        db_session,
        "contradict",
        plan_body={"fire_type": "fire", "trigger_alarm_type": "pre_fire"},
    )

    resp = await client.post(f"{LIST_URL}/{plan_id}/simulate", headers=headers)

    assert resp.status_code == 400
    assert "不一致" in resp.json()["message"]
