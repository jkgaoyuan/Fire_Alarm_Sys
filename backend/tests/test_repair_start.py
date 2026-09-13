"""
开始维修接口（3.7 FR-039 工单流转）
====================================

`assigned → repairing` 这一步在 2026-09-13 之前**没有任何代码实现**：
前端 `handleStartRepair` 只弹「开始维修功能待实现」，后端没有 `/start` 端点。
后果是整条链路断在中间——`crud.complete()` 要求 `status == "repairing"`，
而没有任何路径能把状态置为 `repairing`，于是工单永久停在「已派单」，
「完成维修」按钮（`v-if="row.status === 'repairing'"`）永不显示。

`returned → repairing`（验收退回后重新维修）同样不可达，且前端当时把它
错误地接到了 `/complete` 上，必然 400。

本文件钉住这条转移的行为：谁能调、什么状态能调、状态是否真的落库。
"""

import pytest
from sqlalchemy import select

from app.models.repair import RepairOrder
from tests.auth_helpers import auth_headers, create_user_with_perms
from tests.device_helpers import create_org
from tests.repair_helpers import make_device, make_repair_order

ORDERS_URL = "/api/v1/repair-orders"


async def env(db_session):
    """一台设备 + 三类用户 + 四种状态的工单"""
    building = await create_org(db_session, "总部大楼")
    device = await make_device(db_session, org_id=building.id)

    # 被指派的维修人：有 repair:repair
    repairer = await create_user_with_perms(
        db_session, "rs_repairer", ["repair:view", "repair:repair"]
    )
    # 另一个同样有 repair:repair 的人，但工单不归他
    other_repairer = await create_user_with_perms(
        db_session, "rs_other", ["repair:view", "repair:repair"]
    )
    # 只能看、不能填报（如值班员）
    viewer = await create_user_with_perms(db_session, "rs_viewer", ["repair:view"])

    assigned = await make_repair_order(
        db_session, device_id=device.id, repairer_id=repairer.id, status="assigned"
    )
    returned = await make_repair_order(
        db_session, device_id=device.id, repairer_id=repairer.id, status="returned"
    )
    pending = await make_repair_order(db_session, device_id=device.id, status="pending")
    pending_accept = await make_repair_order(
        db_session, device_id=device.id, repairer_id=repairer.id, status="pending_accept"
    )

    return locals()


def start(client, order_id, user):
    return client.put(f"{ORDERS_URL}/{order_id}/start", headers=auth_headers(user))


# ==================== 鉴权 ====================

@pytest.mark.asyncio
async def test_start_requires_authentication(client, db_session):
    """TC-RP-012: 未认证不能开始维修"""
    e = await env(db_session)

    resp = await client.put(f"{ORDERS_URL}/{e['assigned'].id}/start")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_start_requires_repair_permission(client, db_session):
    """TC-RP-013: 有登录但没有 repair:repair → 403"""
    e = await env(db_session)

    resp = await start(client, e["assigned"].id, e["viewer"])

    assert resp.status_code == 403
    assert "缺少权限" in resp.json()["message"]


@pytest.mark.asyncio
async def test_start_by_non_assignee_is_forbidden(client, db_session):
    """
    TC-RP-014: 有 repair:repair 但工单不归自己 → 403。

    权限码管「这类操作能不能做」，归属检查管「这一单归不归你」。
    与 `/complete` 同口径，两者叠加。
    """
    e = await env(db_session)

    resp = await start(client, e["assigned"].id, e["other_repairer"])

    assert resp.status_code == 403


# ==================== 状态流转 ====================

@pytest.mark.asyncio
async def test_start_moves_assigned_to_repairing(client, db_session):
    """TC-RP-015: 已派单工单的开始维修 → repairing，且走统一信封"""
    e = await env(db_session)

    resp = await start(client, e["assigned"].id, e["repairer"])

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["status"] == "repairing"
    assert body["data"]["id"] == e["assigned"].id


@pytest.mark.asyncio
async def test_start_moves_returned_to_repairing(client, db_session):
    """
    TC-RP-016: 验收退回后「重新维修」→ repairing（闭环）。

    不修会怎样：`returned → repairing` 在状态机表里定义了却无人实现，
    前端只好把它接到 `/complete` 上，而 `complete` 要求 `status == "repairing"`，
    调用必然 400——退回的工单从此无路可走。
    """
    e = await env(db_session)

    resp = await start(client, e["returned"].id, e["repairer"])

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "repairing"


@pytest.mark.asyncio
async def test_start_commits_status_change(client, db_session):
    """
    TC-RP-017: 状态变更必须真的提交。

    测试夹具与请求共用会话，所以「查得到」证明不了「提交了」——
    未提交的变更在同一会话里一样可见（testing-guidelines 第 23 条）。
    先 rollback() 丢弃未提交内容再查，才能证明它落库了。
    """
    e = await env(db_session)
    order_id = e["assigned"].id

    assert (await start(client, order_id, e["repairer"])).status_code == 200

    await db_session.rollback()  # 同步方法，勿 await
    status = (
        await db_session.execute(
            select(RepairOrder.status).where(RepairOrder.id == order_id)
        )
    ).scalar_one()

    assert status == "repairing", "状态变更未提交，被 rollback 丢弃了"


@pytest.mark.asyncio
async def test_start_rejects_unassigned_pending_order(client, db_session):
    """
    TC-RP-018: 未派单（pending，无 repairer_id）的工单不能被任何人开始。

    拦在归属检查上（403）而不是状态检查（400）——与 `/complete` 的检查顺序
    一致：先问「这一单归不归你」，再问「这个状态能不能操作」。
    所以未指派的工单对所有人都是 403，不会因为「谁都不是负责人」而漏过去。
    """
    e = await env(db_session)

    resp = await start(client, e["pending"].id, e["repairer"])

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_start_rejects_pending_state_for_assignee(client, db_session):
    """
    TC-RP-019: 状态机本身也要拦住跳步（已指派但仍是 pending 的异常数据）。

    正常路径下 `pending` 一定没有 repairer_id，本用例构造的是不该存在的数据——
    但状态判断是**独立于归属检查**的第二道闸，缺了它，任何能造成这种数据的
    路径（导入、修数据、将来的批量接口）都能把工单跳过派单直接推进到维修中。
    """
    e = await env(db_session)
    anomalous = await make_repair_order(
        db_session,
        device_id=e["pending"].device_id,
        repairer_id=e["repairer"].id,
        status="pending",
    )

    resp = await start(client, anomalous.id, e["repairer"])

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_start_rejects_pending_accept_order(client, db_session):
    """TC-RP-020: 待验收的工单不能再「开始维修」（状态不能回退）"""
    e = await env(db_session)

    resp = await start(client, e["pending_accept"].id, e["repairer"])

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_start_missing_order_returns_404(client, db_session):
    """TC-RP-021: 工单不存在 → 404"""
    e = await env(db_session)

    resp = await start(client, 999999, e["repairer"])

    assert resp.status_code == 404
