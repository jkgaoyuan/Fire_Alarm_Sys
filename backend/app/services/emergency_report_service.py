"""
事件报告生成服务（3.5 B6）
- 支持同步 PDF 导出（≤100 页）
- 超大报告返回 202 提示走异步导出（3.9 模块）
"""

from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.schemas.emergency import EventReportRequest
from app.services.emergency_service import timeline_payload


def generate_report_html(
    event: Dict[str, Any],
    alarm: Dict[str, Any],
    timelines: list,
    include_photos: bool = True
) -> str:
    """
    生成 HTML 格式的事件报告
    
    Args:
        event: 事件数据
        alarm: 报警数据
        timelines: 时间轴节点列表
        include_photos: 是否包含照片
        
    Returns:
        HTML 字符串
    """
    html_parts = []
    
    # 头部样式
    html_parts.append("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>应急处置报告</title>
    <style>
        body { font-family: "Microsoft YaHei", Arial; margin: 40px; line-height: 1.6; }
        .header { text-align: center; border-bottom: 2px solid #d32f2f; padding-bottom: 10px; margin-bottom: 30px; }
        .section { margin-bottom: 20px; }
        .section-title { font-size: 18px; font-weight: bold; color: #d32f2f; margin-top: 20px; margin-bottom: 10px; }
        .info-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        .info-table td { padding: 8px; border: 1px solid #ddd; }
        .label { width: 120px; background-color: #f5f5f5; font-weight: bold; }
        .timeline { margin-top: 20px; }
        .timeline-item { display: flex; margin-bottom: 10px; align-items: flex-start; }
        .timeline-time { min-width: 160px; color: #666; }
        .timeline-content { flex: 1; background-color: #fff3cd; padding: 10px; border-radius: 4px; margin-left: 10px; }
        .footer { margin-top: 40px; text-align: center; font-size: 12px; color: #999; border-top: 1px solid #eee; padding-top: 10px; }
    </style>
</head>
<body>""")
    
    # 标题
    html_parts.append(f"<div class='header'><h1>应急处置报告</h1><p>编号：{event.get('event_no', 'N/A')}</p></div>")
    
    # 事件基本信息
    html_parts.append("<div class='section'>")
    html_parts.append("<div class='section-title'>一、事件基本信息</div>")
    html_parts.append("<table class='info-table'>")
    events = [
        ("事件编号", event.get("event_no", "N/A")),
        ("事件状态", event.get("status", "N/A")),
        ("开始时间", datetime.fromisoformat(str(event.get("started_at"))).strftime("%Y-%m-%d %H:%M:%S") if event.get("started_at") else "N/A"),
        ("完成时间", datetime.fromisoformat(str(event.get("resolved_at"))).strftime("%Y-%m-%d %H:%M:%S") if event.get("resolved_at") else "N/A"),
        ("处置总结", event.get("summary", "N/A")),
    ]
    for label, value in events:
        html_parts.append(f"<tr><td class='label'>{label}</td><td>{value or '-'}</td></tr>")
    html_parts.append("</table></div>")
    
    # 关联报警信息
    html_parts.append("<div class='section'>")
    html_parts.append("<div class='section-title'>二、关联报警信息</div>")
    html_parts.append("<table class='info-table'>")
    alarms = [
        ("报警 ID", alarm.get("id", "N/A")),
        ("设备编码", alarm.get("device_code", "N/A")),
        ("报警类型", alarm.get("alarm_type", "N/A")),
        ("报警级别", alarm.get("alarm_level", "N/A")),
        ("报警位置", alarm.get("location_description", "N/A")),
        ("产生时间", datetime.fromisoformat(str(alarm.get("created_at"))).strftime("%Y-%m-%d %H:%M:%S") if alarm.get("created_at") else "N/A"),
    ]
    for label, value in alarms:
        html_parts.append(f"<tr><td class='label'>{label}</td><td>{value or '-'}</td></tr>")
    html_parts.append("</table></div>")
    
    # 时间轴
    html_parts.append("<div class='section'>")
    html_parts.append("<div class='section-title'>三、处置时间轴</div>")
    html_parts.append("<div class='timeline'>")
    
    node_titles = {
        "alarm": "火警产生",
        "confirm": "确认真实火警",
        "linkage": "联动执行",
        "escalation": "超时升级",
        "evacuate": "人员疏散",
        "control": "火情控制",
        "check_in": "人员签到",
        "photo": "现场照片",
        "complete": "处置完成",
    }
    
    for timeline in timelines:
        time_str = datetime.fromisoformat(str(timeline.get("operated_at"))).strftime("%Y-%m-%d %H:%M:%S") if timeline.get("operated_at") else "N/A"
        title = node_titles.get(timeline.get("node_type"), timeline.get("node_type", "未知"))
        description = timeline.get("description", "") or "-"
        
        html_parts.append("<div class='timeline-item'>")
        html_parts.append(f"<div class='timeline-time'>{time_str}</div>")
        html_parts.append(f"<div class='timeline-content'><strong>{title}</strong><br/>{description}</div>")
        html_parts.append("</div>")
    
    html_parts.append("</div></div>")
    
    # Footer
    html_parts.append(f"<div class='footer'><p>报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p><p>系统自动归档 - 请勿篡改</p></div>")
    html_parts.append("</body></html>")
    
    return "".join(html_parts)


async def generate_event_report(
    db: AsyncSession,
    event_id: int,
    request: Optional[EventReportRequest] = None
) -> tuple[int, str]:
    """
    生成事件报告
    
    Args:
        db: DB Session
        event_id: 事件 ID
        request: 报告请求参数
        
    Returns:
        (http_status, content_or_url)
        - 200: 直接返回 HTML/PDF 内容
        - 202: 返回任务 ID（需异步导出）
    """
    from app.models.emergency import EmergencyEvent, EmergencyTimeline
    
    request = request or EventReportRequest()
    
    # 查询事件
    stmt = select(EmergencyEvent).where(EmergencyEvent.id == event_id)
    event = (await db.execute(stmt)).scalar_one_or_none()
    
    if not event:
        return (404, "事件不存在")
    
    # 查询时间轴
    from app.models.alarm import Alarm
    timeline_stmt = select(EmergencyTimeline).where(EmergencyTimeline.event_id == event_id)\
        .order_by(EmergencyTimeline.operated_at.asc())
    result = await db.execute(timeline_stmt)
    # 必须转成 dict：`generate_report_html` 的契约是 `timelines: list`（元素按
    # dict 用 `.get()`）。此前直接把 ORM 对象传进去，第 110 行 `.get()` 必抛
    # `AttributeError: 'EmergencyTimeline' object has no attribute 'get'` ——
    # 凡是**有时间轴节点**的事件导出报告都 500（真实事件恒有 alarm/confirm 两条，
    # 所以等于全坏）。用 canonical payload 转换，不手搓字段。
    timelines = [timeline_payload(node) for node in result.scalars().all()]
    
    # 查询报警
    alarm_stmt = select(Alarm).where(Alarm.id == event.alarm_id)
    alarm = (await db.execute(alarm_stmt)).scalar_one_or_none()
    
    # 生成 HTML
    html_content = generate_report_html(
        event.model_dump() if hasattr(event, 'model_dump') else dict(event.__dict__),
        alarm.model_dump() if hasattr(alarm, 'model_dump') else dict(alarm.__dict__) if alarm else {},
        timelines,
        include_photos=request.include_photos if request else True
    )
    
    # 简单估算页数（每 5000 字符为一页）
    estimated_pages = len(html_content) // 5000
    
    if estimated_pages > 100:
        # TODO: 返回 202 提示异步导出（由 3.9 模块处理）
        return (202, f"报告过大（预计{estimated_pages}页），请使用异步导出功能")
    
    # 直接返回 HTML（前端可打印为 PDF）
    return (200, html_content)
