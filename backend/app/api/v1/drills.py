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
            participants=[
                ParticipantItem(**p) for p in (drill.participants or [])
            ],
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
            participants=[ParticipantItem(**p) for p in (drill.participants or [])],
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
            participants=[ParticipantItem(**p) for p in (updated.participants or [])],
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
            participants=[ParticipantItem(**p) for p in (drill.participants or [])],
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
            participants=[ParticipantItem(**p) for p in (drill.participants or [])],
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
            participants=[ParticipantItem(**p) for p in (drill.participants or [])],
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
