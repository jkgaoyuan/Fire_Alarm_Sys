#!/usr/bin/env python3
"""
3.3 性能与容量基准脚本（P1-008）
--------------------------------
在本地 PostgreSQL + Redis 环境下执行两项验收硬指标：
1. 模拟器 100 条/s 上报下的 WS 推送延迟 P95/P99；
2. 1000 / 5000 点位下 /monitor/map/devices 首屏响应时间。

运行前确保后端服务已启动（默认 http://localhost:8000）。
    cd backend
    python scripts/benchmark_3_3.py
"""

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import websockets

DEVICE_REPORT_KEY = "benchmark-device-key"
os.environ.setdefault("DEVICE_REPORT_KEY", DEVICE_REPORT_KEY)

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models.device import Device
from app.models.device_type import DeviceType
from app.models.organization import Organization
from app.models.user import Role, User
from app.db.redis import get_redis_pool
from app.schemas.alarm import DeviceReportRequest
from app.services.device_report_service import handle_device_report

settings = get_settings()
engine = create_async_engine(settings.database_url_async)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/devices"
BENCHMARK_USERNAME = "benchmark_admin"
BENCHMARK_PASSWORD = "Bench1234"


# ==================== 辅助函数 ====================


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_benchmark_user(db: AsyncSession, org_id: int) -> User:
    """创建/复用压测专用 admin 用户（data_scope=all，chief 角色）"""
    user = (await db.execute(select(User).where(User.username == BENCHMARK_USERNAME))).scalar_one_or_none()
    if user:
        return user

    role = (await db.execute(select(Role).where(Role.role_code == "chief"))).scalar_one()
    user = User(
        username=BENCHMARK_USERNAME,
        password_hash=get_password_hash(BENCHMARK_PASSWORD),
        real_name="压测管理员",
        status="active",
        data_scope="all",
        org_id=org_id,
    )
    user.roles.append(role)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_login_token() -> str:
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/login", json={
            "username": BENCHMARK_USERNAME,
            "password": BENCHMARK_PASSWORD,
        })
        if r.status_code != 200:
            raise RuntimeError(f"登录失败: {r.status_code} {r.text}")
        return r.json()["data"]["access_token"]


async def get_ws_ticket(token: str) -> str:
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/monitor/ws-ticket", headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 200:
            raise RuntimeError(f"获取 WS Ticket 失败: {r.status_code} {r.text}")
        return r.json()["data"]["ticket"]


# ==================== 设备种子 ====================


async def seed_devices(count: int, org_id: int) -> list[int]:
    """批量创建带坐标的压测设备，返回 device_id 列表"""
    async with AsyncSessionLocal() as db:
        dtype = (await db.execute(select(DeviceType).order_by(DeviceType.id).limit(1))).scalar_one()
        # 先清旧压测数据
        await db.execute(delete(Device).where(Device.device_code.like("BENCH-%")))
        await db.commit()

        devices = []
        for i in range(count):
            devices.append({
                "device_code": f"BENCH-{i:06d}",
                "device_name": f"压测设备 {i}",
                "type_id": dtype.id,
                "org_id": org_id,
                "status": "normal",
                "map_x": round(random.uniform(0, 2000), 2),
                "map_y": round(random.uniform(0, 1500), 2),
                "attributes": json.dumps({}),
            })

        # 分批插入避免单条 SQL 过大
        batch_size = 500
        for i in range(0, len(devices), batch_size):
            batch = devices[i:i + batch_size]
            await db.execute(text(
                """
                INSERT INTO devices (device_code, device_name, type_id, org_id, status, map_x, map_y, attributes, is_deleted, created_at, updated_at)
                VALUES (:device_code, :device_name, :type_id, :org_id, :status, :map_x, :map_y, :attributes, false, NOW(), NOW())
                """
            ), batch)
            await db.commit()

        rows = (await db.execute(select(Device.id).where(Device.device_code.like("BENCH-%")).order_by(Device.id))).all()
        ids = [row[0] for row in rows]
        print(f"[seed] 已创建 {len(ids)} 台压测设备")
        return ids


async def cleanup_devices() -> None:
    async with AsyncSessionLocal() as db:
        # 先清理引用压测设备的外键记录（alarms / device_status_logs）
        bench_device_ids = select(Device.id).where(Device.device_code.like("BENCH-%")).scalar_subquery()
        from app.models.alarm import Alarm
        from app.models.device import DeviceStatusLog
        await db.execute(delete(Alarm).where(Alarm.device_id.in_(bench_device_ids)))
        await db.execute(delete(DeviceStatusLog).where(DeviceStatusLog.device_id.in_(bench_device_ids)))
        await db.execute(delete(Device).where(Device.device_code.like("BENCH-%")))
        await db.commit()
        print("[seed] 已清理压测设备")


# ==================== 地图视口压测 ====================


async def benchmark_map_viewport(token: str, counts: list[int], org_id: int) -> dict:
    """对指定设备量级分别请求 /monitor/map/devices 并记录耗时"""
    results = {}
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        for count in counts:
            device_ids = await seed_devices(count, org_id)
            # 预热一次
            await client.get(
                "/api/v1/monitor/map/devices?bbox=0,0,2000,1500&limit=500",
                headers={"Authorization": f"Bearer {token}"},
            )
            # 正式采样 5 次
            times = []
            for _ in range(5):
                t0 = time.perf_counter()
                r = await client.get(
                    "/api/v1/monitor/map/devices?bbox=0,0,2000,1500&limit=500",
                    headers={"Authorization": f"Bearer {token}"},
                )
                t1 = time.perf_counter()
                if r.status_code != 200:
                    raise RuntimeError(f"map/devices 请求失败: {r.status_code} {r.text}")
                data = r.json()["data"]
                times.append((t1 - t0) * 1000)

            results[count] = {
                "p50": round(statistics.median(times), 3),
                "p95": round(sorted(times)[int(len(times) * 0.95)], 3),
                "max": round(max(times), 3),
                "avg": round(statistics.mean(times), 3),
                "total": data.get("total"),
                "aggregated": data.get("aggregated"),
            }
            print(f"[map] 设备 {count}: {results[count]}")
            await cleanup_devices()
    return results


# ==================== WS 推送延迟压测 ====================


async def collect_ws_frames(websocket, duration: float, latencies: list, received: dict):
    """在指定时间内持续读取 WS 帧并计算延迟"""
    deadline = time.time() + duration
    while time.time() < deadline:
        try:
            msg = await asyncio.wait_for(websocket.recv(), timeout=0.5)
            recv_ts = time.time()
            try:
                frame = json.loads(msg)
                data = frame.get("data") or {}
                reported_at = data.get("reported_at")
                if reported_at:
                    # device_status 帧携带 reported_at，与本地收到时间比较
                    srv_ts = datetime.fromisoformat(reported_at).timestamp()
                    latencies.append((recv_ts - srv_ts) * 1000)
            except Exception:
                pass
            received["count"] += 1
        except asyncio.TimeoutError:
            continue


async def benchmark_ws_latency(token: str, rate: float, duration: float) -> dict:
    """
    启动 WS 连接，同时以 rate 条/s 驱动模拟器上报，测量 WS 帧接收延迟。
    延迟定义为：客户端收到帧的本地时间 - 帧内服务端 ts 转成的本地时间。

    为避免 Docker 内后端进程的 DEVICE_REPORT_KEY 与本脚本不一致，
    直接调用 handle_device_report 服务函数写 Redis Stream，由容器内 broadcaster 消费并推送。
    """
    ticket = await get_ws_ticket(token)
    latencies_ms = []
    received = {"count": 0}

    # 需要至少一台设备
    async with AsyncSessionLocal() as db:
        org = (await db.execute(select(Organization).order_by(Organization.id).limit(1))).scalar_one()
        device_ids = await seed_devices(1, org.id)
        device_id = device_ids[0]

    redis = None
    async with websockets.connect(f"{WS_URL}?ticket={ticket}") as websocket:
        # 发送 ping 确认连接可用
        await websocket.send(json.dumps({"action": "ping"}))
        try:
            await asyncio.wait_for(websocket.recv(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

        # 启动收集协程
        collector = asyncio.create_task(collect_ws_frames(websocket, duration + 2, latencies_ms, received))

        # 通过服务函数直接上报（与 HTTP 端点入库/广播路径完全一致）
        redis = await get_redis_pool()
        sent = 0
        interval = 1 / rate
        start = time.perf_counter()
        while time.perf_counter() - start < duration:
            payload = DeviceReportRequest(
                device_id=device_id,
                status=random.choice(["normal", "alarm", "fault", "shield"]),
                alarm_type=random.choice(["fire", "pre_fire", "fault", "shield"]),
                location_description="压测位置",
                is_drill=True,
                reported_at=now_utc(),
            )
            try:
                async with AsyncSessionLocal() as report_db:
                    await handle_device_report(report_db, redis, payload)
                sent += 1
            except Exception as exc:
                print(f"[ws] 上报异常: {exc}")
            await asyncio.sleep(interval)

        await collector

    if redis:
        await redis.aclose()
    await cleanup_devices()

    if not latencies_ms:
        return {"sent": sent, "received": received["count"], "p95": None, "p99": None}

    sorted_ms = sorted(latencies_ms)
    return {
        "sent": sent,
        "received": received["count"],
        "p95": round(sorted_ms[int(len(sorted_ms) * 0.95)], 3),
        "p99": round(sorted_ms[int(len(sorted_ms) * 0.99)], 3),
        "max": round(max(sorted_ms), 3),
        "avg": round(statistics.mean(sorted_ms), 3),
    }


# ==================== 入口 ====================


async def main() -> int:
    parser = argparse.ArgumentParser(description="3.3 性能与容量基准（P1-008）")
    parser.add_argument("--map-counts", type=int, nargs="+", default=[1000, 5000])
    parser.add_argument("--ws-rate", type=float, default=100.0)
    parser.add_argument("--ws-duration", type=float, default=60.0)
    parser.add_argument("--skip-ws", action="store_true", help="跳过 WS 延迟测试")
    parser.add_argument("--skip-map", action="store_true", help="跳过地图视口测试")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        org = (await db.execute(select(Organization).order_by(Organization.id).limit(1))).scalar_one()
        await ensure_benchmark_user(db, org.id)

    token = await get_login_token()
    print(f"[auth] 已获取 token，长度 {len(token)}")

    report = {"timestamp": now_utc().isoformat(), "base_url": BASE_URL}

    if not args.skip_map:
        print("\n[benchmark] 开始地图视口压测 ...")
        report["map_viewport"] = await benchmark_map_viewport(token, args.map_counts, org.id)

    if not args.skip_ws:
        print("\n[benchmark] 开始 WS 推送延迟压测 ...")
        print(f"[ws] 速率 {args.ws_rate} 条/s，持续 {args.ws_duration}s")
        report["ws_latency"] = await benchmark_ws_latency(token, args.ws_rate, args.ws_duration)
        print(f"[ws] 结果: {report['ws_latency']}")

    print("\n========== 3.3 性能基准报告 ==========")
    print(f"时间: {report['timestamp']}")
    if "map_viewport" in report:
        print("\n地图视口首屏延迟 (ms):")
        for count, metrics in report["map_viewport"].items():
            print(f"  设备 {count:>5}: P50={metrics['p50']} P95={metrics['p95']} MAX={metrics['max']} AVG={metrics['avg']} aggregated={metrics['aggregated']}")
    if "ws_latency" in report:
        m = report["ws_latency"]
        print(f"\nWS 推送延迟 (ms, 相对时戳): sent={m['sent']} received={m['received']} P95={m['p95']} P99={m['p99']} MAX={m['max']} AVG={m['avg']}")
    print("======================================")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
