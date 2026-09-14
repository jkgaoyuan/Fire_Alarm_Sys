"""
巡检记录提交与查询（3.6 FR-034）
=================================

2026-09-14 实测缺陷：提交巡检记录报

    2 validation errors for InspectionRecordResponse
    device_code  Field required [input_value=<InspectionRecord object>]
    device_name  Field required [input_value=<InspectionRecord object>]

**根因**：`InspectionRecordResponse` 把 `device_code` / `device_name` 定为**必填**，
但 `InspectionRecord` 模型上**根本没有这两个属性**（列只有
`id/task_id/device_id/inspected_by/created_by/result/abnormal_desc/photos/inspected_at/...`，
设备信息要通过 `device` 关系取）。两个端点都用 `model_validate(ORM 对象)` 构造响应，
读不到属性即抛 `ValidationError` → 未捕获 → 500。

**为什么能活到现在**：`/inspection-tasks/{id}/records` 与 `/inspection-records`
全仓库**零测试覆盖**。缺陷自 `c4a857c2`（3.7 开发）引入，横跨两次交付未被发现。

**影响面**（两个端点，不止报错的那一个）：
- `POST /inspection-tasks/{task_id}/records` —— 用户实际撞到的
- `GET  /inspection-records` —— 列表同样构造该响应

另有一处**静默**问题：`inspected_by_name` 是 Optional，`model_validate` 取不到时
不报错、直接给 `None`——页面显示空白而没有任何提示。本文件一并钉住。
"""
from datetime import date

import pytest
import pytest_asyncio

from tests.device_helpers import make_device
from tests.inspection_helpers import (
    auth_headers,
    create_inspection_user,
    create_org,
    make_plan,
    make_record,
    make_task,
)

RECORDS_URL = "/api/v1/inspection-records"
TASKS_URL = "/api/v1/inspection-tasks"


def submit_url(task_id: int) -> str:
    return f"/api/v1/inspection-tasks/{task_id}/records"


@pytest_asyncio.fixture
async def rec_env(db_session):
    """一个组织 + 一名可执行巡检的用户 + 一台设备 + 一个计划 + 一条任务"""
    org = await create_org(db_session, "总部大楼")
    user = await create_inspection_user(
        db_session,
        "insp_rec",
        ["inspection:execute", "inspection:view"],
        data_scope="all",
    )
    device = await make_device(
        db_session, org_id=org.id, device_name="1F大厅烟感A01"
    )
    plan = await make_plan(
        db_session,
        plan_name="每日巡检",
        org_id=org.id,
        responsible_user_id=user.id,
    )
    task = await make_task(db_session, plan_id=plan.id, responsible_user_id=user.id)
    return locals()


def payload(device_id: int, task_id: int, result: str = "normal") -> dict:
    return {
        "task_id": task_id,
        "device_id": device_id,
        "result": result,
        "abnormal_desc": None,
        "photos": [],
    }


# ==================== 提交记录 ====================

@pytest.mark.asyncio
async def test_submit_record_returns_device_fields(client, db_session, rec_env):
    """
    TC-INS-REC-001: 提交记录必须成功，且响应里带得出设备编码与名称。

    不修会怎样：`model_validate(record)` 读不到 `device_code` → ValidationError → 500。
    数据其实已经落库（commit 在构造响应之前），但调用方只看到报错，会重复提交。
    """
    e = rec_env
    # 断言要用的期望值必须在 expire_all() **之前**取出，否则会在测试自身里
    # 触发懒加载 → 测试自己抛 MissingGreenlet，把待测问题淹掉。
    task_id, device_id, headers = e["task"].id, e["device"].id, auth_headers(e["user"])
    expect_code, expect_name = e["device"].device_code, e["device"].device_name

    # 关键：把 identity map 清掉再发请求。
    # 测试夹具与请求**共用同一个 session**，不清的话 device / user 早已在 identity map
    # 里，`_record_out` 访问 `record.device` / `record.inspector` 时**不会触发 SQL**——
    # 于是「忘了 selectinload」这个缺陷会被完全掩盖（实测：去掉 options 后本条仍绿）。
    # 生产环境每请求一个 session，那时就是 MissingGreenlet。
    db_session.expire_all()

    resp = await client.post(
        submit_url(task_id),
        json=payload(device_id, task_id),
        headers=headers,
    )

    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["code"] == 200, body
    data = body["data"]
    assert data["device_code"] == expect_code
    assert data["device_name"] == expect_name


@pytest.mark.asyncio
async def test_submit_record_reports_inspector_name(client, db_session, rec_env):
    """TC-INS-REC-002: `inspected_by_name` 必须真的有值，不能被 None 静默兜底"""
    e = rec_env

    resp = await client.post(
        submit_url(e["task"].id),
        json=payload(e["device"].id, e["task"].id),
        headers=auth_headers(e["user"]),
    )

    data = resp.json()["data"]
    assert data["inspected_by_name"] == e["user"].real_name


@pytest.mark.asyncio
async def test_submit_record_is_persisted(client, db_session, rec_env):
    """TC-INS-REC-003: 记录确实提交（核对 8bee12bb 补的 commit 收口没被回退）"""
    from sqlalchemy import func, select

    from app.models.inspection import InspectionRecord

    e = rec_env
    await client.post(
        submit_url(e["task"].id),
        json=payload(e["device"].id, e["task"].id),
        headers=auth_headers(e["user"]),
    )

    db_session.expire_all()
    count = (
        await db_session.execute(select(func.count(InspectionRecord.id)))
    ).scalar_one()
    assert count == 1, "接口返回了但记录没落库"


# ==================== 记录列表 ====================

@pytest.mark.asyncio
async def test_list_records_returns_device_fields(client, db_session, rec_env):
    """
    TC-INS-REC-004: 列表接口**独立地**也要返回设备字段。

    它和提交接口构造响应共用一个 schema，会一起坏——用户只报了提交，
    但列表在同一根因上，只修一处会留下一半。

    记录**直接落库**而不是先调提交接口：否则提交一坏这条也跟着坏，
    两个端点的问题就糊在一起，分不清是哪一个。

    同样要 `expire_all()`：否则 device / user 在 identity map 里，
    列表查询即使不带 selectinload 也不会触发懒加载，缺陷被掩盖。
    """
    e = rec_env
    # 期望值先取出（expire_all 后读会触发懒加载，见上一条用例的说明）
    headers = auth_headers(e["user"])
    expect_code, expect_name = e["device"].device_code, e["device"].device_name
    expect_inspector = e["user"].real_name

    await make_record(
        db_session,
        task_id=e["task"].id,
        device_id=e["device"].id,
        inspected_by=e["user"].id,
    )

    db_session.expire_all()

    resp = await client.get(RECORDS_URL, headers=headers)

    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["device_code"] == expect_code
    assert items[0]["device_name"] == expect_name
    assert items[0]["inspected_by_name"] == expect_inspector


@pytest.mark.asyncio
async def test_task_list_reports_records_count(client, db_session, rec_env):
    """
    TC-INS-REC-006: 任务列表的「已记录数」必须是**真的数量**。

    不修会怎样：用户提交完记录，任务列表那一列仍显示 0。
    根因是前后端对不上——后端声明的是 `records`（列表）且**从未填充**（恒为 []），
    前端一个页面读 `records_count`（字段根本不存在）、另一个读
    `records?.length`，两处都被 `|| 0` 兜底成 0，**静默**而不是报错。
    """
    e = rec_env
    headers = auth_headers(e["user"])

    # 无记录时是 0，且字段必须存在（不能靠 || 0 兜底出一个「看起来对」的值）
    resp = await client.get(TASKS_URL, headers=headers)
    items = resp.json()["data"]["items"]
    assert items, "任务列表为空，用例前提不成立"
    assert "records_count" in items[0], f"响应里没有 records_count：{sorted(items[0])}"
    assert items[0]["records_count"] == 0

    # 落两条记录
    for _ in range(2):
        await make_record(
            db_session,
            task_id=e["task"].id,
            device_id=e["device"].id,
            inspected_by=e["user"].id,
        )

    resp = await client.get(TASKS_URL, headers=headers)
    items = resp.json()["data"]["items"]
    assert items[0]["records_count"] == 2, "已记录数没有跟着记录数走"


@pytest.mark.asyncio
async def test_list_response_has_no_dead_records_field(client, db_session, rec_env):
    """
    TC-INS-REC-007: 列表响应里不应再有恒为 [] 的 `records` 字段。

    它是 InspectionTaskWithDetails 带来的，列表端点从不填充——
    留着它就是在邀请下一个人照着读、再踩一次「恒显示 0」。
    """
    e = rec_env
    await make_record(
        db_session,
        task_id=e["task"].id,
        device_id=e["device"].id,
        inspected_by=e["user"].id,
    )

    resp = await client.get(TASKS_URL, headers=auth_headers(e["user"]))
    items = resp.json()["data"]["items"]

    assert "records" not in items[0], (
        "列表项又带上了 records 字段；它有记录时也会是 []（从不填充），"
        "前端照着读就会显示 0"
    )


@pytest.mark.asyncio
async def test_submit_abnormal_record_links_repair_order(client, db_session, rec_env):
    """
    TC-INS-REC-005: 异常结果自动建维修工单（3.7 FR-038）仍成立。

    这条路径内部会走 `RepairOrderCRUD.create()`，它自带 commit——
    与「正常」结果那条只 flush 的路径提交时机不同。改响应构造时不要碰坏它。
    """
    e = rec_env

    resp = await client.post(
        submit_url(e["task"].id),
        json=payload(e["device"].id, e["task"].id, result="abnormal"),
        headers=auth_headers(e["user"]),
    )

    assert resp.status_code in (200, 201), resp.text
    record_id = resp.json()["data"]["id"]

    from sqlalchemy import select

    from app.models.repair import RepairOrder

    # 先把 device_id 取出来：expire_all() 会把夹具对象一并过期，
    # 之后在同步上下文读 e["device"].id 会触发刷新 → 测试自己抛 MissingGreenlet，
    # 把「接口对不对」这个问题淹掉。（test_repair_authz.py 的 TC-RP-011 踩过同一个坑。）
    device_id = e["device"].id
    db_session.expire_all()

    order = (
        await db_session.execute(
            select(RepairOrder).where(RepairOrder.device_id == device_id)
        )
    ).scalar_one_or_none()
    assert order is not None, "异常巡检没有自动建维修工单"
    assert order.inspection_record_id == record_id
