"""
端到端回归 - 设备巡检（3.6 FR-032 ~ FR-036）
=============================================
覆盖巡检计划「操作列」对应的全部后端能力：

- 创建 → 列表 → 详情 → 编辑 → 启用/停用 → 生成任务 → 删除
- 已启用计划不允许删除（业务前置 400）
- 删除后再次查询走统一响应体 code=404（HTTP 仍是 200，见 testing-guidelines 第六节第 1 条）
- 维保人员可查看计划但不可管理计划（403）

运行方式（需真实容器）：

    docker compose up -d
    cd backend && E2E_BASE_URL=http://localhost:8000/api/v1 \
        python -m pytest -m e2e tests/e2e/test_inspection_e2e.py -v

未设置 `E2E_BASE_URL` 时整个目录 skip，默认 `python -m pytest` 不依赖容器。
依赖 `scripts/init_data.py` 的幂等预置数据（含 chief / maint 种子账号与巡检权限码）。
"""

import uuid
from datetime import date

import pytest

from tests.e2e.common import RUN_TAG

pytestmark = pytest.mark.e2e


# ==================== 夹具 ====================

@pytest.fixture(scope="module")
def responsible_id(chief) -> int:
    """巡检责任人：取种子用户列表中的第一个（主管自身）"""
    data = chief.unwrap("GET", "/users", params={"page": 1, "page_size": 1})
    assert data["items"], "用户列表为空，请先执行 backend/scripts/init_data.py"
    return data["items"][0]["id"]


@pytest.fixture
def created_plans():
    """本轮创建的巡检计划 id，用例追加、夹具负责收尾清理"""
    ids: list[int] = []
    yield ids
    # 清理在 _cleanup_plans 中统一执行（需要 chief 客户端）
    return ids


@pytest.fixture(autouse=True)
def _cleanup_plans(chief, created_plans):
    """
    用例结束后按前缀清库。

    后端只允许删除「已停用」计划，因此先 toggle 关闭再删；
    删除失败不抛错，只提示下一轮继续清（避免清理逻辑本身把用例判红）。
    """
    yield
    leftovers = []
    for plan_id in created_plans:
        chief.post(f"/inspection-plans/{plan_id}/toggle", json={"is_enabled": False})
        resp = chief.delete(f"/inspection-plans/{plan_id}")
        if resp.json().get("code") not in (200, 404):
            leftovers.append(f"{plan_id}({resp.json().get('message')})")
    if leftovers:
        print(f"\n[warn] 巡检计划清理未收敛，需下一轮清理: {leftovers}")


def plan_payload(prefix: str, org_id: int, responsible_user_id: int, **overrides) -> dict:
    """巡检计划请求体，plan_name 带运行标记便于按前缀识别"""
    payload = {
        "plan_name": f"{RUN_TAG}{prefix}-计划-{uuid.uuid4().hex[:4].upper()}",
        "org_id": org_id,
        "cycle_type": "daily",
        "responsible_user_id": responsible_user_id,
        "start_date": date.today().isoformat(),
    }
    payload.update(overrides)
    return payload


# ==================== 操作列全流程 ====================

def test_plan_crud_workflow(chief, prefix, org_id, responsible_id, created_plans):
    """TC-INS-E2E-001: 创建→列表→详情→编辑→停用→删除 全流程"""
    # 1. 创建
    payload = plan_payload(prefix, org_id, responsible_id)
    plan = chief.unwrap("POST", "/inspection-plans", json=payload)
    created_plans.append(plan["id"])
    assert plan["plan_name"] == payload["plan_name"]
    assert plan["is_enabled"] is True

    # 2. 列表可检索到
    listing = chief.unwrap(
        "GET", "/inspection-plans", params={"page": 1, "page_size": 100}
    )
    assert any(item["id"] == plan["id"] for item in listing["items"])

    # 3. 详情带统计字段
    detail = chief.unwrap("GET", f"/inspection-plans/{plan['id']}")
    assert detail["plan_name"] == payload["plan_name"]
    for field in ("total_tasks", "completed_tasks", "missed_tasks", "completion_rate"):
        assert field in detail

    # 4. 编辑
    updated = chief.unwrap(
        "PUT",
        f"/inspection-plans/{plan['id']}",
        json={"plan_name": f"{payload['plan_name']}-已更新"},
    )
    assert updated["plan_name"].endswith("-已更新")

    # 5. 停用
    toggled = chief.unwrap(
        "POST", f"/inspection-plans/{plan['id']}/toggle", json={"is_enabled": False}
    )
    assert toggled["is_enabled"] is False

    # 6. 删除
    resp = chief.delete(f"/inspection-plans/{plan['id']}")
    assert resp.json()["code"] == 200

    # 7. 再次查询：业务不存在走统一响应体 code=404，HTTP 仍是 200
    after = chief.get(f"/inspection-plans/{plan['id']}")
    assert after.status_code == 200
    assert after.json()["code"] == 404


def test_delete_enabled_plan_rejected(chief, prefix, org_id, responsible_id, created_plans):
    """TC-INS-E2E-002: 已启用计划不可直接删除，应提示先停用"""
    plan = chief.unwrap(
        "POST",
        "/inspection-plans",
        json=plan_payload(prefix, org_id, responsible_id, is_enabled=True),
    )
    created_plans.append(plan["id"])

    resp = chief.delete(f"/inspection-plans/{plan['id']}")
    assert resp.status_code == 400
    assert "请先停用" in resp.json()["detail"]


def test_generate_tasks_for_plan(chief, prefix, org_id, responsible_id, created_plans):
    """TC-INS-E2E-003: 手动生成任务后，任务列表可见当日任务"""
    plan = chief.unwrap(
        "POST",
        "/inspection-plans",
        json=plan_payload(prefix, org_id, responsible_id, is_enabled=True),
    )
    created_plans.append(plan["id"])

    tasks = chief.unwrap(
        "POST", f"/inspection-plans/{plan['id']}/generate", json={"days": 7}
    )
    assert isinstance(tasks, list)

    listing = chief.unwrap(
        "GET", "/inspection-tasks", params={"page": 1, "page_size": 100}
    )
    assert any(item["plan_id"] == plan["id"] for item in listing["items"])


# ==================== 权限矩阵 ====================

def test_maintainer_can_view_but_not_manage_plans(
    maint, prefix, org_id, responsible_id
):
    """TC-INS-E2E-004: 维保人员可查看计划列表，但不可创建计划（403）"""
    # 可查看
    resp = maint.get("/inspection-plans", params={"page": 1, "page_size": 10})
    assert resp.status_code == 200
    assert resp.json()["code"] == 200

    # 不可创建
    resp = maint.post(
        "/inspection-plans", json=plan_payload(prefix, org_id, responsible_id)
    )
    assert resp.status_code == 403
    assert "缺少权限" in resp.json()["detail"]


# ==================== 参数校验 ====================

def test_invalid_cycle_type_rejected(chief, prefix, org_id, responsible_id):
    """TC-INS-E2E-005: 非法周期类型应返回 422"""
    resp = chief.post(
        "/inspection-plans",
        json=plan_payload(prefix, org_id, responsible_id, cycle_type="invalid_cycle"),
    )
    assert resp.status_code == 422
