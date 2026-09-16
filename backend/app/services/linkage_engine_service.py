"""
联动引擎核心服务（3.4-B2）
负责报警触发后的预案匹配与联动动作生成

流程：
1. 监听新报警（alarm_service.create_alarm 事务提交后调用）
2. 按 org_id + fire_type + device_type + alarm_type 匹配启用中的预案
3. 为每个预案的每个动作生成 AlarmLinkageLog（status=pending）
4. 调用 linkage_executor.execute() 模拟执行
5. 失败时生成次级告警（linkage_failed）并通过 WS 广播
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import get_redis_pool
from app.models.alarm import Alarm
from app.models.device import Device
from app.models.linkage import LinkagePlan, AlarmLinkageLog
from app.crud.linkage import linkage_plan_crud
from app.services.linkage_executor import execute_action
from app.services.alarm_service import raise_alarm, publish


class LinkageEngineService:
    """联动引擎服务"""
    
    @staticmethod
    async def on_alarm_created(db: AsyncSession, alarm: Alarm) -> None:
        """
        新报警触发后的自动联动处理
        
        1. 匹配预案
        2. 生成联动日志
        3. 执行动作
        4. 失败时生成次级告警
        """
        # 非火警/预火灾不触发自动联动
        if alarm.alarm_type not in ("fire", "pre_fire"):
            return
        
        # 查询所有启用的预案（后续在内存中过滤）
        all_plans = await linkage_plan_crud.get_multi_enabled(db, skip=0, limit=1000)
        
        matched_plans = []
        for plan in all_plans:
            if LinkageEngineService._matches_alarm(plan, alarm):
                matched_plans.append(plan)
        
        if not matched_plans:
            return
        
        # 并行生成并执行所有动作
        tasks = []
        for plan in matched_plans:
            for action in plan.actions:
                log = AlarmLinkageLog(
                    alarm_id=alarm.id,
                    plan_id=plan.id,
                    action_type=action["action_type"],
                    target_device_id=action.get("target_device_id"),
                    status="pending",
                    is_simulation=False,
                    delay_seconds=action.get("delay_seconds", 0),
                )
                db.add(log)
                await db.flush()  # 获取 id
                
                # 执行动作（模拟）
                tasks.append(
                    LinkageEngineService._execute_log(db, log, plan, action)
                )
        
        # 等待所有任务完成（最多 5 秒内）
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        await db.commit()
    
    @staticmethod
    def _matches_alarm(plan: LinkagePlan, alarm: Alarm) -> bool:
        """
        检查预案是否匹配当前报警
        
        匹配规则：
        1. 演练告警只触发「允许模拟测试」的预案
        2. org_id 精确匹配（或预案 org_id 为 null 表示全局）
        3. fire_type 匹配（或预案 fire_type 为 null 表示不限制）
        4. trigger_device_type_id 匹配（或为 null 表示不限制）
        5. trigger_alarm_type 匹配（或为 null 表示不限制）
        """
        # 开关必须在这里生效：否则关掉甲预案、去点乙预案的模拟，
        # 甲预案照样会被这条演练告警触发——那这个开关就只是装饰。
        if alarm.is_drill and not plan.is_simulation_allowed:
            return False

        # org_id 匹配
        if plan.org_id is not None and plan.org_id != alarm.org_id:
            return False
        
        # fire_type 匹配
        if plan.fire_type is not None and plan.fire_type != alarm.alarm_type:
            return False
        
        # device_type 匹配
        if plan.trigger_device_type_id is not None:
            if alarm.device_id is None:
                return False
            # TODO: 从 devices 表获取 device.type_id 进行对比
            # 这里简化处理：暂不校验
        
        # alarm_type 匹配
        if plan.trigger_alarm_type is not None:
            if plan.trigger_alarm_type != alarm.alarm_type:
                return False
        
        return True
    
    @staticmethod
    async def _execute_log(
        db: AsyncSession, 
        log: AlarmLinkageLog, 
        plan: LinkagePlan,
        action: dict
    ) -> None:
        """
        执行单个联动动作
        
        状态机：pending → sent → success/failed
        失败时生成次级告警
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            # 更新为 sent
            log.status = "sent"
            log.executed_at = datetime.now(timezone.utc)
            
            # 模拟执行
            result_status, result_message = await execute_action(action, log)
            
            # 更新结果
            log.status = result_status
            log.result_message = result_message
            log.completed_at = datetime.now(timezone.utc)
            
            if result_status == "success":
                # 成功：广播 linkage_executed
                await LinkageEngineService._broadcast_executed(log, plan, action)
            else:
                # 失败：生成次级告警
                secondary_alarm = await LinkageEngineService._create_secondary_alarm(
                    db, log, plan, action
                )
                # 广播 linkage_failed
                await LinkageEngineService._broadcast_failed(
                    log, plan, action, secondary_alarm
                )
                
        except Exception as e:
            # 异常处理：标记失败
            log.status = "failed"
            log.result_message = f"执行异常：{str(e)}"
            log.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
            # 生成次级告警
            secondary_alarm = await LinkageEngineService._create_secondary_alarm(
                db, log, plan, action, str(e)
            )
            await LinkageEngineService._broadcast_failed(log, plan, action, secondary_alarm)
    
    @staticmethod
    async def _safe_publish(event_type: str, data: dict) -> None:
        """
        推送联动事件。**任何推送侧故障都不得影响执行结果的判定。**

        原先是 `await settings.get_redis()` —— `Settings` 没有这个方法，必抛
        AttributeError；又因为调用点在 `_execute_log` 的 try 内，异常被捕获后
        把刚写好的 `status="success"` 覆盖成 `"failed"`。于是**每次成功执行都
        被记成失败**，且失败文案是引擎自己的内部错误。改用全仓库统一的
        `get_redis_pool()`，并在此处兜底（口径对齐 `alarm_service.publish`：
        推送失败绝不回滚已提交的消防业务数据）。
        """
        try:
            redis = await get_redis_pool()
            await publish(redis, event_type, data)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] 联动事件推送失败 {event_type}: {type(exc).__name__}: {exc}")

    @staticmethod
    async def _broadcast_executed(log: AlarmLinkageLog, plan: LinkagePlan, action: dict) -> None:
        """广播联动成功事件"""
        await LinkageEngineService._safe_publish(
            "linkage_executed",
            {
                "log_id": log.id,
                "alarm_id": log.alarm_id,
                "plan_id": plan.id,
                "plan_name": plan.plan_name,
                "action_type": log.action_type,
                "target_device_id": log.target_device_id,
                "status": "success",
            },
        )

    @staticmethod
    async def _broadcast_failed(
        log: AlarmLinkageLog,
        plan: LinkagePlan,
        action: dict,
        secondary_alarm: Optional[Alarm]
    ) -> None:
        """广播联动失败事件"""
        await LinkageEngineService._safe_publish(
            "linkage_failed",
            {
                "log_id": log.id,
                "alarm_id": log.alarm_id,
                "plan_id": plan.id,
                "plan_name": plan.plan_name,
                "action_type": log.action_type,
                "target_device_id": log.target_device_id,
                "status": "failed",
                "result_message": log.result_message,
                "secondary_alarm_id": secondary_alarm.id if secondary_alarm else None,
            },
        )

    @staticmethod
    async def _resolve_target_device(
        db: AsyncSession, log: AlarmLinkageLog
    ) -> Optional[Device]:
        """
        次级告警要挂在**真实设备**上：`raise_alarm` 的 `device` 必填，且
        `org_id` / `device_code` 都从它快照。优先用日志里的目标设备，
        没有就回退到触发这条联动的报警所属设备。
        """
        if log.target_device_id is not None:
            device = await db.get(Device, log.target_device_id)
            if device is not None:
                return device

        if log.alarm_id is not None:
            alarm = await db.get(Alarm, log.alarm_id)
            if alarm is not None and alarm.device_id is not None:
                return await db.get(Device, alarm.device_id)

        return None

    async def _create_secondary_alarm(
        db: AsyncSession,
        log: AlarmLinkageLog,
        plan: LinkagePlan,
        action: dict,
        extra_message: Optional[str] = None
    ) -> Optional[Alarm]:
        """
        生成联动失败的次级告警。

        `alarm_type` 用 `fault` 而不是 `linkage_failed`：后者不在
        `ALARM_TYPE_PROFILE` 里，`raise_alarm` 会直接 400。失败详情写进
        `location_description`，来源预案在文案里说清楚。

        原先这里传 `device=None` 且用非法类型，两个错误都被裸 `except` 吞掉，
        于是「联动失败产生次级告警」从未生效过、也不留任何痕迹。
        找不到设备时仍返回 None，但会打印告警——静默失败正是这个函数
        烂了这么久没人发现的原因。
        """
        device = await LinkageEngineService._resolve_target_device(db, log)
        if device is None:
            print(
                f"[WARN] 联动失败但找不到目标设备，无法生成次级告警："
                f"log_id={log.id} plan_id={plan.id} alarm_id={log.alarm_id}"
            )
            return None

        message_parts = [
            f"联动预案 '{plan.plan_name}' 执行失败",
            f"动作类型：{log.action_type}",
        ]
        if log.result_message:
            message_parts.append(f"失败原因：{log.result_message}")
        if extra_message:
            message_parts.append(extra_message)

        try:
            alarm, _ = await raise_alarm(
                db,
                device,
                "fault",
                is_drill=False,
                location_description="; ".join(message_parts),
            )
            return alarm
        except Exception as exc:  # noqa: BLE001
            print(
                f"[WARN] 生成次级告警失败：{type(exc).__name__}: {exc} "
                f"(log_id={log.id} plan_id={plan.id})"
            )
            return None


# 单例
linkage_engine = LinkageEngineService()
