"""
消防演练服务层（3.8 模块）
===========================
核心业务逻辑：
- 演练执行流程管理（planned → ongoing → completed）
- 评估打分与分数计算
- 报告生成（复用 3.5 HTML + 前端打印方案，无需 reportlab）
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drill import DrillEvent, DrillEvaluation, DrillStatus
from app.schemas.drill import EvaluationItem
from app.crud.drill_crud import drill_crud, eval_crud


class DrillService:
    """演练业务服务类"""

    # ==================== 演练执行流程 ====================

    async def execute_drill(
        self,
        db: AsyncSession,
        *,
        drill_id: int,
        actual_start_at: datetime,
        photos: Optional[List[Dict[str, Any]]] = None,
        videos: Optional[List[Dict[str, Any]]] = None,
    ) -> DrillEvent:
        """开始执行演练（planned → ongoing）"""
        drill = await drill_crud.get(db, drill_id)
        if not drill:
            raise ValueError(f"演练不存在：{drill_id}")

        if drill.status != DrillStatus.planned.value:
            raise ValueError(f"演练当前状态为'{drill.status}'，无法开始执行（仅计划中的演练可执行）")

        drill.status = DrillStatus.ongoing.value
        drill.actual_start_at = actual_start_at
        if photos:
            drill.photos = photos
        if videos:
            drill.videos = videos

        db.add(drill)
        await db.commit()
        await db.refresh(drill)
        return drill

    async def complete_drill(
        self,
        db: AsyncSession,
        *,
        drill_id: int,
        summary: str,
        actual_end_at: Optional[datetime] = None,
    ) -> DrillEvent:
        """完成演练（ongoing → completed）"""
        drill = await drill_crud.get(db, drill_id)
        if not drill:
            raise ValueError(f"演练不存在：{drill_id}")

        if drill.status != DrillStatus.ongoing.value:
            raise ValueError(f"演练当前状态为'{drill.status}'，无法标记完成（仅执行中的演练可完成）")

        drill.summary = summary
        drill.actual_end_at = actual_end_at or datetime.now()
        drill.status = DrillStatus.completed.value

        db.add(drill)
        await db.commit()
        await db.refresh(drill)
        return drill

    async def cancel_drill(
        self,
        db: AsyncSession,
        *,
        drill_id: int,
        reason: Optional[str] = None,
    ) -> DrillEvent:
        """取消演练（planned/ongoing → cancelled）"""
        drill = await drill_crud.get(db, drill_id)
        if not drill:
            raise ValueError(f"演练不存在：{drill_id}")

        if drill.status == DrillStatus.completed.value:
            raise ValueError("已完成的演练不能取消")

        drill.status = DrillStatus.cancelled.value
        if reason:
            current = drill.summary or ""
            drill.summary = f"{current} 取消原因：{reason}".strip()

        db.add(drill)
        await db.commit()
        await db.refresh(drill)
        return drill

    # ==================== 评估打分 ====================

    async def submit_evaluation(
        self,
        db: AsyncSession,
        *,
        drill_id: int,
        evaluator_id: int,
        items: List[EvaluationItem],
        problems: Optional[str] = None,
        improvements: Optional[str] = None,
        evaluation_summary: Optional[str] = None,
    ) -> DrillEvaluation:
        """提交演练评估（每演练仅一次）"""
        drill = await drill_crud.get(db, drill_id)
        if not drill:
            raise ValueError(f"演练不存在：{drill_id}")

        existing = await eval_crud.get_by_drill_id(db, drill_id)
        if existing:
            raise ValueError(f"演练 {drill_id} 已有评估，请勿重复提交")

        return await eval_crud.create(
            db,
            drill_id=drill_id,
            evaluator_id=evaluator_id,
            items=items,
            problems=problems,
            improvements=improvements,
            evaluation_summary=evaluation_summary,
        )

    # ==================== 报告生成（3.5 HTML + Print 方案） ====================

    async def generate_report_html(self, db: AsyncSession, drill_id: int) -> str:
        """
        生成演练评估报告 HTML
        前端通过 window.print() 转换为 PDF（复用 3.5 方案）
        """
        drill = await drill_crud.get(db, drill_id)
        if not drill:
            raise ValueError(f"演练不存在：{drill_id}")

        evaluation = await eval_crud.get_by_drill_id(db, drill_id)

        def fmt(dt: Optional[datetime]) -> str:
            return dt.strftime("%Y-%m-%d %H:%M") if dt else "—"

        type_labels = {
            "evacuation": "疏散演练",
            "firefighting": "灭火演练",
            "comprehensive": "综合演练",
        }
        status_labels = {
            "planned": "计划中",
            "ongoing": "执行中",
            "completed": "已完成",
            "cancelled": "已取消",
        }

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>消防演练评估报告 - {drill.drill_name}</title>
<style>
    body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; padding: 40px; line-height: 1.6; color: #333; }}
    h1 {{ color: #d9534f; border-bottom: 3px solid #d9534f; padding-bottom: 10px; }}
    h2 {{ color: #c9302c; margin-top: 30px; }}
    .info-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
    .info-table th, .info-table td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
    .info-table th {{ background-color: #f8f9fa; width: 120px; }}
    .score-section {{ background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0; }}
    .score-item {{ display: flex; justify-content: space-between; margin: 8px 0; }}
    .score-total {{ font-size: 18px; font-weight: bold; color: #d9534f; margin-top: 15px; padding-top: 15px; border-top: 2px solid #ddd; }}
    .section-box {{ background: #fff; border: 1px solid #ddd; padding: 20px; margin: 20px 0; border-radius: 5px; }}
    .footer {{ margin-top: 40px; text-align: right; font-size: 12px; color: #666; }}
    @media print {{ body {{ padding: 0; }} .no-print {{ display: none; }} }}
</style>
</head>
<body>
<h1>消防演练评估报告</h1>
<div class="no-print" style="text-align:center;margin:20px;">
<button onclick="window.print()" style="padding:10px 30px;background:#d9534f;color:white;border:none;border-radius:5px;cursor:pointer;font-size:14px;">打印为 PDF</button>
</div>
<table class="info-table">
<tr><th>演练名称</th><td>{drill.drill_name}</td></tr>
<tr><th>演练类型</th><td>{type_labels.get(drill.drill_type, drill.drill_type)}</td></tr>
<tr><th>计划时间</th><td>{fmt(drill.planned_at)}</td></tr>
<tr><th>实际开始</th><td>{fmt(drill.actual_start_at)}</td></tr>
<tr><th>实际结束</th><td>{fmt(drill.actual_end_at)}</td></tr>
<tr><th>演练地点</th><td>{drill.location or "未指定"}</td></tr>
<tr><th>参与人数</th><td>{len(drill.participants or [])}人</td></tr>
<tr><th>演练状态</th><td>{status_labels.get(drill.status, drill.status)}</td></tr>
</table>
<h2>现场总结</h2>
<div class="section-box">{drill.summary or "无现场总结"}</div>
"""

        if evaluation:
            html += "<h2>评估得分</h2><div class='score-section'>"
            for item in evaluation.items or []:
                item_obj = EvaluationItem(**item) if isinstance(item, dict) else item
                ratio = (item_obj.score / item_obj.max_score * 100) if item_obj.max_score else 0
                html += (
                    f"<div class='score-item'>"
                    f"<span>{item_obj.label}</span>"
                    f"<span>{item_obj.score}/{item_obj.max_score}分（{ratio:.0f}%）</span></div>"
                )
                if item_obj.comment:
                    html += f"<div style='margin-left:20px;color:#666;font-size:12px;'>备注：{item_obj.comment}</div>"
            html += f"<div class='score-total'>总分：{evaluation.total_score}分</div></div>"

            if evaluation.problems:
                html += f"<h2>存在问题</h2><div class='section-box'>{evaluation.problems}</div>"
            if evaluation.improvements:
                html += f"<h2>改进措施</h2><div class='section-box'>{evaluation.improvements}</div>"
            if evaluation.evaluation_summary:
                html += f"<h2>总体评估摘要</h2><div class='section-box'>{evaluation.evaluation_summary}</div>"
        else:
            html += "<h2>评估得分</h2><p style='color:#999;padding:20px;'>暂无评估数据</p>"

        html += f"""
<div class="footer">
报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
| 报告编号：DRILL-{drill.id}-RPT
</div>
</body></html>"""
        return html


# 导出服务实例
drill_service = DrillService()
