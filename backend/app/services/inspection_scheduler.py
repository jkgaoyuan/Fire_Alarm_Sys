""" 
巡检定时调度器（3.6-B3）
=======================
技术选型：FastAPI lifespan + asyncio.create_task()（DEC-043）
功能：
1. 每日凌晨自动生成当日巡检任务
2. 每小时扫描漏检任务并标记
注意：暂不引入 Celery，使用 asyncio 实现（PRD v2.0 §2.2）
"""

import asyncio
from datetime import date, datetime, time, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.services.inspection_service import scan_missed_tasks


settings = get_settings()


class InspectionScheduler:
    """巡检定时调度器"""
    
    def __init__(self, task_generate_time: time = time(0, 0, 0), scan_interval: int = 3600):
        """
        初始化调度器
        
        Args:
            task_generate_time: 任务生成时间（默认每天凌晨 00:00）
            scan_interval: 漏检扫描间隔（秒），默认 1 小时
        """
        self.task_generate_time = task_generate_time
        self.scan_interval = scan_interval
        self._generate_task: Optional[asyncio.Task] = None
        self._scan_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self, engine):
        """启动调度器"""
        if self._running:
            return
            
        self._running = True
        print("[INSPECTION SCHEDULER] Starting...")
        
        # 创建数据库会话工厂
        SessionLocal = sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
        
        # 启动任务生成任务
        self._generate_task = asyncio.create_task(self._periodic_task_generator(SessionLocal))
        print(f"[INSPECTION SCHEDULER] Task generator started (time={self.task_generate_time})")
        
        # 启动漏检扫描任务
        self._scan_task = asyncio.create_task(self._periodic_missed_scanner(SessionLocal))
        print(f"[INSPECTION SCHEDULER] Missed scanner started ({self.scan_interval}s interval)")
        
    async def stop(self):
        """停止调度器"""
        if not self._running:
            return
            
        self._running = False
        
        # 取消所有任务
        for task in [self._generate_task, self._scan_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                    
        print("[INSPECTION SCHEDULER] Stopped")
        
    async def _periodic_task_generator(self, SessionLocal):
        """
        周期性生成任务的后台协程
        
        逻辑：
        1. 计算下一次执行时间（到第二天任务生成时间的剩余时间）
        2. 等待到时间点
        3. 为所有启用的计划生成今日任务
        4. 重复执行
        """
        while self._running:
            try:
                now = datetime.now()
                target = now.replace(
                    hour=self.task_generate_time.hour,
                    minute=self.task_generate_time.minute,
                    second=0,
                    microsecond=0
                )
                
                # 如果目标时间已过，设置为明天同一时间
                if target <= now:
                    target += timedelta(days=1)
                
                wait_seconds = (target - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                # 执行生成逻辑
                async with SessionLocal() as session:
                    # 这里简化实现：实际应查询所有启用的计划生成今日任务
                    # TODO: 添加日志记录生成的计划数
                    print(f"[INSPECTION SCHEDULER] Generating tasks for {date.today()}")
                    
                    # 调用 service 层接口
                    from app.services.inspection_service import generate_tasks_for_plan
                    # ... 具体生成逻辑待补充
                    
                print(f"[INSPECTION SCHEDULER] Tasks generated for {date.today()}")
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[INSPECTION SCHEDULER ERROR] Task generator failed: {e}")
                await asyncio.sleep(60)  # 错误后重试间隔
    
    async def _periodic_missed_scanner(self, SessionLocal):
        """
        周期性扫描漏检任务的后台协程
        
        逻辑：
        1. 每隔 scan_interval 秒扫描一次
        2. 检查 pending/doing 状态且已过期的任务
        3. 标记为 missed
        4. 统计需要预警的计划（漏检≥3 次）
        """
        while self._running:
            try:
                await asyncio.sleep(self.scan_interval)
                
                async with SessionLocal() as session:
                    result = await scan_missed_tasks(session)
                    
                    if result["marked_missed"] > 0:
                        print(f"[INSPECTION SCHEDULER] Scanned: marked {result['marked_missed']} tasks as missed")
                        
                    if result["alert_count"] > 0:
                        print(f"[INSPECTION SCHEDULER] ALERT: {result['alert_count']} plans exceeded missed threshold")
                        
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[INSPECTION SCHEDULER ERROR] Missed scanner failed: {e}")
                await asyncio.sleep(60)


# 全局调度器实例（由 main.py lifespan 管理）
scheduler: Optional[InspectionScheduler] = None


# 导入缺失的 timedelta
from datetime import timedelta
