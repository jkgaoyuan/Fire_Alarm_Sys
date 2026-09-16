"""
消防演练参与人员 —— HTTP 层用例
================================
为什么新建这个文件：`tests/test_drill_crud.py` 只在 **CRUD 层**覆盖参与人员
（`TestParticipantManagement`），而 `POST /drills` 与
`POST /drills/{id}/participants` 的**参数解析零覆盖** —— 这正是它们的
body/query 实际形状无测试保障、改签名不会亮红灯的原因。

覆盖：
1. 候选人端点（`drill:execute` 守卫，**刻意不是** `system:user`）
2. 角色经 `POST /drills` 真正落库并可回读 —— 此前被后端硬编码成「参与者」丢弃
3. participants 响应带 `user_name`（响应期补充，不落库）
4. 旧 `participant_user_ids` 字段仍兼容
"""

import pytest

from tests.auth_helpers import auth_headers, create_user_with_perms


# ==================== 夹具 ====================

@pytest.fixture
async def drill_actor(db_session):
    """持有演练全套权限的操作者（主管等价物）

    注意要带 `drill:update` —— `PUT /drills/{id}` 由它守卫，缺了会 403。
    """
    return await create_user_with_perms(
        db_session,
        "drill_boss",
        ["drill:create", "drill:view", "drill:update", "drill:execute"],
    )


@pytest.fixture
async def two_members(db_session):
    """两名参与人员，real_name 刻意与 username 不同，便于验证姓名补充"""
    a = await create_user_with_perms(db_session, "member_a")
    b = await create_user_with_perms(db_session, "member_b")
    a.real_name = "张三"
    b.real_name = "李四"
    await db_session.commit()
    return a, b


# ==================== 候选人端点 ====================

@pytest.mark.asyncio
async def test_candidates_require_drill_execute_not_system_user(client, db_session):
    """
    TC-DRILL-001 候选人端点由 `drill:execute` 守卫 —— 不是 `system:user`。

    这正是新建该端点的全部理由：值班员/维保员持有 `drill:execute` 却**没有**
    `system:user`，沿用 `GET /users` 会让「执行演练时加人」对他们整个不可用。
    """
    # 只有 drill:view 的人 —— 应当被拒
    viewer = await create_user_with_perms(db_session, "only_viewer", ["drill:view"])
    resp = await client.get(
        "/api/v1/drills/participant-candidates", headers=auth_headers(viewer)
    )
    assert resp.status_code == 403

    # 有 drill:execute 的人 —— 应当通过（且**不**需要 system:user）
    executor = await create_user_with_perms(db_session, "exec_only", ["drill:execute"])
    resp = await client.get(
        "/api/v1/drills/participant-candidates", headers=auth_headers(executor)
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_candidates_return_lean_fields(client, db_session, two_members):
    """
    TC-DRILL-002 候选人只返回精简字段，**不得**回退成 `UserOut`。

    `UserOut` 含 phone / email / data_scope / status / created_at ——
    这个端点由 drill 域权限守卫，值班员与维保员都持有，没必要把联系方式给他们。
    """
    a, b = two_members
    resp = await client.get(
        "/api/v1/drills/participant-candidates", headers=auth_headers(a)
    )
    assert resp.status_code == 403  # 普通用户无 drill 权限，先确认门禁有效

    boss = await create_user_with_perms(db_session, "lean_checker", ["drill:execute"])
    resp = await client.get(
        "/api/v1/drills/participant-candidates", headers=auth_headers(boss)
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    assert items, "候选人列表不应为空"

    # 键集必须精确 —— 多出 phone/email 即说明退回用了 UserOut
    assert set(items[0].keys()) == {"id", "username", "real_name", "role_names"}

    names = {i["real_name"] for i in items}
    assert {"张三", "李四"} <= names


@pytest.mark.asyncio
async def test_candidates_exclude_disabled_users(client, db_session):
    """
    TC-DRILL-003 停用用户不得出现在候选人里。

    变异：去掉 `.where(User.status == "active")` → 本用例必红。
    """
    boss = await create_user_with_perms(db_session, "active_filter", ["drill:execute"])
    gone = await create_user_with_perms(db_session, "disabled_one")
    gone.status = "disabled"
    await db_session.commit()

    resp = await client.get(
        "/api/v1/drills/participant-candidates", headers=auth_headers(boss)
    )
    assert resp.status_code == 200, resp.text
    usernames = {i["username"] for i in resp.json()["data"]}
    assert "disabled_one" not in usernames


# ==================== 角色补通（核心缺陷） ====================

@pytest.mark.asyncio
async def test_create_drill_persists_participant_roles(client, drill_actor, two_members):
    """
    TC-DRILL-004 经 `POST /drills` 提交的角色必须**真正落库**并能回读。

    这是本次修的核心缺陷：前端界面上一直收集角色，但提交时只发
    `participant_user_ids`，后端 `create` 又把所有人写死 `"role": "参与者"`，
    **填了角色会被无声丢弃**。

    变异：把 `_normalize_participants` 里的 `p.get("role")` 改回常量
    `"参与者"` → 本用例必红。
    """
    a, b = two_members
    resp = await client.post(
        "/api/v1/drills",
        headers=auth_headers(drill_actor),
        json={
            "drill_name": "角色落库验证",
            "drill_type": "evacuation",
            "participants": [
                {"user_id": a.id, "role": "指挥员"},
                {"user_id": b.id, "role": "疏散员"},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    drill_id = resp.json()["data"]["id"]

    # 回读
    detail = await client.get(
        f"/api/v1/drills/{drill_id}", headers=auth_headers(drill_actor)
    )
    assert detail.status_code == 200, detail.text
    roles = {p["user_id"]: p["role"] for p in detail.json()["data"]["participants"]}
    assert roles == {a.id: "指挥员", b.id: "疏散员"}


@pytest.mark.asyncio
async def test_update_drill_persists_participant_roles(client, drill_actor, two_members):
    """
    TC-DRILL-005 经 `PUT /drills/{id}` 改角色也必须落库。

    变异：`update` 里不处理 `participants_input`（只留旧 `participant_user_ids`
    分支）→ 本用例必红。
    """
    a, b = two_members
    created = await client.post(
        "/api/v1/drills",
        headers=auth_headers(drill_actor),
        json={
            "drill_name": "改角色验证",
            "drill_type": "firefighting",
            "participants": [{"user_id": a.id, "role": "指挥员"}],
        },
    )
    drill_id = created.json()["data"]["id"]

    resp = await client.put(
        f"/api/v1/drills/{drill_id}",
        headers=auth_headers(drill_actor),
        json={"participants": [{"user_id": b.id, "role": "操作员"}]},
    )
    assert resp.status_code == 200, resp.text

    detail = await client.get(
        f"/api/v1/drills/{drill_id}", headers=auth_headers(drill_actor)
    )
    parts = detail.json()["data"]["participants"]
    assert len(parts) == 1
    assert parts[0]["user_id"] == b.id
    assert parts[0]["role"] == "操作员"


@pytest.mark.asyncio
async def test_role_defaults_to_participant_when_omitted(client, drill_actor, two_members):
    """
    TC-DRILL-006 `participants` 里省掉 role 时回落到「参与者」，不得变成 None。
    """
    a, _ = two_members
    resp = await client.post(
        "/api/v1/drills",
        headers=auth_headers(drill_actor),
        json={
            "drill_name": "缺省角色",
            "drill_type": "comprehensive",
            "participants": [{"user_id": a.id}],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["participants"][0]["role"] == "参与者"


@pytest.mark.asyncio
async def test_legacy_participant_user_ids_still_works(client, drill_actor, two_members):
    """
    TC-DRILL-007 旧字段 `participant_user_ids` 仍兼容（等价于全部「参与者」）。

    变异：删掉 `_normalize_participants` 里的 `participant_user_ids` 分支
    → 参与者会变成空列表，本用例必红。
    """
    a, b = two_members
    resp = await client.post(
        "/api/v1/drills",
        headers=auth_headers(drill_actor),
        json={
            "drill_name": "旧字段兼容",
            "drill_type": "evacuation",
            "participant_user_ids": [a.id, b.id],
        },
    )
    assert resp.status_code == 200, resp.text
    parts = resp.json()["data"]["participants"]
    assert {p["user_id"] for p in parts} == {a.id, b.id}
    assert all(p["role"] == "参与者" for p in parts)


# ==================== 姓名补充 ====================

@pytest.mark.asyncio
async def test_participants_include_user_name(client, drill_actor, two_members):
    """
    TC-DRILL-008 participants 响应必须带 `user_name`（响应期补充，不落库）。

    变异：把 `_participants_out` 的 `user_name=` 去掉 → 本用例必红。
    """
    a, b = two_members
    created = await client.post(
        "/api/v1/drills",
        headers=auth_headers(drill_actor),
        json={
            "drill_name": "姓名补充",
            "drill_type": "evacuation",
            "participants": [{"user_id": a.id, "role": "指挥员"}],
        },
    )
    drill_id = created.json()["data"]["id"]

    detail = await client.get(
        f"/api/v1/drills/{drill_id}", headers=auth_headers(drill_actor)
    )
    part = detail.json()["data"]["participants"][0]
    assert part["user_name"] == "张三"

    # 注意：详情响应由 _participants_out 现查姓名；JSONB 里**不含** user_name
    # 这件事由 TC-DRILL-009 直接在存储层断言。


@pytest.mark.asyncio
async def test_stored_participants_do_not_contain_user_name(db_session, drill_actor, two_members):
    """
    TC-DRILL-009 存储形状必须保持 PRD 的 `{user_id, role, sign_in_at}` —— 姓名不落库。

    姓名落库会随用户改名而过期，且把「展示」混进「存储」。
    """
    from app.crud.drill_crud import drill_crud
    from app.models.drill import DrillType

    a, _ = two_members
    drill = await drill_crud.create(
        db_session,
        drill_name="不落库验证",
        drill_type=DrillType.evacuation,
        created_by=drill_actor.id,
        participants_input=[{"user_id": a.id, "role": "指挥员"}],
    )
    assert drill.participants == [
        {"user_id": a.id, "role": "指挥员", "sign_in_at": None}
    ]


@pytest.mark.asyncio
async def test_missing_user_yields_none_name_not_500(client, drill_actor):
    """
    TC-DRILL-010 参与人对应的用户已被删除时，详情端点不得 500。

    存储里的 user_id 可能指向已删除用户 —— 补充姓名的那次查询会查不到，
    此时 `user_name` 留 None，由前端回退显示 `#<id>`。
    """
    created = await client.post(
        "/api/v1/drills",
        headers=auth_headers(drill_actor),
        json={
            "drill_name": "用户已删除",
            "drill_type": "evacuation",
            "participant_user_ids": [999999],  # 不存在的用户
        },
    )
    assert created.status_code == 200, created.text
    drill_id = created.json()["data"]["id"]

    detail = await client.get(
        f"/api/v1/drills/{drill_id}", headers=auth_headers(drill_actor)
    )
    assert detail.status_code == 200, detail.text
    part = detail.json()["data"]["participants"][0]
    assert part["user_id"] == 999999
    assert part["user_name"] is None
