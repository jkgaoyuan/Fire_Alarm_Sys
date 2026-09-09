#!/usr/bin/env python3
"""
设备档案分页性能基准脚本（P0-016）
----------------------------------
验证 GET /api/v1/devices 在 1000+ 设备下的分页响应是否流畅。

运行前确保后端服务已启动（默认 http://localhost:8000）。
    cd backend
    python scripts/benchmark_device_pagination.py
"""

import argparse
import asyncio
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

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

settings = get_settings()
engine = create_async_engine(settings.database_url_async)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

BASE_URL = "http://localhost:8000"
BENCHMARK_USERNAME = "benchmark_admin"
BENCHMARK_PASSWORD = "Bench1234"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_benchmark_user(db: AsyncSession, org_id: int) -> User:
    """创建/复用压测专用 admin 用户（data_scope=all，chief 角色）"""
    user = (
        await db.execute(select(User).where(User.username == BENCHMARK_USERNAME))
    ).scalar_one_or_none()
    if user:
        return user

    role = (
        await db.execute(select(Role).where(Role.role_code == "chief"))
    ).scalar_one()
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
        r = await client.post(
            "/api/v1/auth/login",
            json={"username": BENCHMARK_USERNAME, "password": BENCHMARK_PASSWORD},
        )
        if r.status_code != 200:
            raise RuntimeError(f"登录失败: {r.status_code} {r.text}")
        return r.json()["data"]["access_token"]


async def bulk_insert_devices(db: AsyncSession, org_id: int, type_id: int, count: int) -> list[int]:
    """批量插入压测设备，返回设备 id 列表"""
    ids: list[int] = []
    batch_size = 200
    for start in range(0, count, batch_size):
        batch_end = min(start + batch_size, count)
        devices = []
        for i in range(start, batch_end):
            code = f"BENCH-PG-{i:05d}"
            devices.append(
                Device(
                    device_code=code,
                    device_name=f"压测设备{i:05d}",
                    type_id=type_id,
                    org_id=org_id,
                    manufacturer="Benchmark",
                    model=f"BM-{i % 10}",
                    brand="BenchBrand",
                    status="normal",
                    install_date=now_utc().date(),
                    map_x=float(random.randint(0, 1000)),
                    map_y=float(random.randint(0, 1000)),
                    attributes={"bench": True},
                    is_deleted=False,
                )
            )
        db.add_all(devices)
        await db.flush()
        ids.extend([d.id for d in devices])
    await db.commit()
    return ids


async def cleanup_devices(db: AsyncSession, ids: list[int]) -> None:
    """清理压测设备"""
    if not ids:
        return
    await db.execute(delete(Device).where(Device.id.in_(ids)))
    await db.commit()


async def measure_page_latency(
    token: str, page: int, page_size: int = 20, runs: int = 50
) -> dict:
    """对指定页码执行 runs 次请求，返回延迟统计"""
    latencies: list[float] = []
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        for _ in range(runs):
            start = time.time()
            r = await client.get(
                "/api/v1/devices",
                params={"page": page, "page_size": page_size},
                headers=headers,
            )
            elapsed = time.time() - start
            if r.status_code != 200:
                raise RuntimeError(f"第 {page} 页请求失败: {r.status_code} {r.text[:200]}")
            latencies.append(elapsed)

    latencies.sort()
    n = len(latencies)
    return {
        "runs": n,
        "min": latencies[0],
        "p50": latencies[n // 2],
        "p95": latencies[int(n * 0.95)] if n > 1 else latencies[0],
        "p99": latencies[int(n * 0.99)] if n > 1 else latencies[0],
        "max": latencies[-1],
        "avg": statistics.mean(latencies),
    }


async def run_benchmark(device_count: int = 1200, runs: int = 50) -> dict:
    """执行完整基准测试"""
    async with AsyncSessionLocal() as db:
        # 获取或创建根区域与设备类型
        org = (
            await db.execute(select(Organization).where(Organization.parent_id.is_(None)))
        ).scalar_one_or_none()
        if org is None:
            raise RuntimeError("未找到根区域，请先运行 init_data.py")

        device_type = (
            await db.execute(select(DeviceType).limit(1))
        ).scalar_one_or_none()
        if device_type is None:
            raise RuntimeError("未找到设备类型，请先运行 init_data.py")

        await ensure_benchmark_user(db, org.id)

        print(f"插入 {device_count} 台压测设备...")
        ids = await bulk_insert_devices(db, org.id, device_type.id, device_count)
        print(f"插入完成，设备 id 范围: {ids[0]} ~ {ids[-1]}")

        try:
            token = await get_login_token()
            print(f"登录成功，开始分页压测（runs={runs}）...\n")

            results = {}
            for page in [1, 10, 50]:
                if (page - 1) * 20 >= device_count:
                    continue
                stats = await measure_page_latency(token, page, runs=runs)
                results[f"page_{page}"] = stats
                print(
                    f"第 {page:3d} 页: runs={stats['runs']:3d} "
                    f"p50={stats['p50']*1000:7.1f}ms  "
                    f"p95={stats['p95']*1000:7.1f}ms  "
                    f"p99={stats['p99']*1000:7.1f}ms  "
                    f"max={stats['max']*1000:7.1f}ms  "
                    f"avg={stats['avg']*1000:7.1f}ms"
                )

            print("\n分页压测完成。")
            return results

        finally:
            print("清理压测设备...")
            await cleanup_devices(db, ids)
            print("清理完成。")


def main():
    parser = argparse.ArgumentParser(description="设备档案分页性能基准")
    parser.add_argument("--count", type=int, default=1200, help="压测设备数量（默认 1200）")
    parser.add_argument("--runs", type=int, default=50, help="每页请求次数（默认 50）")
    args = parser.parse_args()

    asyncio.run(run_benchmark(device_count=args.count, runs=args.runs))


if __name__ == "__main__":
    main()
