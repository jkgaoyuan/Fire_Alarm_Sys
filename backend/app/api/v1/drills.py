"""
消防演练管理 API（3.8-B4）
==========================
PRD 章节：3.8 消防演练
端点清单：
1. GET /drills - 演练列表（分页 + 筛选）- drill:view
2. POST /drills - 创建演练计划（drill:create）
3. GET /drills/{id} - 演练详情（drill:view）
4. PUT /drills/{id} - 更新演练计划（drill:update）
5. DELETE /drills/{id} - 删除演练计划（drill:delete）
6. POST /drills/{id}/execute - 开始执行演练（drill:execute）
7. POST /drills/{id}/complete - 完成演练（drill:execute）
8. POST /drills/{id}/cancel - 取消演练（drill:update）
9. POST /drills/{id}/participants - 添加参与人员（drill:execute）
10. POST /drills/{id}/sign-in - 参与人员签到（drill:execute）
11. GET /drills/{id}/evaluation - 获取评估（drill:evaluate）
12. POST /drills/evaluation - 提交评估（drill:evaluate）
13. GET /drills/statistics - 统计数据（drill:stat）
14. GET /drills/{id}/report/html - 生成 HTML 报告（drill:export）

权限码：
- drill:view - 查看演练
- drill:create - 新增计划
- drill:update - 编辑计划
- drill:delete - 删除计划
- drill:execute - 执行演练
- drill:evaluate - 评估打分
- drill:stat - 演练统计
- drill:export - 导出报告
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, Path, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db, require_permission, get_current_user
from app.models.user import User
from app.models.drill import DrillEvent, DrillEvaluation, DrillStatus, DrillType
from app.schemas.auth import ResponseModel as Response
from app.schemas.drill import (
    DrillEventCreate,
    DrillEventUpdate,
    DrillEventResponse,
    DrillEventWithEvaluation,
    DrillEventLite,
    DrillEventPagination,
    DrillEvaluationCreate,
    DrillEvaluationResponse,
    DrillEvaluationLite,
    ParticipantItem,
    ParticipantInput,
    DrillCandidateUser,
    DrillStatistics,
)
from app.crud.drill_crud import drill_crud, eval_crud
from app.services.drill_service import drill_service


router = APIRouter(tags=["Drill"])


# ==================== 辅助 Schema ====================

class DrillExecuteRequest(BaseModel):
    """执行演练请求体"""
    photos: Optional[List[Dict[str, Any]]] = Field(None, description="现场照片")
    videos: Optional[List[Dict[str, Any]]] = Field(None, description="现场视频")


class DrillCompleteRequest(BaseModel):
    """完成演练请求体"""
    summary: str = Field(..., min_length=1, description="现场总结")
    actual_end_at: Optional[datetime] = Field(None, description="实际结束时间")


class DrillCancelRequest(BaseModel):
    """取消演练请求体"""
    reason: Optional[str] = Field(None, description="取消原因")


class DrillSignInRequest(BaseModel):
    """签到请求体"""
    user_id: int = Field(..., description="用户 ID")


# ==================== 辅助函数 ====================

async def get_drill_or_404(db: AsyncSession, drill_id: int) -> DrillEvent:
    """获取演练事件或返回 404"""
    drill = await drill_crud.get(db, drill_id)
    if not drill:
        raise HTTPException(status_code=404, detail="演练不存在")
    return drill


def _participants_payload(
    items: Optional[List[ParticipantInput]],
) -> Optional[List[Dict[str, Any]]]:
    """把 schema 的参与人员转成 CRUD 需要的 dict 列表。

    `None` 表示「请求里没提供这个字段」—— 与「提供了空列表」含义不同
    （前者不动，后者清空），所以这里不能退化成 `[]`。
    """
    if items is None:
        return None
    return [p.model_dump() for p in items]


async def _participants_out(db: AsyncSession, drill: DrillEvent) -> List[ParticipantItem]:
    """把存储的 participants 补上姓名后返回。

    存储形状只有 `{user_id, role, sign_in_at}`（PRD 的 JSONB 形状），**不含姓名**；
    而 `DrillEvent` **没有任何 relationship / ForeignKey**（见 `models/drill.py`，
    `created_by` 只是裸 Integer），所以不能写 `drill.creator.real_name`，
    只能手动查一次 User。

    姓名**只进响应，绝不写回 JSONB**。用户已被删除时 `user_name` 留 `None`，
    由前端回退显示 `#<user_id>`。

    此前本文件有 6 处各自内联 `[ParticipantItem(**p) for p in ...]`，
    全部无姓名；统一走这里，避免再出现第 7 处漏掉姓名。
    """
    raw = drill.participants or []
    user_ids = {p["user_id"] for p in raw if "user_id" in p}

    name_map: Dict[int, str] = {}
    if user_ids:
        rows = await db.execute(
            select(User.id, User.real_name, User.username).where(User.id.in_(user_ids))
        )
        name_map = {uid: (real_name or username) for uid, real_name, username in rows.all()}

    # 刻意逐字段构造而非 `ParticipantItem(**p)`：后者在存储形状意外多出
    # `user_name` 键时会抛「重复传参」，而 JSONB 是无类型约束的。
    return [
        ParticipantItem(
            user_id=p["user_id"],
            role=p.get("role") or "参与者",
            sign_in_at=p.get("sign_in_at"),
            user_name=name_map.get(p["user_id"]),
        )
        for p in raw
    ]


# ==================== 演练计划管理 ====================

@router.get(
    "/drills",
    response_model=Response[DrillEventPagination],
    summary="获取演练列表",
    dependencies=[Depends(require_permission("drill:view"))]
)
async def get_drill_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status_filter: Optional[str] = Query(None, description="状态筛选"),
    drill_type: Optional[str] = Query(None, description="类型筛选"),
    db: AsyncSession = Depends(get_db),
):
    """分页查询演练列表"""
    try:
        status_enum = DrillStatus(status_filter) if status_filter else None
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的状态值：{status_filter}")
    try:
        type_enum = DrillType(drill_type) if drill_type else None
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的演练类型：{drill_type}")

    skip = (page - 1) * page_size
    drills, total = await drill_crud.get_list(
        db,
        skip=skip,
        limit=page_size,
        status_filter=status_enum,
        drill_type_filter=type_enum,
    )

    items = [
        DrillEventLite(
            id=d.id,
            drill_name=d.drill_name,
            drill_type=DrillType(d.drill_type),
            status=DrillStatus(d.status),
            planned_at=d.planned_at,
            location=d.location,
            created_at=d.created_at,
            participant_count=len(d.participants or []),
        )
        for d in drills
    ]

    return Response(
        data=DrillEventPagination(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "/drills",
    response_model=Response[DrillEventResponse],
    summary="创建演练计划",
    dependencies=[Depends(require_permission("drill:create"))]
)
async def create_drill(
    drill_data: DrillEventCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建演练计划"""
    drill = await drill_crud.create(
        db,
        drill_name=drill_data.drill_name,
        drill_type=drill_data.drill_type,
        created_by=user.id,
        planned_at=drill_data.planned_at,
        location=drill_data.location,
        participant_user_ids=drill_data.participant_user_ids,
        participants_input=_participants_payload(drill_data.participants),
        status=drill_data.status or DrillStatus.planned,
    )

    return Response(
        data=DrillEventResponse(
            id=drill.id,
            drill_name=drill.drill_name,
            drill_type=DrillType(drill.drill_type),
            status=DrillStatus(drill.status),
            planned_at=drill.planned_at,
            location=drill.location,
            created_at=drill.created_at,
            participant_count=len(drill.participants or []),
            actual_start_at=drill.actual_start_at,
            actual_end_at=drill.actual_end_at,
            summary=drill.summary,
            photos=drill.photos or [],
            videos=drill.videos or [],
            participants=await _participants_out(db, drill),
            created_by=drill.created_by,
            updated_at=drill.updated_at,
        )
    )


@router.get(
    "/drills/statistics",
    response_model=Response[DrillStatistics],
    summary="演练统计数据",
    dependencies=[Depends(require_permission("drill:stat"))]
)
async def get_statistics(
    db: AsyncSession = Depends(get_db),
):
    """获取演练统计信息"""
    stats = await drill_crud.get_stats(db)
    return Response(data=DrillStatistics(**stats))


# ⚠️ 本路由必须声明在 `/drills/{drill_id}` 之前（下方）。FastAPI 按声明顺序匹配，
#    否则 "participant-candidates" 会被 `{drill_id}: int` 吃掉并返回 422。
#    同上方的 `/drills/statistics`。
@router.get(
    "/drills/participant-candidates",
    response_model=Response[List[DrillCandidateUser]],
    summary="演练参与人员候选人",
    dependencies=[Depends(require_permission("drill:execute"))]
)
async def list_participant_candidates(
    keyword: Optional[str] = Query(None, description="按用户名 / 姓名模糊搜索"),
    db: AsyncSession = Depends(get_db),
):
    """列出可被选为参与人员的人员（供演练表单与详情页的选择器使用）

    **为什么不复用 `GET /users`**：那个端点由 `system:user` 守卫，而演练域由
    `drill:*` 守卫 —— 值班员与维保员持有 `drill:execute` 却**没有** `system:user`，
    沿用会让「执行演练时加人」对他们整个不可用（与 P2-011 同族的问题）。

    **为什么权限选 `drill:execute` 而非 `drill:view`**：`require_permission`
    只接受单个权限码、没有 any-of 变体（`core/dependencies.py:86`）。而详情页
    「添加参与人员」本身就是 `drill:execute` 守卫的，所以它是**在覆盖所有需要它
    的人的前提下最窄的那个**；表单侧要 `drill:create`，主管绑定全部权限码，已被覆盖。

    ⚠️ **暴露面变化**：值班员 / 维保员将首次能看到「活跃用户的姓名 + 角色名」。
    他们本就能执行演练并为演练点名加人，属于本需求内在；因此这里刻意返回
    **精简字段**（不含 phone / email / data_scope / status），不复用 `UserOut`。
    """
    stmt = (
        select(User)
        .options(selectinload(User.roles))
        .where(User.status == "active")
        .order_by(User.id.asc())
    )
    if keyword:
        stmt = stmt.where(
            User.username.ilike(f"%{keyword}%") | User.real_name.ilike(f"%{keyword}%")
        )
    # 沿用全仓既有用户选择器的约定（一次性拉 100，无 remote-method）。
    # 已知限制：用户超过 100 人时选不到，已登记待办。
    stmt = stmt.limit(100)

    users = (await db.execute(stmt)).scalars().all()

    return Response(
        data=[
            DrillCandidateUser(
                id=u.id,
                username=u.username,
                real_name=u.real_name,
                role_names=[r.role_name for r in u.roles],
            )
            for u in users
        ]
    )


@router.get(
    "/drills/{drill_id}",
    response_model=Response[DrillEventWithEvaluation],
    summary="获取演练详情",
    dependencies=[Depends(require_permission("drill:view"))]
)
async def get_drill_detail(
    drill_id: int = Path(..., description="演练 ID"),
    db: AsyncSession = Depends(get_db),
):
    """获取演练详情（包含参与人员、照片、视频、评估等）"""
    drill = await get_drill_or_404(db, drill_id)
    evaluation = await eval_crud.get_by_drill_id(db, drill_id)

    eval_resp = None
    if evaluation:
        eval_resp = DrillEvaluationResponse(
            id=evaluation.id,
            drill_id=evaluation.drill_id,
            total_score=evaluation.total_score,
            evaluated_at=evaluation.evaluated_at,
            evaluator_id=evaluation.evaluator_id,
            items=evaluation.items or [],
            problems=evaluation.problems,
            improvements=evaluation.improvements,
            evaluation_summary=evaluation.evaluation_summary,
            created_at=evaluation.created_at,
            updated_at=evaluation.updated_at,
        )

    return Response(
        data=DrillEventWithEvaluation(
            id=drill.id,
            drill_name=drill.drill_name,
            drill_type=DrillType(drill.drill_type),
            status=DrillStatus(drill.status),
            planned_at=drill.planned_at,
            location=drill.location,
            created_at=drill.created_at,
            participant_count=len(drill.participants or []),
            actual_start_at=drill.actual_start_at,
            actual_end_at=drill.actual_end_at,
            summary=drill.summary,
            photos=drill.photos or [],
            videos=drill.videos or [],
            participants=await _participants_out(db, drill),
            created_by=drill.created_by,
            updated_at=drill.updated_at,
            evaluation=eval_resp,
        )
    )


@router.put(
    "/drills/{drill_id}",
    response_model=Response[DrillEventResponse],
    summary="更新演练计划",
    dependencies=[Depends(require_permission("drill:update"))]
)
async def update_drill(
    drill_id: int = Path(..., description="演练 ID"),
    update_data: DrillEventUpdate = ...,
    db: AsyncSession = Depends(get_db),
):
    """更新演练计划"""
    updated = await drill_crud.update(
        db,
        drill_id,
        drill_name=update_data.drill_name,
        drill_type=update_data.drill_type,
        planned_at=update_data.planned_at,
        actual_start_at=update_data.actual_start_at,
        actual_end_at=update_data.actual_end_at,
        location=update_data.location,
        participant_user_ids=update_data.participant_user_ids,
        participants_input=_participants_payload(update_data.participants),
        status=update_data.status,
        summary=update_data.summary,
        photos=update_data.photos,
        videos=update_data.videos,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="演练不存在")

    return Response(
        data=DrillEventResponse(
            id=updated.id,
            drill_name=updated.drill_name,
            drill_type=DrillType(updated.drill_type),
            status=DrillStatus(updated.status),
            planned_at=updated.planned_at,
            location=updated.location,
            created_at=updated.created_at,
            participant_count=len(updated.participants or []),
            actual_start_at=updated.actual_start_at,
            actual_end_at=updated.actual_end_at,
            summary=updated.summary,
            photos=updated.photos or [],
            videos=updated.videos or [],
            participants=await _participants_out(db, updated),
            created_by=updated.created_by,
            updated_at=updated.updated_at,
        )
    )


@router.delete(
    "/drills/{drill_id}",
    response_model=Response[None],
    summary="删除演练计划",
    dependencies=[Depends(require_permission("drill:delete"))]
)
async def delete_drill(
    drill_id: int = Path(..., description="演练 ID"),
    db: AsyncSession = Depends(get_db),
):
    """删除演练计划（级联删除评估）"""
    success = await drill_crud.delete(db, drill_id)
    if not success:
        raise HTTPException(status_code=404, detail="演练不存在")
    return Response(data=None)


# ==================== 演练执行管理 ====================

@router.post(
    "/drills/{drill_id}/execute",
    response_model=Response[DrillEventResponse],
    summary="开始执行演练",
    dependencies=[Depends(require_permission("drill:execute"))]
)
async def start_execute_drill(
    drill_id: int = Path(..., description="演练 ID"),
    request: DrillExecuteRequest = None,
    db: AsyncSession = Depends(get_db),
):
    """开始执行演练（planned → ongoing）"""
    try:
        drill = await drill_service.execute_drill(
            db,
            drill_id=drill_id,
            actual_start_at=datetime.now(),
            photos=request.photos if request else None,
            videos=request.videos if request else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        data=DrillEventResponse(
            id=drill.id,
            drill_name=drill.drill_name,
            drill_type=DrillType(drill.drill_type),
            status=DrillStatus(drill.status),
            planned_at=drill.planned_at,
            location=drill.location,
            created_at=drill.created_at,
            participant_count=len(drill.participants or []),
            actual_start_at=drill.actual_start_at,
            actual_end_at=drill.actual_end_at,
            summary=drill.summary,
            photos=drill.photos or [],
            videos=drill.videos or [],
            participants=await _participants_out(db, drill),
            created_by=drill.created_by,
            updated_at=drill.updated_at,
        )
    )


@router.post(
    "/drills/{drill_id}/complete",
    response_model=Response[DrillEventResponse],
    summary="完成演练",
    dependencies=[Depends(require_permission("drill:execute"))]
)
async def complete_drill(
    drill_id: int = Path(..., description="演练 ID"),
    request: DrillCompleteRequest = ...,
    db: AsyncSession = Depends(get_db),
):
    """完成演练（ongoing → completed）"""
    try:
        drill = await drill_service.complete_drill(
            db,
            drill_id=drill_id,
            summary=request.summary,
            actual_end_at=request.actual_end_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        data=DrillEventResponse(
            id=drill.id,
            drill_name=drill.drill_name,
            drill_type=DrillType(drill.drill_type),
            status=DrillStatus(drill.status),
            planned_at=drill.planned_at,
            location=drill.location,
            created_at=drill.created_at,
            participant_count=len(drill.participants or []),
            actual_start_at=drill.actual_start_at,
            actual_end_at=drill.actual_end_at,
            summary=drill.summary,
            photos=drill.photos or [],
            videos=drill.videos or [],
            participants=await _participants_out(db, drill),
            created_by=drill.created_by,
            updated_at=drill.updated_at,
        )
    )


@router.post(
    "/drills/{drill_id}/cancel",
    response_model=Response[DrillEventResponse],
    summary="取消演练",
    dependencies=[Depends(require_permission("drill:update"))]
)
async def cancel_drill(
    drill_id: int = Path(..., description="演练 ID"),
    request: DrillCancelRequest = None,
    db: AsyncSession = Depends(get_db),
):
    """取消演练计划"""
    try:
        drill = await drill_service.cancel_drill(
            db,
            drill_id=drill_id,
            reason=request.reason if request else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        data=DrillEventResponse(
            id=drill.id,
            drill_name=drill.drill_name,
            drill_type=DrillType(drill.drill_type),
            status=DrillStatus(drill.status),
            planned_at=drill.planned_at,
            location=drill.location,
            created_at=drill.created_at,
            participant_count=len(drill.participants or []),
            actual_start_at=drill.actual_start_at,
            actual_end_at=drill.actual_end_at,
            summary=drill.summary,
            photos=drill.photos or [],
            videos=drill.videos or [],
            participants=await _participants_out(db, drill),
            created_by=drill.created_by,
            updated_at=drill.updated_at,
        )
    )


@router.post(
    "/drills/{drill_id}/participants",
    response_model=Response[ParticipantItem],
    summary="添加参与人员",
    dependencies=[Depends(require_permission("drill:execute"))]
)
async def add_participant(
    drill_id: int = Path(..., description="演练 ID"),
    request: DrillSignInRequest = ...,
    role: str = Query("参与者", description="参与角色"),
    db: AsyncSession = Depends(get_db),
):
    """添加演练参与人员"""
    drill = await drill_crud.add_participant(
        db, drill_id=drill_id, user_id=request.user_id, role=role
    )
    if not drill:
        raise HTTPException(status_code=404, detail="演练不存在")

    return Response(
        data=ParticipantItem(user_id=request.user_id, role=role, sign_in_at=None)
    )


@router.post(
    "/drills/{drill_id}/sign-in",
    response_model=Response[None],
    summary="参与人员签到",
    dependencies=[Depends(require_permission("drill:execute"))]
)
async def sign_in(
    drill_id: int = Path(..., description="演练 ID"),
    request: DrillSignInRequest = ...,
    db: AsyncSession = Depends(get_db),
):
    """参与人员签到"""
    drill = await drill_crud.sign_in(db, drill_id=drill_id, user_id=request.user_id)
    if not drill:
        raise HTTPException(status_code=404, detail="演练不存在或未配置该参与人员")
    return Response(data=None)


# ==================== 评估打分 ====================

@router.get(
    "/drills/{drill_id}/evaluation",
    response_model=Response[DrillEvaluationResponse],
    summary="获取演练评估",
    dependencies=[Depends(require_permission("drill:evaluate"))]
)
async def get_evaluation(
    drill_id: int = Path(..., description="演练 ID"),
    db: AsyncSession = Depends(get_db),
):
    """获取演练评估（每个演练只有一个评估）"""
    evaluation = await eval_crud.get_by_drill_id(db, drill_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="该演练暂无评估")

    return Response(
        data=DrillEvaluationResponse(
            id=evaluation.id,
            drill_id=evaluation.drill_id,
            total_score=evaluation.total_score,
            evaluated_at=evaluation.evaluated_at,
            evaluator_id=evaluation.evaluator_id,
            items=evaluation.items or [],
            problems=evaluation.problems,
            improvements=evaluation.improvements,
            evaluation_summary=evaluation.evaluation_summary,
            created_at=evaluation.created_at,
            updated_at=evaluation.updated_at,
        )
    )


@router.post(
    "/drills/evaluation",
    response_model=Response[DrillEvaluationResponse],
    summary="提交演练评估",
    dependencies=[Depends(require_permission("drill:evaluate"))]
)
async def submit_evaluation(
    evaluation_data: DrillEvaluationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交演练评估（仅允许一次）"""
    try:
        evaluation = await drill_service.submit_evaluation(
            db,
            drill_id=evaluation_data.drill_id,
            evaluator_id=user.id,
            items=evaluation_data.items,
            problems=evaluation_data.problems,
            improvements=evaluation_data.improvements,
            evaluation_summary=evaluation_data.evaluation_summary,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        data=DrillEvaluationResponse(
            id=evaluation.id,
            drill_id=evaluation.drill_id,
            total_score=evaluation.total_score,
            evaluated_at=evaluation.evaluated_at,
            evaluator_id=evaluation.evaluator_id,
            items=evaluation.items or [],
            problems=evaluation.problems,
            improvements=evaluation.improvements,
            evaluation_summary=evaluation.evaluation_summary,
            created_at=evaluation.created_at,
            updated_at=evaluation.updated_at,
        )
    )


# ==================== 报告导出 ====================

@router.get(
    "/drills/{drill_id}/report/html",
    response_model=Response[str],
    summary="生成演练报告 HTML",
    dependencies=[Depends(require_permission("drill:export"))]
)
async def export_report_html(
    drill_id: int = Path(..., description="演练 ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    生成演练评估报告 HTML（前端使用浏览器打印功能转换为 PDF）
    复用 3.5 的 HTML+Print 方案，无需额外依赖 reportlab
    """
    try:
        html = await drill_service.generate_report_html(db, drill_id)
        return Response(data=html)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
