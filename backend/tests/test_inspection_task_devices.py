"""
巡检任务的「应检设备」（执行巡检设备选择器）
============================================

2026-09-14 实测缺陷：**维保员登录后点「执行巡检」看不到任何设备，无法提交巡检**。

**根因**：执行巡检弹窗直接调 `GET /devices`，而该端点套通用 `apply_data_scope`，
`data_scope='self'` 锚的是 `devices.created_by` —— **设备的录入人**。
设备通常由管理员录入，于是维保员拿到的永远是空表：

    admin    → GET /devices → total 2
    maint01  → GET /devices → total 0   ← code 200 / message success，不报错

界面上只是一张空表格，没有任何提示。

这与 `apply_task_data_scope` 要解决的是**同一类问题**——那个函数开头就写了
「刻意不复用 `user_service.apply_data_scope`，因为任务的归属是 `responsible_user_id`，
不是 `created_by`」。设备域漏了这一步，本文件钉住修正后的口径。

顺带修掉的范围错误：原先能挑到**该计划范围之外**的设备来填报——
任务只覆盖某区域某类设备，记录却可以落在任意设备上。
"""
import pytest
import pytest_asyncio

from tests.auth_helpers import auth_headers
from tests.device_helpers import create_device_type, make_device
from tests.inspection_helpers import (
    create_inspection_user,
    create_org,
    make_plan,
    make_task,
)

TASKS_URL = "/api/v1/inspection-tasks"


def devices_url(task_id: int) -> str:
    return f"/api/v1/inspection-tasks/{task_id}/devices"


def ids_of(body: dict) -> set[int]:
    return {item["id"] for item in body["data"]["items"]}


@pytest_asyncio.fixture
async def dev_env(db_session):
    """
    一栋楼 + 一个楼层（+ 另一栋楼），两个设备类型，四种角色。

    组织：楼 A(id=a) └─ 楼层 A1；楼 B（在范围之外）
    """
    building_a = await create_org(db_session, "楼A")
    floor_a1 = await create_org(db_session, "楼A-1层", parent=building_a)
    building_b = await create_org(db_session, "楼B")

    smoke = await create_device_type(db_session, "smoke_detector", "烟感探测器")
    heat = await create_device_type(db_session, "heat_detector", "温感探测器")

    # 计划覆盖「楼A（含子区域）+ 烟感」，责任人 = 维保员
    maintainer = await create_inspection_user(
        db_session,
        "dev_maint",
        ["inspection:view", "inspection:execute"],
        data_scope="self",  # ⚠️ 正是出事的那种范围
        org=building_a,
    )
    plan = await make_plan(
        db_session,
        plan_name="楼A烟感每日巡检",
        org_id=building_a.id,
        device_type_id=smoke.id,
        responsible_user_id=maintainer.id,
    )
    task = await make_task(db_session, plan_id=plan.id, responsible_user_id=maintainer.id)

    # 范围内的设备：楼A 自身、楼A的子楼层（子区域必须一并覆盖）
    in_scope = await make_device(
        db_session, org_id=building_a.id, device_name="楼A烟感", type_id=smoke.id
    )
    in_scope_child = await make_device(
        db_session, org_id=floor_a1.id, device_name="楼层烟感", type_id=smoke.id
    )
    # 范围外的设备：别的楼 / 别的类型 / 已退役 / 已删除
    other_org = await make_device(
        db_session, org_id=building_b.id, device_name="楼B烟感", type_id=smoke.id
    )
    other_type = await make_device(
        db_session, org_id=building_a.id, device_name="楼A温感", type_id=heat.id
    )
    retired = await make_device(
        db_session,
        org_id=building_a.id,
        device_name="楼A烟感-退役",
        type_id=smoke.id,
        status="retired",
    )
    removed = await make_device(
        db_session, org_id=building_a.id, device_name="楼A烟感-已删", type_id=smoke.id
    )
    removed.is_deleted = True
    await db_session.commit()

    return locals()


@pytest.mark.asyncio
async def test_maintainer_with_self_scope_can_see_required_devices(client, db_session, dev_env):
    """
    TC-INS-DEV-001: **维保员（data_scope=self）必须能看到应检设备**。

    这条就是本次故障的守护用例：不修的话 `GET /devices` 返回 total=0，
    维保员点「执行巡检」只能看到一张空表格，任务永远提交不出去。
    """
    e = dev_env
    resp = await client.get(
        devices_url(e["task"].id), headers=auth_headers(e["maintainer"])
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    got = ids_of(body)
    assert got, "维保员仍然看不到任何应检设备（本次缺陷未修复）"
    assert e["in_scope"].id in got
    # 子区域必须一并覆盖：计划挂在「楼A」，设备在「楼A-1层」
    assert e["in_scope_child"].id in got, "计划组织的子区域设备被漏掉了"
    assert body["data"]["total"] == 2


@pytest.mark.asyncio
async def test_excludes_devices_outside_plan_scope(client, db_session, dev_env):
    """
    TC-INS-DEV-002: 范围外的设备不得出现。

    别的区域、别的类型、已退役、已逻辑删除，四类都要挡住——
    原先直接调 `/devices` 时**这四类全都能被挑到**，记录会落在不该检的设备上。
    """
    e = dev_env
    resp = await client.get(
        devices_url(e["task"].id), headers=auth_headers(e["maintainer"])
    )
    got = ids_of(resp.json())

    assert e["other_org"].id not in got, "别的小区的设备混进来了"
    assert e["other_type"].id not in got, "计划指定了设备类型，别的类型不该出现"
    assert e["retired"].id not in got, "已退役设备不该可被巡检"
    assert e["removed"].id not in got, "已逻辑删除设备不该出现"


@pytest.mark.asyncio
async def test_plan_without_device_type_returns_all_types(client, db_session, dev_env):
    """TC-INS-DEV-003: 计划未指定设备类型时应返回范围内所有类型，而不是什么都不返回"""
    e = dev_env
    plan = await make_plan(
        db_session,
        plan_name="不限类型",
        org_id=e["building_a"].id,
        device_type_id=None,
        responsible_user_id=e["maintainer"].id,
    )
    task = await make_task(
        db_session, plan_id=plan.id, responsible_user_id=e["maintainer"].id
    )

    got = ids_of(
        (
            await client.get(
                devices_url(task.id), headers=auth_headers(e["maintainer"])
            )
        ).json()
    )
    assert e["in_scope"].id in got
    assert e["other_type"].id in got, "未限定类型时不该把其它类型排除掉"
    assert e["other_org"].id not in got, "区域范围仍必须生效"


@pytest.mark.asyncio
async def test_carries_type_and_org_display_names(client, db_session, dev_env):
    """
    TC-INS-DEV-004: 类型名/区域名必须有值。

    前端表格要显示「类型」列。这两个字段取自 device_type / org 关系，
    忘了 selectinload 的话要么 500（MissingGreenlet），要么被兜成 None
    ——后者会让这一列空白而**不报错**，正是本项目反复栽的静默坑。
    """
    e = dev_env
    items = (
        await client.get(devices_url(e["task"].id), headers=auth_headers(e["maintainer"]))
    ).json()["data"]["items"]
    row = next(i for i in items if i["id"] == e["in_scope"].id)

    assert row["type_name"] == "烟感探测器"
    assert row["org_name"] == "楼A"
    assert row["device_code"]


@pytest.mark.asyncio
async def test_user_who_cannot_see_task_cannot_see_its_devices(client, db_session, dev_env):
    """
    TC-INS-DEV-005: **看不到该任务的人，不能借这个端点看到它的设备**。

    这个端点是新开的取数口子，如果不做任务级授权，它就成了一台绕过设备数据权限的
    设备枚举器：任何有 `inspection:execute` 的人换个 task_id 就能扫别人区域的设备。
    这里用一个 self 范围、且不是该任务责任人的用户来验证。
    """
    e = dev_env
    outsider = await create_inspection_user(
        db_session,
        "dev_outsider",
        ["inspection:view", "inspection:execute"],
        data_scope="self",
        org=e["building_b"],
    )

    resp = await client.get(
        devices_url(e["task"].id), headers=auth_headers(outsider)
    )

    assert resp.status_code == 404, (
        f"非责任人拿到了别人的应检设备：{resp.status_code} {resp.text}"
    )


@pytest.mark.asyncio
async def test_requires_execute_permission(client, db_session, dev_env):
    """TC-INS-DEV-006: 只有查看权限的用户不得调用（设备选择器属于执行链路）"""
    e = dev_env
    viewer = await create_inspection_user(
        db_session,
        "dev_viewer",
        ["inspection:view"],  # 没有 inspection:execute
        data_scope="all",
    )

    resp = await client.get(devices_url(e["task"].id), headers=auth_headers(viewer))

    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_unknown_task_returns_404(client, db_session, dev_env):
    """TC-INS-DEV-007: 不存在的任务返回 404，而不是空列表（空列表会被当成「没有设备」）"""
    e = dev_env
    resp = await client.get(
        devices_url(999999), headers=auth_headers(e["maintainer"])
    )

    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_keyword_filters_within_scope(client, db_session, dev_env):
    """TC-INS-DEV-008: 关键字在范围内筛选，不能把关键字当成绕过范围的手段"""
    e = dev_env
    got = ids_of(
        (
            await client.get(
                devices_url(e["task"].id),
                params={"keyword": "楼A烟感"},
                headers=auth_headers(e["maintainer"]),
            )
        ).json()
    )
    assert e["in_scope"].id in got
    assert e["in_scope_child"].id not in got, "关键字未生效"
    assert e["other_org"].id not in got, "关键字绕过了区域范围"
