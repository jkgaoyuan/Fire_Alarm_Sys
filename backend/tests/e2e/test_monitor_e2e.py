"""
3.3 实时监控与电子地图 —— 端到端回归用例

区别于 `tests/test_ws_realtime.py` / `tests/test_monitor_api.py`（fakeredis + ASGI 进程内调用），
本模块通过真实 HTTP/WS 访问 **运行中的后端容器 + PostgreSQL + Redis**，覆盖单测环境拿不到的行为：
XADD → 消费者组 → 广播的真实链路延迟（计划里程碑 M1 的 P95 红线）、握手在真实 uvicorn 下的
拒绝形态、平面图落盘后 `/static` 可访问与删除、轨迹导出的文件字节，以及 Nginx 反代
（`/ws/`、`/static/`）与三类角色的权限矩阵。

前置（上报端点默认关闭，需本地凭据；离线扫描会把上一批用例的设备刷成 offline，
统计卡片的增量断言要求它停摆，其自身行为由 `tests/test_device_report.py` 覆盖）：

    docker compose up -d
    # .env.docker: ALLOW_DEVICE_REPORT=true / DEVICE_REPORT_KEY=local-e2e-device-key
    #              OFFLINE_SCAN_ENABLED=false
    E2E_BASE_URL=http://localhost:8000/api/v1 \\
        python -m pytest tests/e2e/test_monitor_e2e.py -v

公共 fixture 见 `tests/e2e/conftest.py`；设备与报警均带运行前缀，会话结束时复位并逻辑删除。
"""

import asyncio
import io
import json
import math
import os
import time
from datetime import datetime
from urllib.parse import urlsplit

import httpx
import pytest
from PIL import Image

pytestmark = pytest.mark.e2e

# 计划 8 节 M1：模拟器 → WS → 客户端帧延迟 P95 ≤ 2s，PRD 验收红线 3s
LATENCY_SAMPLES = 10
LATENCY_P95_BUDGET = 2.0
LATENCY_MAX_BUDGET = 3.0

FRAME_KEYS = {"id", "type", "ts", "data"}
PNG_MIME = "image/png"


# ==================== 工具 ====================


def api_origin(base_url: str) -> str:
    """去掉 /api/v1 后缀，用于直接访问后端自身挂载的 /static 与 /ws"""
    parts = urlsplit(base_url)
    return f"{parts.scheme}://{parts.netloc}"


def ticket_of(api) -> str:
    data = api.unwrap("POST", "/monitor/ws-ticket")
    assert data["ws_path"] == "/ws/devices", "握手地址由后端给出，前端不能硬编码"
    return data["ticket"]


def ws_url(origin: str, ticket: str, last_msg_id: str | None = None) -> str:
    query = f"?ticket={ticket}"
    if last_msg_id:
        query += f"&last_msg_id={last_msg_id}"
    return f"{origin}/ws/devices{query}"


def report(client: httpx.Client, device_key: dict, device_code: str, **payload):
    """设备上报走预共享凭据，不带用户 Token"""
    return client.post(
        "/monitor/report", json={"device_code": device_code, **payload}, headers=device_key
    )


async def _api(api, method: str, url: str, **kw):
    """在 WS 协程里触发一次 REST 动作，失败时先报 HTTP 结果而不是「帧没来」"""
    resp = await asyncio.to_thread(api.request, method, url, **kw)
    assert resp.status_code == 200, f"{method} {url} -> {resp.status_code} {resp.text}"
    return resp


async def _report(client, device_key, device_code: str, **payload):
    resp = await asyncio.to_thread(report, client, device_key, device_code, **payload)
    assert resp.json()["code"] == 200, resp.text
    return resp


async def _await_frame(ws, expected_type: str, timeout: float = 8.0, **fields) -> dict:
    """等到类型与关键字段都匹配的帧；期间经过的其他帧用于失败诊断"""
    seen: list[str] = []
    deadline = time.perf_counter() + timeout
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            pytest.fail(f"{timeout}s 内未收到 {expected_type} 帧，已收到：{seen}")
        try:
            frame = json.loads(await asyncio.wait_for(ws.recv(), remaining))
        except asyncio.TimeoutError:
            continue
        seen.append(f"{frame['type']}:{frame['data'].get('device_code') or frame['data'].get('alarm_id')}")
        if frame["type"] != expected_type:
            continue
        if all(frame["data"].get(key) == value for key, value in fields.items()):
            return frame


async def _assert_no_frame(ws, expected_type: str, timeout: float = 1.5) -> None:
    """幂等操作不得再次广播（多端会被反复触发停止音频）"""
    try:
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout))
    except asyncio.TimeoutError:
        return
    pytest.fail(f"不应再收到 {expected_type}，实际收到 {frame['type']} {frame['data']}")


def png_bytes(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (240, 240, 240)).save(buf, "PNG")
    return buf.getvalue()


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def _stream_ms(entry_id: str) -> int:
    """Stream id 形如 `1788902063408-0`，按毫秒段比较，字典序在跨位数时会失真"""
    return int(entry_id.split("-")[0])


# ==================== fixtures ====================


@pytest.fixture(scope="module")
def ws_origin(base_url) -> str:
    parts = urlsplit(base_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    netloc = parts.netloc
    if ":" not in netloc:
        port = parts.port or (443 if scheme == "wss" else 80)
        netloc = f"{netloc}:{port}"
    return f"{scheme}://{netloc}"


@pytest.fixture(scope="module")
def floor_org(chief) -> int:
    """
    平面图的挂载节点。

    种子组织树只有一个根节点且无创建接口，平面图上传也不校验 org_type，
    因此端到端直接挂在根节点上；「zone 挂设备、floor 挂图」的继承规则由单测覆盖。
    """
    return chief.unwrap("GET", "/organizations/tree")[0]["id"]


@pytest.fixture
def uploaded_map(chief, floor_org):
    """上传一张 2400x1200 的平面图，用例结束移除，不给种子数据留残留"""
    resp = chief.post(
        f"/organizations/{floor_org}/map-image",
        files={"file": ("floor-1f.png", io.BytesIO(png_bytes(2400, 1200)), PNG_MIME)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200, body
    yield body["data"]
    chief.delete(f"/organizations/{floor_org}/map-image")


# ==================== 大屏与 TopN（FR-014） ====================


def test_dashboard_counts_move_with_reports(chief, client, device_key, make_device):
    """统计卡片随上报变化；online 口径为 总数 - 离线 - 退役（计划 A-13）"""
    before = chief.unwrap("GET", "/monitor/dashboard")

    first = make_device()
    second = make_device()
    assert report(client, device_key, first["device_code"], alarm_type="fire").json()["code"] == 200
    assert report(client, device_key, second["device_code"], alarm_type="fault").json()["code"] == 200

    after = chief.unwrap("GET", "/monitor/dashboard")
    assert after["total"] == before["total"] + 2
    assert after["alarm"] == before["alarm"] + 1
    assert after["fault"] == before["fault"] + 1
    assert after["pending_alarm"] == before["pending_alarm"] + 2
    assert after["pending_fire"] == before["pending_fire"] + 1
    assert after["normal"] == before["normal"], "两台新设备都被上报带出 normal，计数不得虚增"
    assert after["online"] == after["total"] - after["offline"] - after["retired"]


def test_recent_alarms_pin_pending_fire_and_hide_drill(
    chief, client, device_key, make_device, make_alarm
):
    """
    TopN 排序与演练隔离（计划 5.1 / FR-014）。

    帧字段名为 alarm_id（与 /alarms 的 id 不同），前端靠 utils/alarm.js 归一，
    这里把契约钉住，防止后端改名把大屏与地图一起打断。
    """
    drill = make_device()
    drill_report = report(
        client,
        device_key,
        drill["device_code"],
        alarm_type="pre_fire",
        is_drill=True,
        location_description="年度演练",
    ).json()["data"]
    assert drill_report["alarm_created"] is True

    fired = make_alarm("fire", location_description="3 层东侧走廊")
    alarm_id = fired["report"]["alarm_id"]

    items = chief.unwrap("GET", "/monitor/alarms/recent", params={"limit": 50})
    assert items[0]["alarm_type"] == "fire" and items[0]["status"] == "pending", "未确认火警必须置顶"

    mine = next(item for item in items if item["alarm_id"] == alarm_id)
    assert mine["device_id"] == fired["device"]["id"]
    assert mine["org_id"] == fired["device"]["org_id"], "帧缺 org_id 会让 WS 权限过滤失效"
    assert mine["map_x"] == 120.5 and mine["map_y"] == 340.25, "地图打点依赖上报里的原图像素坐标"
    assert mine["location_description"] == "3 层东侧走廊"
    assert mine["alarm_level"] == "critical"
    assert drill_report["alarm_id"] not in {item["alarm_id"] for item in items}, "演练报警默认不入大屏"

    with_drill = chief.unwrap(
        "GET", "/monitor/alarms/recent", params={"limit": 100, "include_drill": True}
    )
    assert drill_report["alarm_id"] in {item["alarm_id"] for item in with_drill}


# ==================== WebSocket 握手与推送（FR-013） ====================


def test_ws_ticket_is_one_time_and_required(chief, ws_origin):
    """
    一次性 Ticket（计划 3.3 / OQ-6）。

    注意：uvicorn 下「accept 前 close(4401)」表现为握手被拒（HTTP 403），
    浏览器侧只会看到 onclose(1006)，4401 仅在 ASGI 层可断言（见 test_ws_realtime.py）。
    """
    websockets = pytest.importorskip("websockets")
    ticket = ticket_of(chief)

    async def probe(url: str):
        async with websockets.connect(url, open_timeout=5) as ws:
            await ws.send(json.dumps({"action": "ping"}))
            # 上一用例的事件可能仍在扇出途中，客户端本就按 type 分派
            return await _await_frame(ws, "pong", timeout=6)

    frame = asyncio.run(probe(ws_url(ws_origin, ticket)))
    assert frame["type"] == "pong" and set(frame) == FRAME_KEYS

    for bad in (ws_url(ws_origin, "not-a-real-ticket"), f"{ws_origin}/ws/devices"):
        with pytest.raises(Exception) as exc:
            asyncio.run(probe(bad))
        assert "403" in str(exc.value), str(exc.value)

    with pytest.raises(Exception) as exc:
        asyncio.run(probe(ws_url(ws_origin, ticket)))
    assert "403" in str(exc.value), "同一 ticket 重放必须被拒绝"


def test_alarm_new_latency_within_budget(chief, client, device_key, make_device, ws_origin):
    """M1 红线：模拟器上报 → WS 客户端收到 alarm_new，P95 ≤ 2s 且无单帧超 3s"""
    websockets = pytest.importorskip("websockets")
    devices = [make_device() for _ in range(LATENCY_SAMPLES)]

    async def measure() -> tuple[list[float], dict]:
        latencies: list[float] = []
        last_frame: dict = {}
        async with websockets.connect(
            ws_url(ws_origin, ticket_of(chief)), open_timeout=5
        ) as ws:
            for device in devices:
                started = time.perf_counter()
                await _report(
                    client,
                    device_key,
                    device["device_code"],
                    alarm_type="fire",
                    location_description="延迟采样",
                )
                # 上报先广播 device_status 再广播 alarm_new，只统计业务报警帧
                last_frame = await _await_frame(ws, "alarm_new", device_id=device["id"])
                latencies.append(time.perf_counter() - started)
        return latencies, last_frame

    latencies, frame = asyncio.run(measure())
    assert len(latencies) == LATENCY_SAMPLES
    assert set(frame) == FRAME_KEYS, "帧协议 {id, type, ts, data} 不得随意增删顶层键"
    assert frame["id"], "id 即前端重连用的 last_msg_id，不能为空"
    assert frame["data"]["alarm_type"] == "fire"

    p95 = percentile(latencies, 0.95)
    print(
        "\n[latency] n={} p50={:.3f}s p95={:.3f}s max={:.3f}s".format(
            len(latencies), percentile(latencies, 0.5), p95, max(latencies)
        )
    )
    assert p95 <= LATENCY_P95_BUDGET, f"P95={p95:.3f}s 超过 2s 预算：{latencies}"
    assert max(latencies) <= LATENCY_MAX_BUDGET, f"单帧 {max(latencies):.3f}s 触到 3s 红线"


def test_handling_actions_broadcast_to_clients(
    chief, client, device_key, make_alarm, ws_origin
):
    """
    一条连接上跑完消音 → 确认 → 恢复上报 → 复位的广播序列（FR-016 / FR-013）。

    消音重复调用必须幂等：第二次不再广播，否则多端会被反复触发停音。
    """
    websockets = pytest.importorskip("websockets")
    created = make_alarm("fire", location_description="消音复位链路")
    device, alarm_id = created["device"], created["report"]["alarm_id"]

    async def run() -> list[str]:
        types: list[str] = []
        async with websockets.connect(
            ws_url(ws_origin, ticket_of(chief)), open_timeout=5
        ) as ws:
            await ws.send(json.dumps({"action": "ping"}))
            await _await_frame(ws, "pong")

            await _api(chief, "POST", f"/alarms/{alarm_id}/silence")
            frame = await _await_frame(ws, "alarm_silenced", alarm_id=alarm_id)
            assert frame["data"]["silenced_by"] and set(frame["data"]) == {
                "alarm_id",
                "device_id",
                "org_id",
                "silenced_by",
                "silenced_at",
            }
            types.append("alarm_silenced")

            await _api(chief, "POST", f"/alarms/{alarm_id}/silence")
            await _assert_no_frame(ws, "alarm_silenced")
            types.append("alarm_silenced#idempotent")

            await _api(
                chief, "POST", f"/alarms/{alarm_id}/confirm", json={"confirm_result": "real"}
            )
            frame = await _await_frame(ws, "alarm_confirmed", alarm_id=alarm_id)
            assert frame["data"]["status"] == "confirmed"
            types.append("alarm_confirmed")

            await _report(client, device_key, device["device_code"], status="normal")
            frame = await _await_frame(ws, "device_status", device_id=device["id"])
            assert frame["data"]["status"] == "normal" and frame["data"]["old_status"] == "alarm"
            types.append("device_status")

            await _api(
                chief,
                "POST",
                f"/alarms/{alarm_id}/reset",
                json={"physical_restored": True, "remark": "端到端复位"},
            )
            frame = await _await_frame(ws, "alarm_reset", alarm_id=alarm_id)
            assert frame["data"]["status"] == "resolved"
            types.append("alarm_reset")
        return types

    assert asyncio.run(run()) == [
        "alarm_silenced",
        "alarm_silenced#idempotent",
        "alarm_confirmed",
        "device_status",
        "alarm_reset",
    ]


def test_reconnect_replays_missed_frames(chief, client, device_key, make_device, ws_origin):
    """断线期间的事件用 last_msg_id 增量补发；断点被裁剪则要求全量刷新（PRD 2.2）"""
    websockets = pytest.importorskip("websockets")
    first, second = make_device(), make_device()

    async def catch_up() -> list[str]:
        async with websockets.connect(
            ws_url(ws_origin, ticket_of(chief)), open_timeout=5
        ) as ws:
            await _report(client, device_key, first["device_code"], alarm_type="fire")
            frame = await _await_frame(ws, "alarm_new", device_id=first["id"])
            entry_id = frame["id"]

        # 连接关闭期间产生的事件只能靠 XRANGE 补发
        await _report(client, device_key, second["device_code"], alarm_type="pre_fire")
        async with websockets.connect(
            ws_url(ws_origin, ticket_of(chief), last_msg_id=entry_id), open_timeout=5
        ) as ws:
            replayed = await _await_frame(ws, "alarm_new", device_id=second["id"], timeout=6)
            assert _stream_ms(replayed["id"]) > _stream_ms(entry_id), "补发帧必须晚于断点"
            return [replayed["type"]]

    assert asyncio.run(catch_up()) == ["alarm_new"]

    async def overflow() -> str:
        async with websockets.connect(
            ws_url(ws_origin, ticket_of(chief), last_msg_id="1-1"), open_timeout=5
        ) as ws:
            frame = json.loads(await asyncio.wait_for(ws.recv(), 6))
            return frame["type"] + ":" + frame["data"]["reason"]

    assert asyncio.run(overflow()) == "resync_required:replay_overflow"


# ==================== 复位前置校验（FR-016.2 / OQ-2） ====================


def test_reset_requires_explicit_physical_evidence(chief, client, device_key, make_alarm):
    """未勾选、物理状态未恢复、误报无原因三种入口都必须被挡住"""
    created = make_alarm("fire")
    device, alarm_id = created["device"], created["report"]["alarm_id"]

    uncheck = chief.post(f"/alarms/{alarm_id}/reset", json={"physical_restored": False})
    assert uncheck.status_code == 400
    assert "物理状态" in uncheck.json()["message"]

    still_alarm = chief.post(f"/alarms/{alarm_id}/reset", json={"physical_restored": True})
    assert still_alarm.status_code == 400, "设备仍在报警且上报新鲜，不允许复位"
    assert "未恢复" in still_alarm.json()["message"]

    false_without_reason = chief.post(
        f"/alarms/{alarm_id}/confirm", json={"confirm_result": "false_alarm"}
    )
    assert false_without_reason.status_code == 422, "误报必填原因（模型级校验）"

    assert report(client, device_key, device["device_code"], status="normal").json()["code"] == 200
    detail = chief.unwrap("GET", f"/alarms/{alarm_id}")
    assert detail["status"] == "pending" and detail["device_code"] == device["device_code"]

    reset = chief.unwrap(
        "POST", f"/alarms/{alarm_id}/reset", json={"physical_restored": True, "remark": "已现场复位"}
    )
    assert reset["status"] == "resolved" and reset["reset_at"]

    again = chief.unwrap("POST", f"/alarms/{alarm_id}/reset", json={"physical_restored": True})
    assert again["status"] == "resolved", "重复复位幂等"
    assert chief.unwrap("GET", f"/devices/{device['id']}")["status"] == "normal"


def test_reports_require_device_key_and_reject_retired(client, chief, device_key, make_device):
    """上报端点用预共享凭据；退役设备不再接收上报（计划 5.5）"""
    device = make_device()

    anonymous = client.post(
        "/monitor/report", json={"device_code": device["device_code"], "status": "fault"}
    )
    assert anonymous.status_code == 401 and "DEVICE_REPORT_KEY" in anonymous.json()["message"]

    assert report(client, device_key, device["device_code"], status="fault").json()["code"] == 200
    assert chief.post(f"/devices/{device['id']}/retire", json={"reason": "端到端退役"}).status_code == 200

    retired = report(client, device_key, device["device_code"], status="normal")
    assert retired.status_code == 400 and "退役" in retired.json()["message"]

    unknown = report(client, device_key, "NOT-EXIST-CODE", status="fault")
    assert unknown.status_code == 200 and unknown.json()["code"] == 404


# ==================== 平面图与地图点位（FR-015） ====================


def test_map_image_lifecycle_and_static_access(chief, duty, base_url, floor_org, uploaded_map):
    """
    上传 → 元数据 → /static 可访问 → 删除。

    超宽图必须回写压缩后的宽高，否则前端按错误基准归一化会让点位整体错位。
    """
    assert uploaded_map["map_image_width"] == 2000 and uploaded_map["map_image_height"] == 1000
    assert uploaded_map["map_origin"] == "top_left"
    url = uploaded_map["map_image_url"]
    assert url.startswith("/static/maps/")

    meta = chief.unwrap("GET", "/monitor/map", params={"org_id": floor_org})
    assert meta["resolved_org_id"] == floor_org and meta["map_image_url"] == url

    image = httpx.get(api_origin(base_url) + url, timeout=30)
    assert image.status_code == 200, image.text
    assert image.headers["content-type"].startswith(PNG_MIME)
    assert Image.open(io.BytesIO(image.content)).size == (2000, 1000)

    removed = chief.delete(f"/organizations/{floor_org}/map-image")
    assert removed.json()["code"] == 200
    assert chief.unwrap("GET", "/monitor/map", params={"org_id": floor_org})["map_image_url"] is None
    assert httpx.get(api_origin(base_url) + url, timeout=30).status_code == 404, "文件必须一并删除"

    rejected = duty.post(
        f"/organizations/{floor_org}/map-image",
        files={"file": ("floor.png", io.BytesIO(png_bytes(10, 10)), PNG_MIME)},
    )
    assert rejected.status_code == 403 and "monitor:config" in rejected.json()["message"]


def test_map_image_rejects_non_image_and_unknown_org(chief, duty, floor_org):
    """魔数校验不信任扩展名与客户端 MIME；不存在的区域返回业务 404"""
    fake = chief.post(
        f"/organizations/{floor_org}/map-image",
        files={"file": ("floor.png", io.BytesIO(b"not an image at all"), PNG_MIME)},
    )
    assert fake.status_code == 200 and fake.json()["code"] == 400
    assert "类型" in fake.json()["message"]

    empty = chief.post(
        f"/organizations/{floor_org}/map-image",
        files={"file": ("floor.png", io.BytesIO(b""), PNG_MIME)},
    )
    assert empty.json()["code"] == 400

    assert duty.get("/monitor/map", params={"org_id": 9_999_999}).json()["code"] == 404


def test_map_devices_support_bbox_and_aggregation(chief, floor_org, make_device):
    """视口裁剪与超限网格聚合（FR-015 性能优化）；坐标取远离既有数据的高位区间"""
    coords = [(5000.0, 5000.0), (5050.0, 5000.0), (5100.0, 5000.0)]
    created = [make_device(map_x=x, map_y=y) for x, y in coords]

    everything = chief.unwrap("GET", "/monitor/map/devices", params={"org_id": floor_org})
    assert everything["total"] >= len(created)
    assert everything["aggregated"] is False
    by_code = {item["device_code"]: item for item in everything["items"]}
    for device in created:
        point = by_code[device["device_code"]]
        assert (point["map_x"], point["map_y"]) == (device["map_x"], device["map_y"])
        assert point["count"] == 1 and point["has_active_alarm"] is False

    window = chief.unwrap(
        "GET",
        "/monitor/map/devices",
        params={"org_id": floor_org, "bbox": "4990,4990,5060,5010"},
    )
    assert window["total"] == 2 and window["bbox"] == [4990.0, 4990.0, 5060.0, 5010.0]

    clustered = chief.unwrap(
        "GET", "/monitor/map/devices", params={"org_id": floor_org, "limit": 1}
    )
    assert clustered["aggregated"] is True and clustered["total"] == everything["total"]
    assert all(item["device_code"].startswith("cluster-") for item in clustered["items"])
    assert sum(item["count"] for item in clustered["items"]) == clustered["total"]

    assert chief.unwrap(
        "GET", "/monitor/map/devices", params={"org_id": floor_org, "bbox": "bad-bbox"}
    )["total"] == everything["total"], "非法 bbox 应忽略而不是报错"


def test_map_points_light_up_with_active_alarm(
    chief, client, device_key, make_device, floor_org
):
    """报警中的点位在地图接口上带 has_active_alarm，前端据此着色闪烁"""
    device = make_device(map_x=5200.0, map_y=5200.0)
    assert report(client, device_key, device["device_code"], alarm_type="fire").json()["code"] == 200

    window = chief.unwrap(
        "GET", "/monitor/map/devices", params={"org_id": floor_org, "bbox": "5190,5190,5210,5210"}
    )
    point = window["items"][0]
    assert (point["status"], point["has_active_alarm"], point["alarm_type"]) == (
        "alarm",
        True,
        "fire",
    )


# ==================== 历史轨迹（FR-018） ====================


def test_trajectory_window_points_and_export(chief, client, device_key, make_device):
    """默认近 7 天、按时间升序、状态中文化，xlsx/csv 双格式导出"""
    device = make_device()
    code = device["device_code"]
    report(client, device_key, code, alarm_type="fault")
    report(client, device_key, code, status="normal")
    report(client, device_key, code, alarm_type="fire")

    data = chief.unwrap("GET", f"/devices/{device['id']}/trajectory")
    assert data["device_code"] == code and data["total"] == 4
    assert (data["page"], data["page_size"]) == (1, 50)
    days = (datetime.fromisoformat(data["end"]) - datetime.fromisoformat(data["start"])).days
    assert days == 7, "缺省区间必须是近 7 天"

    times = [item["time"] for item in data["items"]]
    assert times == sorted(times), "轨迹必须按时间升序，否则前端阶梯图会倒着画"
    assert [i["new_status"] for i in data["items"]] == ["normal", "fault", "normal", "alarm"]
    assert data["items"][0]["old_status"] is None and data["items"][0]["status_label"] == "正常"
    assert [i["reason"] for i in data["items"]] == ["设备建档", "设备上报", "设备上报", "设备上报"]

    too_wide = chief.get(
        f"/devices/{device['id']}/trajectory",
        params={"start": "2020-01-01T00:00:00", "end": datetime.utcnow().isoformat()},
    ).json()
    assert too_wide["code"] == 400 and "90" in too_wide["message"]

    reversed_window = chief.get(
        f"/devices/{device['id']}/trajectory",
        params={"start": "2026-01-02T00:00:00", "end": "2026-01-01T00:00:00"},
    ).json()
    assert reversed_window["code"] == 400 and "早于" in reversed_window["message"]

    xlsx = chief.get(f"/devices/{device['id']}/trajectory/export")
    assert xlsx.status_code == 200
    assert "spreadsheetml.sheet" in xlsx.headers["content-type"]
    assert "attachment" in xlsx.headers["content-disposition"]
    assert xlsx.content[:2] == b"PK", "xlsx 必须是 zip 容器"

    csv_resp = chief.get(f"/devices/{device['id']}/trajectory/export", params={"format": "csv"})
    text = csv_resp.content.decode("utf-8-sig")
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert text.splitlines()[0] == "时间,原状态,新状态,变更原因,操作人"
    assert len(text.strip().splitlines()) == data["total"] + 1

    assert chief.get(
        f"/devices/{device['id']}/trajectory/export", params={"format": "pdf"}
    ).status_code == 422


# ==================== 权限矩阵（HTTP 层） ====================


def test_monitor_permission_matrix(maint, duty, chief, make_alarm):
    """维保看不到监控与报警；值班员可读可处置但不能配置平面图"""
    created = make_alarm("pre_fire")
    alarm_id = created["report"]["alarm_id"]

    for method, path in [
        ("GET", "/monitor/dashboard"),
        ("GET", "/monitor/alarms/recent"),
        ("GET", "/monitor/map/devices"),
        ("GET", "/alarms"),
    ]:
        resp = maint.request(method, path)
        assert resp.status_code == 403, f"{method} {path} -> {resp.text}"

    assert maint.post("/monitor/ws-ticket").status_code == 403
    assert maint.post(f"/alarms/{alarm_id}/silence").status_code == 403

    assert duty.unwrap("GET", "/monitor/dashboard")["total"] >= 1
    assert duty.unwrap("POST", "/monitor/ws-ticket")["ticket"]
    assert duty.unwrap("GET", "/alarms", params={"page_size": 100})["total"] >= 1
    assert duty.unwrap("POST", f"/alarms/{alarm_id}/silence")["id"] == alarm_id

    assert duty.post(
        "/organizations/1/map-image",
        files={"file": ("x.png", io.BytesIO(png_bytes(8, 8)), PNG_MIME)},
    ).status_code == 403

    assert chief.unwrap("GET", f"/alarms/{alarm_id}")["device_id"] == created["device"]["id"]


def test_duty_scope_cannot_reach_other_orgs(duty, chief, make_device):
    """值班员（dept）的地图定位与统计都受区域约束（OQ-1）"""
    device = make_device()
    meta = duty.unwrap("GET", "/monitor/map", params={"org_id": device["org_id"]})
    assert meta["org_id"] == device["org_id"] and meta["org_name"]
    # 越权/不存在都走统一响应体的 code=404，HTTP 仍是 200
    assert duty.get("/monitor/map", params={"org_id": 9_999_999}).json()["code"] == 404

    mine = duty.unwrap("GET", "/monitor/dashboard")["total"]
    assert mine == chief.unwrap("GET", "/monitor/dashboard")["total"], "种子树只有一个区域"


# ==================== Nginx 反向代理（浏览器实际使用的路径） ====================


@pytest.fixture(scope="session")
def public_url() -> str:
    """前端容器入口；未起 docker 或端口不通时跳过该组用例"""
    url = (os.getenv("E2E_PUBLIC_URL") or "http://localhost").rstrip("/")
    try:
        httpx.get(url + "/health", timeout=5)
    except httpx.HTTPError as exc:
        pytest.skip(f"前端入口不可达 {url}：{exc}")
    return url


def test_websocket_and_static_work_through_nginx(chief, public_url, floor_org):
    """
    `/ws/` 与 `/static/` 必须反代到后端。

    两者都曾被 SPA history 回退规则吞掉（返回 index.html 而不是升级连接/图片），
    浏览器里表现为「实时推送静默失效」，只能在这条路径上验证。
    """
    websockets = pytest.importorskip("websockets")
    rest = public_url + "/api/v1"
    login = httpx.post(
        rest + "/auth/login",
        json={"username": "admin", "password": "Admin1234"},
        timeout=30,
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    ticket = httpx.post(rest + "/monitor/ws-ticket", headers=headers, timeout=30).json()["data"]["ticket"]
    origin = public_url.replace("http://", "ws://").replace("https://", "wss://")

    async def ping_pong() -> str:
        async with websockets.connect(f"{origin}/ws/devices?ticket={ticket}", open_timeout=8) as ws:
            await ws.send(json.dumps({"action": "ping"}))
            return json.loads(await asyncio.wait_for(ws.recv(), 8))["type"]

    assert asyncio.run(ping_pong()) == "pong"

    upload = httpx.post(
        rest + f"/organizations/{floor_org}/map-image",
        headers=headers,
        files={"file": ("proxy.png", io.BytesIO(png_bytes(64, 32)), PNG_MIME)},
        timeout=30,
    )
    url = upload.json()["data"]["map_image_url"]
    try:
        served = httpx.get(public_url + url, timeout=30)
        assert served.status_code == 200, served.text
        assert served.headers["content-type"].startswith(PNG_MIME)
        assert Image.open(io.BytesIO(served.content)).size == (64, 32)
    finally:
        httpx.delete(rest + f"/organizations/{floor_org}/map-image", headers=headers, timeout=30)
