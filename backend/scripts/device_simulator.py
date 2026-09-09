#!/usr/bin/env python3
"""
设备上报模拟器
---------------
用途：3.3 B-19 —— 在没有真实 MQTT 网关的情况下驱动报警生成、WebSocket 推送与地图联动，
供演示、验收与压测使用。进程内直调 B-13 服务函数（`handle_device_report`），
因此与 HTTP 上报走完全相同的入库、去重、状态留痕与 Stream 广播路径。

运行方式（需 .env 指向可用的 PostgreSQL 与 Redis）：
    cd E:/pycharm/AI_PROJECT_CODE/Fire_Alarm_Sys/backend
    python scripts/device_simulator.py --rate 5 --scenario random --duration 60
    python scripts/device_simulator.py --scenario fire-alarm --device-code FS-001

容器内运行：
    docker exec -it fire_alarm_backend python scripts/device_simulator.py --rate 20

参数：
    --rate N        每秒上报条数（默认 1）
    --scenario S    random（默认，按权重随机）/ fire-alarm（固定火警脚本）
    --duration S    运行秒数，0 表示一直运行（默认 0）
    --limit N       仅使用设备档案中的前 N 台（默认全部）
    --device-code   仅模拟指定编码的设备（可重复）
    --drill         上报标记为演练（is_drill=true，不计入待处理火警）
"""

import argparse
import asyncio
import random
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.redis import close_redis_pool, get_redis_pool  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.schemas.alarm import DeviceReportRequest  # noqa: E402
from app.services.device_report_service import handle_device_report  # noqa: E402

# random 场景的状态权重：多数设备保持正常，少量抖动才能观察去重与收敛
STATUS_WEIGHTS = [
    ("normal", 60),
    ("alarm", 15),
    ("fault", 12),
    ("shield", 5),
    ("offline", 8),
]

STATUS_ALARM_TYPE = {
    "alarm": ("fire", "pre_fire"),
    "fault": ("fault",),
    "shield": ("shield",),
}

LOCATION_SAMPLES = [
    "1F 大厅东侧",
    "3F 走廊烟感",
    "地下车库 B2-07",
    "5F 弱电井",
    "屋顶消防水箱间",
]


def _pick_status() -> str:
    statuses = [name for name, _ in STATUS_WEIGHTS]
    weights = [weight for _, weight in STATUS_WEIGHTS]
    return random.choices(statuses, weights=weights, k=1)[0]


def random_report(device: Device, *, is_drill: bool) -> DeviceReportRequest:
    status = _pick_status()
    alarm_types = STATUS_ALARM_TYPE.get(status)
    return DeviceReportRequest(
        device_id=device.id,
        status=status,
        alarm_type=random.choice(alarm_types) if alarm_types else None,
        location_description=random.choice(LOCATION_SAMPLES) if alarm_types else None,
        is_drill=is_drill,
        reported_at=datetime.utcnow(),
    )


def fire_alarm_report(device: Device, step: int, *, is_drill: bool) -> DeviceReportRequest:
    """
    固定脚本（演示 FR-016 全链路）：
    0 正常 → 1 预警 → 2 火警 → 3 火警复现（验证同类去重）→ 4 恢复正常 → 循环
    """
    phase = step % 5
    if phase == 0:
        status, alarm_type = "normal", None
    elif phase == 1:
        status, alarm_type = "alarm", "pre_fire"
    elif phase in (2, 3):
        status, alarm_type = "alarm", "fire"
    else:
        status, alarm_type = "normal", None
    return DeviceReportRequest(
        device_id=device.id,
        status=status,
        alarm_type=alarm_type,
        location_description="消防控制室演练脚本" if alarm_type else None,
        is_drill=is_drill,
        reported_at=datetime.utcnow(),
    )


async def load_devices(
    db: AsyncSession, codes: list[str] | None, limit: int | None
) -> list[Device]:
    query = select(Device).where(Device.is_deleted.is_(False), Device.status != "retired")
    if codes:
        query = query.where(Device.device_code.in_(codes))
    rows = (await db.execute(query.order_by(Device.id))).scalars().all()
    devices = list(rows)
    return devices[:limit] if limit else devices


async def run(args: argparse.Namespace) -> int:
    redis = await get_redis_pool()
    sent = alarms = skipped = 0
    started = datetime.utcnow()

    async with AsyncSessionLocal() as db:
        devices = await load_devices(db, args.device_code, args.limit)
        if not devices:
            print("[ simulator ] 设备档案为空，请先在 3.2 中建档或放宽筛选条件")
            return 1
        print(
            f"[ simulator ] 设备 {len(devices)} 台 / 速率 {args.rate} 条/s / 场景 {args.scenario}"
            f"{' / 演练标记' if args.drill else ''}，Ctrl+C 退出"
        )

        interval = 1 / args.rate if args.rate > 0 else 0
        step = 0
        while True:
            if args.duration and (datetime.utcnow() - started).total_seconds() >= args.duration:
                break
            device = random.choice(devices) if args.scenario == "random" else devices[step % len(devices)]
            payload = (
                random_report(device, is_drill=args.drill)
                if args.scenario == "random"
                else fire_alarm_report(device, step, is_drill=args.drill)
            )
            try:
                result = await handle_device_report(db, redis, payload)
                sent += 1
                if result["alarm_created"]:
                    alarms += 1
                    print(
                        f"  +{result['device_code']} 新报警 id={result['alarm_id']} "
                        f"{result['old_status']}→{result['status']}"
                    )
                elif result["status_changed"]:
                    print(f"  ~{result['device_code']} {result['old_status']}→{result['status']}")
            except Exception as exc:  # noqa: BLE001 - 模拟器需要继续跑完脚本而不是中断
                await db.rollback()
                skipped += 1
                print(f"  !{payload.device_id} 上报被拒: {exc}")
            step += 1
            if interval:
                await asyncio.sleep(interval)

    await close_redis_pool()
    print(f"[ simulator ] 完成：上报 {sent} 条 / 新建报警 {alarms} 条 / 拒绝 {skipped} 条")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="消防设备上报模拟器（3.3 B-19）")
    parser.add_argument("--rate", type=float, default=1.0, help="每秒上报条数")
    parser.add_argument(
        "--scenario", choices=("random", "fire-alarm"), default="random"
    )
    parser.add_argument("--duration", type=int, default=0, help="运行秒数，0 为不限")
    parser.add_argument("--limit", type=int, default=None, help="最多使用前 N 台设备")
    parser.add_argument(
        "--device-code", action="append", default=None, help="仅模拟指定设备编码，可重复"
    )
    parser.add_argument("--drill", action="store_true", help="标记为演练上报（is_drill）")
    args = parser.parse_args()
    if args.rate <= 0:
        parser.error("--rate 必须大于 0（0 会变成不限速灌库）")

    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\n[ simulator ] 已手动停止")
        return 0


if __name__ == "__main__":
    sys.exit(main())
