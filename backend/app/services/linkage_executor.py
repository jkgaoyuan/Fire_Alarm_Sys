"""
联动动作执行适配层（3.4-B3）
提供模拟执行器作为默认实现，为未来 MQTT/真实设备协议预留抽象接口

执行状态机：pending → sent → success / failed

执行策略：
- 模拟执行器：随机成功/失败（可配置失败率），模拟网络延迟
- 真实执行器：通过 MQTT 发送指令（待后续开发）
"""

import random
import asyncio
from typing import Tuple, Optional

# 默认失败率 10%（便于测试联动失败场景）
DEFAULT_FAILURE_RATE = 0.1


async def execute_action(
    action: dict, 
    log: 'AlarmLinkageLog',
    failure_rate: float = DEFAULT_FAILURE_RATE
) -> Tuple[str, str]:
    """
    执行单个联动动作（模拟）
    
    Args:
        action: 动作定义，包含 action_type, params 等
        log: 联动日志对象
        failure_rate: 失败率 [0, 1]，用于模拟随机失败
    
    Returns:
        (status, message) 元组
    
    Action Type 列表：
    - start_exhaust: 启动排烟
    - close_door: 关闭防火门
    - start_lighting: 启动应急照明
    - broadcast: 疏散广播
    """
    action_type = action.get("action_type", "unknown")
    params = action.get("params", {})
    
    # 模拟网络延迟（100~300ms）
    await asyncio.sleep(random.uniform(0.1, 0.3))
    
    # 延迟执行处理（首版不阻塞，仅记录提示）
    delay_seconds = log.delay_seconds if hasattr(log, "delay_seconds") else 0
    if delay_seconds > 0:
        return (
            "success",
            f"延迟 {delay_seconds} 秒执行（该功能后续支持）"
        )
    
    # 根据 action_type 生成不同结果
    if action_type == "start_exhaust":
        result = await _execute_start_exhaust(params, failure_rate)
    elif action_type == "close_door":
        result = await _execute_close_door(params, failure_rate)
    elif action_type == "start_lighting":
        result = await _execute_start_lighting(params, failure_rate)
    elif action_type == "broadcast":
        result = await _execute_broadcast(params, failure_rate)
    else:
        result = ("failed", f"未知的动作类型：{action_type}")
    
    return result


async def _execute_start_exhaust(
    params: dict, 
    failure_rate: float
) -> Tuple[str, str]:
    """启动排烟风机"""
    zone = params.get("zone", "未知区域")
    
    # 随机失败
    if random.random() < failure_rate:
        return ("failed", f"排烟风机启动失败：设备离线或故障（区域：{zone}）")
    
    return (
        "success",
        f"已成功启动排烟风机（区域：{zone}）"
    )


async def _execute_close_door(
    params: dict, 
    failure_rate: float
) -> Tuple[str, str]:
    """关闭防火门"""
    door_id = params.get("door_id", "未知门")
    
    if random.random() < failure_rate:
        return ("failed", f"防火门关闭失败：门体卡阻（门号：{door_id}）")
    
    return (
        "success",
        f"已成功关闭防火门（门号：{door_id}）"
    )


async def _execute_start_lighting(
    params: dict, 
    failure_rate: float
) -> Tuple[str, str]:
    """启动应急照明"""
    area = params.get("area", "未知区域")
    
    if random.random() < failure_rate:
        return ("failed", f"应急照明启动失败：电源异常（区域：{area}）")
    
    return (
        "success",
        f"已成功启动应急照明（区域：{area}）"
    )


async def _execute_broadcast(
    params: dict, 
    failure_rate: float
) -> Tuple[str, str]:
    """播放疏散广播"""
    zone = params.get("zone", "未知区域")
    
    if random.random() < failure_rate:
        return ("failed", f"疏散广播播放失败：音频系统离线（区域：{zone}）")
    
    return (
        "success",
        f"已成功播放疏散广播（区域：{zone}）"
    )


class LinkageExecutorInterface:
    """
    联动执行器抽象接口
    
    真实设备协议对接时，只需实现此接口的 execute_action 方法，
    无需修改联动引擎核心逻辑。
    """
    
    async def execute_action(
        self, 
        action: dict,
        log: 'AlarmLinkageLog'
    ) -> Tuple[str, str]:
        """
        执行联动动作
        
        Args:
            action: 动作定义
            log: 联动日志对象
        
        Returns:
            (status, message) 元组
        """
        raise NotImplementedError


# 默认使用模拟执行器
class MockExecutor(LinkageExecutorInterface):
    """模拟执行器（默认）"""
    
    async def execute_action(
        self, 
        action: dict,
        log: 'AlarmLinkageLog'
    ) -> Tuple[str, str]:
        return await execute_action(action, log)


# 单例
mock_executor = MockExecutor()
