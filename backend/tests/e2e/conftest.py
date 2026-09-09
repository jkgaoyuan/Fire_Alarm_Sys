"""
端到端用例的公共 fixture

真实运行的后端 + PostgreSQL + Redis：`E2E_BASE_URL` 未设置时整目录跳过，
因此 `pytest` 默认收集不会产生网络副作用。
"""

import os
import uuid

import httpx
import pytest

from tests.e2e.common import RUN_TAG, Api, device_payload, find_by_keyword, login


@pytest.fixture(scope="session")
def base_url() -> str:
    url = os.getenv("E2E_BASE_URL")
    if not url:
        pytest.skip("未设置 E2E_BASE_URL，跳过端到端回归（需真实后端容器）")
    return url.rstrip("/")


@pytest.fixture(scope="session")
def client(base_url) -> httpx.Client:
    cli = httpx.Client(base_url=base_url, timeout=30.0)
    try:
        cli.get("/device-types")
    except httpx.HTTPError as exc:
        pytest.skip(f"后端不可达 {base_url}：{exc}")
    yield cli
    cli.close()


@pytest.fixture(scope="session")
def chief(client) -> Api:
    """消防主管：data_scope=all，拥有全部设备/报警/监控权限"""
    return login(client, "chief")


@pytest.fixture(scope="session")
def duty(client) -> Api:
    """消防值班员：data_scope=dept，可读监控与处置报警，无平面图配置权"""
    return login(client, "duty")


@pytest.fixture(scope="session")
def maint(client) -> Api:
    """维保人员：data_scope=self，3.3 的监控与报警权限全部缺失"""
    return login(client, "maint")


@pytest.fixture(scope="session")
def prefix() -> str:
    """本次运行的编码前缀，保证与历史数据及重复运行互不冲突"""
    return RUN_TAG + uuid.uuid4().hex[:6].upper()


@pytest.fixture(scope="session")
def types(chief) -> dict:
    """type_code -> 设备类型（含 attribute_schema）"""
    return {t["type_code"]: t for t in chief.unwrap("GET", "/device-types")}


@pytest.fixture(scope="session")
def org_id(chief) -> int:
    """根组织节点 id（区域级联与 dept 数据范围的锚点）"""
    tree = chief.unwrap("GET", "/organizations/tree")
    assert tree, "组织树为空，请先执行 init_data.py"
    return tree[0]["id"]


@pytest.fixture(scope="session")
def make_device(chief, types, org_id, prefix):
    """按需建档一台设备，返回 DeviceOut"""

    def _make(**overrides) -> dict:
        code = overrides.pop("device_code", f"{prefix}-{uuid.uuid4().hex[:4].upper()}")
        return chief.unwrap(
            "POST", "/devices", json=device_payload(code, types, org_id, **overrides)
        )

    return _make


@pytest.fixture(scope="session")
def device_key() -> dict:
    """设备侧预共享凭据（`ALLOW_DEVICE_REPORT` 需在本地 .env.docker 里打开）"""
    return {"X-Device-Key": os.getenv("E2E_DEVICE_KEY", "local-e2e-device-key")}


@pytest.fixture(scope="session")
def make_alarm(client, make_device, device_key):
    """
    通过设备上报造一条报警，返回 {device, report}。

    报警只有上报这一个写入口（人工处置只能改状态），
    因此造数据必须先建档再上报，与真实链路一致。
    """

    def _make(alarm_type: str = "fire", **payload) -> dict:
        device = make_device()
        resp = client.post(
            "/monitor/report",
            json={"device_code": device["device_code"], "alarm_type": alarm_type, **payload},
            headers=device_key,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 200, body
        return {"device": device, "report": body["data"]}

    return _make


@pytest.fixture(scope="session", autouse=True)
def _cleanup(client, device_key):
    """
    会话结束按运行标记清库。

    设备是软删，报警行没有删除接口；残留的未复位报警会永久污染后续运行的统计卡片。
    复位前必须先把设备上报回 normal——上报新鲜时 5.5 的守卫会拒绝复位；
    而设备一旦删除就再也上报不了，所以顺序是「上报 → 复位 → 删设备」。
    """
    yield
    api = login(client, "chief")
    pending = api.unwrap(
        "GET",
        "/alarms",
        params={
            "page_size": 100,
            "status": "pending,confirmed,processing,false_alarm",
            "include_drill": True,
        },
    )
    leftovers = []
    for item in pending["items"]:
        code = item.get("device_code") or ""
        if not code.startswith(RUN_TAG):
            continue
        client.post("/monitor/report", json={"device_code": code, "status": "normal"}, headers=device_key)
        resp = api.post(
            f"/alarms/{item['id']}/reset", json={"physical_restored": True, "remark": "端到端清理"}
        )
        if resp.json().get("code") != 200:
            leftovers.append(f"{item['id']}({resp.json().get('message')})")
    for item in find_by_keyword(api, RUN_TAG)["items"]:
        api.delete(f"/devices/{item['id']}")
    if leftovers:
        print(f"\n[warn] 端到端清理后仍有未收敛报警需要下一轮清理: {leftovers}")
