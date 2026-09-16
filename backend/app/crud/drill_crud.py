"""
消防演练模块 CRUD 操作（3.8 FR-043 ~ FR-047）
===============================================
对应模型：DrillEvent, DrillEvaluation
遵循项目 CRUD 规范：异步 AsyncSession，独立方法（不依赖 Create/Update Schema 传参）
"""

from copy import deepcopy
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drill import DrillEvent, DrillEvaluation, DrillStatus, DrillType
from app.schemas.drill import EvaluationItem


# ==================== 参与人员归一 ====================

DEFAULT_PARTICIPANT_ROLE = "参与者"


def _normalize_participants(
    participants: Optional[List[Dict[str, Any]]] = None,
    participant_user_ids: Optional[List[int]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """把两种入参形态归一成存储形状 `{user_id, role, sign_in_at}`。

    - `participants`（新，逐人带 role）优先；缺失则回退 `participant_user_ids`（旧，全部「参与者」）
    - 两者都为 `None` 时返回 `None` —— 调用方据此区分「没传」与「传了空列表」，
      这个区别在 update 里很重要：没传 = 不动，传 `[]` = 清空

    元素须为 `dict`（端点负责把 Pydantic 模型 `model_dump()` 后再传）。
    全仓库**只有这一处**决定 role 的默认值 —— 此前 `create` 与 `update` 各自
    硬编码了一份「参与者」，前端填的角色必然被丢弃。
    """
    if participants is not None:
        return [
            {
                "user_id": p["user_id"],
                "role": p.get("role") or DEFAULT_PARTICIPANT_ROLE,
                "sign_in_at": None,
            }
            for p in participants
        ]
    if participant_user_ids is not None:
        return [
            {"user_id": uid, "role": DEFAULT_PARTICIPANT_ROLE, "sign_in_at": None}
            for uid in participant_user_ids
        ]
    return None


# ==================== DrillEvent CRUD ====================

class DrillEventCRUD:
    """演练事件 CRUD 操作"""

    def __init__(self):
        self.model = DrillEvent

    async def get(self, db: AsyncSession, drill_id: int) -> Optional[DrillEvent]:
        """根据 ID 查询演练事件"""
        result = await db.execute(
            select(DrillEvent).where(DrillEvent.id == drill_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        db: AsyncSession,
        *,
        drill_name: str,
        drill_type: DrillType,
        created_by: int,
        planned_at: Optional[datetime] = None,
        location: Optional[str] = None,
        participant_user_ids: Optional[List[int]] = None,
        participants_input: Optional[List[Dict[str, Any]]] = None,
        status: DrillStatus = DrillStatus.planned,
    ) -> DrillEvent:
        """创建演练事件

        `participants_input`（带 role）优先于 `participant_user_ids`（旧，全部「参与者」）。
        见 `_normalize_participants`。
        """
        participants = _normalize_participants(participants_input, participant_user_ids) or []
        drill = DrillEvent(
            drill_name=drill_name,
            drill_type=drill_type.value if isinstance(drill_type, DrillType) else drill_type,
            planned_at=planned_at,
            location=location,
            participants=participants,
            status=status.value if isinstance(status, DrillStatus) else status,
            created_by=created_by,
        )
        db.add(drill)
        await db.commit()
        await db.refresh(drill)
        return drill

    async def get_list(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 50,
        status_filter: Optional[DrillStatus] = None,
        drill_type_filter: Optional[DrillType] = None,
    ) -> Tuple[List[DrillEvent], int]:
        """分页查询演练列表（支持状态/类型筛选）"""
        stmt = select(DrillEvent)

        if status_filter is not None:
            stmt = stmt.where(DrillEvent.status == status_filter.value)
        if drill_type_filter is not None:
            stmt = stmt.where(DrillEvent.drill_type == drill_type_filter.value)

        # 总数（独立 count 语句，避免子查询兼容问题）
        count_stmt = select(func.count()).select_from(DrillEvent)
        if status_filter is not None:
            count_stmt = count_stmt.where(DrillEvent.status == status_filter.value)
        if drill_type_filter is not None:
            count_stmt = count_stmt.where(DrillEvent.drill_type == drill_type_filter.value)
        total = (await db.execute(count_stmt)).scalar_one() or 0

        result = await db.execute(
            stmt.order_by(DrillEvent.id.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def update(
        self,
        db: AsyncSession,
        drill_id: int,
        *,
        drill_name: Optional[str] = None,
        drill_type: Optional[DrillType] = None,
        planned_at: Optional[datetime] = None,
        actual_start_at: Optional[datetime] = None,
        actual_end_at: Optional[datetime] = None,
        location: Optional[str] = None,
        participant_user_ids: Optional[List[int]] = None,
        participants_input: Optional[List[Dict[str, Any]]] = None,
        status: Optional[DrillStatus] = None,
        summary: Optional[str] = None,
        photos: Optional[List[Dict[str, Any]]] = None,
        videos: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[DrillEvent]:
        """更新演练事件（仅更新显式传入的字段）

        ⚠️ **整体覆盖语义**：传入参与人员时会**全量替换** `drill.participants`，
        原有的 `sign_in_at`（签到记录）会被一并清零。这是既存行为，本次未改变，
        但角色变为可编辑后，用户会更频繁地编辑这一栏，撞上的概率上升。
        """

        drill = await self.get(db, drill_id)
        if not drill:
            return None

        if drill_name is not None:
            drill.drill_name = drill_name
        if drill_type is not None:
            drill.drill_type = drill_type.value if isinstance(drill_type, DrillType) else drill_type
        if planned_at is not None:
            drill.planned_at = planned_at
        if actual_start_at is not None:
            drill.actual_start_at = actual_start_at
        if actual_end_at is not None:
            drill.actual_end_at = actual_end_at
        if location is not None:
            drill.location = location
        if status is not None:
            drill.status = status.value if isinstance(status, DrillStatus) else status
        if summary is not None:
            drill.summary = summary
        if photos is not None:
            drill.photos = photos
        if videos is not None:
            drill.videos = videos
        # 只有显式传了参与人员才动它。normalized 为 None 表示两个字段都没传 ——
        # 与「传了空列表表示清空」是两回事，不能合并。
        normalized = _normalize_participants(participants_input, participant_user_ids)
        if normalized is not None:
            drill.participants = normalized

        db.add(drill)
        await db.commit()
        await db.refresh(drill)
        return drill

    async def delete(self, db: AsyncSession, drill_id: int) -> bool:
        """删除演练事件（ORM 级联删除评估）"""
        drill = await self.get(db, drill_id)
        if not drill:
            return False
        await db.delete(drill)
        await db.commit()
        return True

    async def add_participant(
        self, db: AsyncSession, *, drill_id: int, user_id: int, role: str
    ) -> Optional[DrillEvent]:
        """添加参与人员（已存在则更新角色）"""
        drill = await self.get(db, drill_id)
        if not drill:
            return None

        # 深拷贝：避免与 SQLAlchemy 历史快照共享 dict 对象导致变更检测失效
        participants = deepcopy(drill.participants or [])
        for p in participants:
            if p.get("user_id") == user_id:
                p["role"] = role
                break
        else:
            participants.append({"user_id": user_id, "role": role, "sign_in_at": None})

        # 重新赋值触发 SQLAlchemy JSON 变更检测
        drill.participants = participants
        db.add(drill)
        await db.commit()
        await db.refresh(drill)
        return drill

    async def sign_in(
        self, db: AsyncSession, *, drill_id: int, user_id: int
    ) -> Optional[DrillEvent]:
        """参与人员签到"""
        drill = await self.get(db, drill_id)
        if not drill:
            return None

        # 深拷贝：避免与 SQLAlchemy 历史快照共享 dict 对象导致变更检测失效
        participants = deepcopy(drill.participants or [])
        found = False
        for p in participants:
            if p.get("user_id") == user_id:
                p["sign_in_at"] = datetime.now().isoformat()
                found = True
                break
        if not found:
            return None

        drill.participants = participants
        db.add(drill)
        await db.commit()
        await db.refresh(drill)
        return drill

    async def get_stats(
        self,
        db: AsyncSession,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """演练统计数据"""
        # 总数与完成数
        total_stmt = select(func.count()).select_from(DrillEvent)
        completed_stmt = select(func.count()).select_from(DrillEvent).where(
            DrillEvent.status == DrillStatus.completed.value
        )
        total = (await db.execute(total_stmt)).scalar_one() or 0
        completed = (await db.execute(completed_stmt)).scalar_one() or 0

        # 本月演练数
        now = datetime.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_stmt = select(func.count()).select_from(DrillEvent).where(
            DrillEvent.created_at >= month_start
        )
        this_month = (await db.execute(month_stmt)).scalar_one() or 0

        # 平均评估分
        avg_stmt = select(func.avg(DrillEvaluation.total_score))
        avg_score = (await db.execute(avg_stmt)).scalar_one()
        avg_score = round(float(avg_score), 2) if avg_score is not None else 0.0

        completion_rate = (completed / total * 100) if total > 0 else 0.0

        return {
            "total_drills": total,
            "completed_drills": completed,
            "this_month_drills": this_month,
            "avg_score": avg_score,
            "completion_rate": round(completion_rate, 2),
        }


# ==================== DrillEvaluation CRUD ====================

class DrillEvaluationCRUD:
    """演练评估 CRUD 操作"""

    def __init__(self):
        self.model = DrillEvaluation

    async def get(self, db: AsyncSession, eval_id: int) -> Optional[DrillEvaluation]:
        """根据 ID 查询评估"""
        result = await db.execute(
            select(DrillEvaluation).where(DrillEvaluation.id == eval_id)
        )
        return result.scalar_one_or_none()

    async def get_by_drill_id(
        self, db: AsyncSession, drill_id: int
    ) -> Optional[DrillEvaluation]:
        """根据演练 ID 获取评估（唯一）"""
        result = await db.execute(
            select(DrillEvaluation).where(DrillEvaluation.drill_id == drill_id)
        )
        return result.scalar_one_or_none()

    async def create(
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
        """创建演练评估（自动计算总分）"""
        total_score = sum(item.score for item in items)
        # Pydantic 模型序列化存储
        items_data = [item.model_dump() for item in items]

        evaluation = DrillEvaluation(
            drill_id=drill_id,
            evaluator_id=evaluator_id,
            items=items_data,
            total_score=total_score,
            problems=problems,
            improvements=improvements,
            evaluation_summary=evaluation_summary,
        )
        db.add(evaluation)
        await db.commit()
        await db.refresh(evaluation)
        return evaluation

    async def update(
        self,
        db: AsyncSession,
        eval_id: int,
        *,
        items: Optional[List[EvaluationItem]] = None,
        problems: Optional[str] = None,
        improvements: Optional[str] = None,
        evaluation_summary: Optional[str] = None,
    ) -> Optional[DrillEvaluation]:
        """更新评估（items 更新时重新计算总分）"""
        evaluation = await self.get(db, eval_id)
        if not evaluation:
            return None

        if items is not None:
            evaluation.items = [item.model_dump() for item in items]
            evaluation.total_score = sum(item.score for item in items)
        if problems is not None:
            evaluation.problems = problems
        if improvements is not None:
            evaluation.improvements = improvements
        if evaluation_summary is not None:
            evaluation.evaluation_summary = evaluation_summary

        db.add(evaluation)
        await db.commit()
        await db.refresh(evaluation)
        return evaluation

    async def delete(self, db: AsyncSession, eval_id: int) -> bool:
        """删除评估"""
        evaluation = await self.get(db, eval_id)
        if not evaluation:
            return False
        await db.delete(evaluation)
        await db.commit()
        return True


# 导出实例（模块级单例）
drill_crud = DrillEventCRUD()
eval_crud = DrillEvaluationCRUD()
