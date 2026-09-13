"""
维修工单的授权与数据范围（3.7 FR-042）
======================================

2026-09-13 权限审计发现：`repair:*` 5 个权限码在 init_data.py 里定义了、
也逐角色授予了，却**没有任何端点校验**——因为 repair.py 用的是
**手写的角色判断**（`if not any(r.role_code == "chief" ...)`）。
后果是「授予/撤销这些码」是空操作，RBAC 看起来生效、实际没接线。

本文件钉住接线后的行为，并补上此前完全缺失的**数据范围过滤**：
list/get 只看登录即可读全部工单（含故障描述、设备、人员），
与巡检任务那批同类问题一致。

改造前的事实（实测，非推断）：
- `list_repair_orders` / `get_repair_order` 无权限码、无数据范围
- `assign` / `accept` / `return` 硬编码 `role_code == "chief"`
- 能合法进入该页面的角色都不受影响：duty_officer 与 maintainer 都有
  repair:view / repair:create；chief 在 init_data 里被绑定全部权限码
"""

from datetime import date

import pytest

from tests.auth_helpers import auth_headers, create_user_with_perms
from tests.device_helpers import create_org
from tests.repair_helpers import make_device, make_repair_order

ORDERS_URL = "/api/v1/repair-orders"


async def env(db_session):
    """两棵组织树 + 三类数据范围角色 + 两台设备"""
    building = await create_org(db_session, "总部大楼")
    floor1 = await create_org(db_session, "1号楼", parent=building)
    other = await create_org(db_session, "外部大楼")

    chief = await create_user_with_perms(
        db_session,
        "rp_chief",
        ["repair:view", "repair:create", "repair:assign", "repair:accept", "repair:repair"],
        data_scope="all",
    )
    dept_user = await create_user_with_perms(
        db_session, "rp_dept", ["repair:view"], data_scope="dept", org=floor1
    )
    self_user = await create_user_with_perms(
        db_session, "rp_self", ["repair:view"], data_scope="self"
    )
    other_user = await create_user_with_perms(
        db_session, "rp_other", ["repair:view"], data_scope="all"
    )
    nobody = await create_user_with_perms(db_session, "rp_nobody", ["device:view"])

    inner_device = await make_device(db_session, org_id=floor1.id)
    outer_device = await make_device(db_session, org_id=other.id)

    mine = await make_repair_order(
        db_session, device_id=inner_device.id, created_by=self_user.id
    )
    not_mine = await make_repair_order(
        db_session, device_id=outer_device.id, created_by=other_user.id
    )

    return locals()


def ids(body):
    return {item["id"] for item in body["data"]["items"]}


# ==================== 权限码 ====================

@pytest.mark.asyncio
async def test_list_requires_authentication(client):
    """TC-RP-001: 未认证读工单列表必须 401"""
    assert (await client.get(ORDERS_URL)).status_code == 401


@pytest.mark.asyncio
async def test_list_requires_view_permission(client, db_session):
    """TC-RP-002: 有登录但缺 repair:view → 403（此前是 200）"""
    e = await env(db_session)

    resp = await client.get(ORDERS_URL, headers=auth_headers(e["nobody"]))

    assert resp.status_code == 403
    assert "缺少权限" in resp.json()["message"]


@pytest.mark.asyncio
async def test_assign_requires_assign_permission(client, db_session):
    """
    TC-RP-003: 派单需要 repair:assign，而不是「角色码必须是 chief」。

    不修会怎样：派单权限硬编码在角色码上，给别的角色授予 repair:assign
    不起任何作用，调整派单权限必须改代码。
    """
    e = await env(db_session)
    order = await make_repair_order(db_session, device_id=e["inner_device"].id)

    # 只有 repair:view，没有 repair:assign
    resp = await client.put(
        f"{ORDERS_URL}/{order.id}/assign",
        json={"repairer_id": e["other_user"].id},
        headers=auth_headers(e["self_user"]),
    )
    assert resp.status_code == 403, "缺 repair:assign 却放行了派单"

    # 有 repair:assign 的可通过
    resp = await client.put(
        f"{ORDERS_URL}/{order.id}/assign",
        json={"repairer_id": e["other_user"].id},
        headers=auth_headers(e["chief"]),
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_complete_requires_repair_permission(client, db_session):
    """TC-RP-004: 完成维修需要 repair:repair（叠加原有的归属检查）"""
    e = await env(db_session)
    order = await make_repair_order(
        db_session, device_id=e["inner_device"].id, repairer_id=e["self_user"].id
    )

    # self_user 是维修人（归属检查过得去），但没有 repair:repair
    resp = await client.put(
        f"{ORDERS_URL}/{order.id}/complete",
        json={"repair_result": "已更换配件"},
        headers=auth_headers(e["self_user"]),
    )
    assert resp.status_code == 403, "缺 repair:repair 却放行了维修填报"


# ==================== 数据范围 ====================

@pytest.mark.asyncio
async def test_all_scope_sees_everything(client, db_session):
    """TC-RP-005: data_scope=all 不受限"""
    e = await env(db_session)

    resp = await client.get(ORDERS_URL, headers=auth_headers(e["chief"]))

    assert ids(resp.json()) == {e["mine"].id, e["not_mine"].id}


@pytest.mark.asyncio
async def test_self_scope_sees_only_related_orders(client, db_session):
    """
    TC-RP-006: data_scope=self 只看与我有关的工单。

    不修会怎样：此前**完全没有数据范围过滤**，任何登录用户都能读到全部工单的
    故障描述、设备与人员信息。

    口径是「我报的 / 我修的 / 我验收的 / 我建的」，不只是 created_by——
    工单是多方协作对象，只按 created_by 过滤会让维修人看不到派给自己的单。
    """
    e = await env(db_session)

    resp = await client.get(ORDERS_URL, headers=auth_headers(e["self_user"]))

    assert ids(resp.json()) == {e["mine"].id}


@pytest.mark.asyncio
async def test_self_scope_includes_assigned_repairer(client, db_session):
    """TC-RP-007: 被指派的维修人必须能看到该工单（哪怕不是自己建的）"""
    e = await env(db_session)
    assigned = await make_repair_order(
        db_session,
        device_id=e["outer_device"].id,
        created_by=e["other_user"].id,
        repairer_id=e["self_user"].id,
    )

    resp = await client.get(ORDERS_URL, headers=auth_headers(e["self_user"]))

    assert assigned.id in ids(resp.json()), "派给自己的单看不见"


@pytest.mark.asyncio
async def test_dept_scope_uses_device_org(client, db_session):
    """
    TC-RP-008: data_scope=dept 经 device.org_id 折算。

    RepairOrder 自己没有 org_id（这点与 InspectionTask 相同），
    组织要从设备反查；直接用 user_service.apply_data_scope 会因属性缺失
    静默变成 no-op——调用看起来生效、实际谁都能看全部。
    """
    e = await env(db_session)

    resp = await client.get(ORDERS_URL, headers=auth_headers(e["dept_user"]))

    assert ids(resp.json()) == {e["mine"].id}, "部门范围未按设备所属组织折算"


@pytest.mark.asyncio
async def test_total_matches_items(client, db_session):
    """TC-RP-009: total 与 items 用同一个范围条件，不能出现「总数 2、只回 1 条」"""
    e = await env(db_session)

    resp = await client.get(ORDERS_URL, headers=auth_headers(e["self_user"]))
    body = resp.json()

    assert body["data"]["total"] == len(body["data"]["items"]) == 1


@pytest.mark.asyncio
async def test_out_of_scope_detail_returns_404(client, db_session):
    """
    TC-RP-010: 越权读详情按「不存在」处理（404），不泄露存在性。

    不修会怎样：列表做了范围过滤而详情没做，等于给了一个按 ID 逐个捞取的旁路。
    """
    e = await env(db_session)

    resp = await client.get(
        f"{ORDERS_URL}/{e['not_mine'].id}", headers=auth_headers(e["self_user"])
    )

    assert resp.status_code == 404

    # 范围内的应正常返回
    resp = await client.get(
        f"{ORDERS_URL}/{e['mine'].id}", headers=auth_headers(e["self_user"])
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_in_scope_detail_survives_fresh_session(client, db_session):
    """
    TC-RP-011: 详情接口在**关系未被预先加载**时也必须能返回。

    不修会怎样：响应构造会访问 `order.device` / `order.reporter` 等关系。
    异步会话下懒加载抛 MissingGreenlet → 线上 500。
    2026-09-13 给详情加范围过滤时，把 `crud.get()`（带 4 个 selectinload）
    换成了裸 `select(RepairOrder)`，正好踩中——而 **TC-RP-010 给了假绿**：
    测试夹具与请求共用会话，设备/用户对象已在 identity map 里，
    访问关系根本没触发 SQL。实测 admin 打详情返回 500 才发现。

    所以这里先 `expire_all()` 把 identity map 清掉，强制关系从库里真加载。
    """
    e = await env(db_session)
    # 先把要用的 id 取出来：expire_all() 会把夹具对象一并过期，
    # 之后在测试里再读 e['mine'].id 会触发同步刷新 → 测试自己抛 MissingGreenlet，
    # 把「接口有没有 500」这个待测问题淹掉。（第一版就是这么写错的。）
    mine_id = e["mine"].id
    headers = auth_headers(e["chief"])

    db_session.expire_all()  # 同步方法，勿 await

    resp = await client.get(f"{ORDERS_URL}/{mine_id}", headers=headers)

    assert resp.status_code == 200, f"关系懒加载失败：{resp.text[:200]}"
    body = resp.json()["data"]
    # 顺带确认关联字段真的取到了值，而不是被 None 兜底掩盖
    assert body["device_name"] == "测试设备"
