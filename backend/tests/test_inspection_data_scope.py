"""
巡检任务列表：默认时间窗 + 数据权限范围
========================================
对应 3.6 计划第 278 行「计划/任务按 org_id 过滤；维保人员默认只看责任人为自己的任务」。

两个已修复缺陷的守护：
1. 默认窗口上限截到今天 → /generate 产出的未来任务全部不可见（TC-SCOPE-001/002）
2. 列表完全没做 data_scope → self 用户能看到所有人的任务（TC-SCOPE-003~006）
"""
from datetime import date, timedelta

import pytest
import pytest_asyncio

from tests.inspection_helpers import (
    INSPECTION_VIEW_PERM,
    auth_headers,
    create_inspection_user,
    create_org,
    make_plan,
    make_task,
    task_ids,
)


@pytest_asyncio.fixture
async def scope_env(db_session):
    """两棵独立组织树 + 三类角色（all / dept / self）"""
    building = await create_org(db_session, "总部大楼")
    floor1 = await create_org(db_session, "1号楼", parent=building)
    other_building = await create_org(db_session, "外部大楼")

    chief = await create_inspection_user(
        db_session, "insp_chief", [INSPECTION_VIEW_PERM], data_scope="all"
    )
    dept_user = await create_inspection_user(
        db_session, "insp_dept", [INSPECTION_VIEW_PERM], data_scope="dept", org=floor1
    )
    self_user = await create_inspection_user(
        db_session, "insp_self", [INSPECTION_VIEW_PERM], data_scope="self"
    )
    other_user = await create_inspection_user(
        db_session, "insp_other", [INSPECTION_VIEW_PERM], data_scope="all"
    )

    # 楼内计划（责任人=self_user）与外部楼计划（责任人=other_user）。
    # inner_plan 挂在 floor1——dept 用户也挂 floor1，范围口径是「本部门及子部门」
    # （与 P1-007 对 devices 的 `apply_data_scope` 一致），挂到父节点 building
    # 反而不该可见。
    inner_plan = await make_plan(
        db_session,
        plan_name="楼内计划",
        org_id=floor1.id,
        responsible_user_id=self_user.id,
    )
    outer_plan = await make_plan(
        db_session,
        plan_name="外部计划",
        org_id=other_building.id,
        responsible_user_id=other_user.id,
    )

    today = date.today()
    inner_task = await make_task(
        db_session, plan_id=inner_plan.id, responsible_user_id=self_user.id, task_date=today
    )
    outer_task = await make_task(
        db_session, plan_id=outer_plan.id, responsible_user_id=other_user.id, task_date=today
    )

    return {
        "building": building,
        "floor1": floor1,
        "other_building": other_building,
        "chief": chief,
        "dept_user": dept_user,
        "self_user": self_user,
        "other_user": other_user,
        "inner_plan": inner_plan,
        "outer_plan": outer_plan,
        "inner_task": inner_task,
        "outer_task": outer_task,
    }


# ==================== 默认时间窗 ====================

@pytest.mark.asyncio
async def test_default_window_includes_future_tasks(client, db_session, scope_env):
    """
    TC-SCOPE-001: 不传日期时，未来日期的任务必须可见。

    不修会怎样：默认窗口是 [本月1日, 今天]，而 /generate 产出的是
    [今天, 今天+N)——线上实测「生成 7 天、库里 7 条、列表只回 1 条」，
    用户点完「生成任务」看到列表几乎空着。
    """
    today = date.today()
    future_task = await make_task(
        db_session,
        plan_id=scope_env["inner_plan"].id,
        responsible_user_id=scope_env["self_user"].id,
        task_date=today + timedelta(days=5),
    )

    resp = await client.get(
        "/api/v1/inspection-tasks", headers=auth_headers(scope_env["chief"])
    )
    assert resp.status_code == 200, resp.text
    assert future_task.id in task_ids(resp.json()), "未来任务被默认窗口截掉了"


@pytest.mark.asyncio
async def test_explicit_end_date_still_narrows(client, db_session, scope_env):
    """
    TC-SCOPE-002: 显式传 end_date 时仍然收窄（去掉的是隐式上限，不是这个筛选能力）。
    """
    today = date.today()
    future_task = await make_task(
        db_session,
        plan_id=scope_env["inner_plan"].id,
        responsible_user_id=scope_env["self_user"].id,
        task_date=today + timedelta(days=5),
    )

    resp = await client.get(
        "/api/v1/inspection-tasks",
        params={"end_date": today.isoformat()},
        headers=auth_headers(scope_env["chief"]),
    )
    assert future_task.id not in task_ids(resp.json())


# ==================== 数据权限范围 ====================

@pytest.mark.asyncio
async def test_all_scope_sees_every_task(client, scope_env):
    """TC-SCOPE-003: data_scope=all 不受限，两棵树的计划都能看到。"""
    resp = await client.get(
        "/api/v1/inspection-tasks", headers=auth_headers(scope_env["chief"])
    )
    ids = task_ids(resp.json())
    assert ids == {scope_env["inner_task"].id, scope_env["outer_task"].id}


@pytest.mark.asyncio
async def test_self_scope_sees_only_own_tasks(client, scope_env):
    """
    TC-SCOPE-004: data_scope=self 只看责任人是自己的任务。

    不修会怎样：列表此前完全不读 data_scope，维保人员能看到全公司所有人的任务。
    注意锚点是 `responsible_user_id` 而不是 `created_by`——任务是管理员生成/定时生成的，
    按 created_by 过滤会让维保人员一条都看不到。
    """
    resp = await client.get(
        "/api/v1/inspection-tasks", headers=auth_headers(scope_env["self_user"])
    )
    ids = task_ids(resp.json())
    assert ids == {scope_env["inner_task"].id}
    assert scope_env["outer_task"].id not in ids


@pytest.mark.asyncio
async def test_dept_scope_sees_subtree_only(client, scope_env):
    """
    TC-SCOPE-005: data_scope=dept 只看本部门及子部门下的任务。

    任务表没有 org_id，范围要经 plan.org_id 折算；dept 用户挂在「1号楼」，
    能看到同属 1号楼的计划，看不到外部大楼的。
    口径是「本部门及**子**部门」——挂在父节点 building 的计划不可见（同 P1-007）。
    """
    resp = await client.get(
        "/api/v1/inspection-tasks", headers=auth_headers(scope_env["dept_user"])
    )
    ids = task_ids(resp.json())
    assert ids == {scope_env["inner_task"].id}
    assert scope_env["outer_task"].id not in ids


@pytest.mark.asyncio
async def test_scope_applies_to_total_not_just_items(client, scope_env):
    """
    TC-SCOPE-006: total 与 items 口径一致。

    不修会怎样：若只过滤 items 而 count 用未过滤的 stmt，
    分页会出现「总数 2、只回 1 条」，翻到第二页是空的。
    """
    resp = await client.get(
        "/api/v1/inspection-tasks", headers=auth_headers(scope_env["self_user"])
    )
    body = resp.json()
    assert body["data"]["total"] == len(body["data"]["items"]) == 1
