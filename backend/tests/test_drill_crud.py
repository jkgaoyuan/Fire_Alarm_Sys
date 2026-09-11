"""
消防演练模块后端单元测试（3.8-B5）
=====================================
测试范围：
- DrillEvent CRUD: 创建/查询/更新/删除
- DrillEvaluation CRUD: 提交评估 + 分数计算 + 唯一约束
- 状态流转：planned -> ongoing -> completed / cancelled
- 参与人员管理：添加/签到
- 统计功能
- 服务层边界条件：不存在演练/非法流转/重复评估
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drill import DrillEvent, DrillEvaluation, DrillStatus, DrillType
from app.schemas.drill import EvaluationItem
from app.crud.drill_crud import drill_crud, eval_crud
from app.services.drill_service import drill_service


# ==================== 测试 fixtures ====================

@pytest.fixture
def drill_params():
    """演练创建参数（匹配 drill_crud.create 签名）"""
    return {
        "drill_name": "2026 年度夏季疏散演练",
        "drill_type": DrillType.evacuation,
        "planned_at": datetime.now() + timedelta(days=7),
        "location": "办公楼 3 层全体区域",
        "participant_user_ids": [1, 2, 3],
        "status": DrillStatus.planned,
        "created_by": 1,
    }


@pytest.fixture
def evaluation_items():
    """评估项样本数据"""
    return [
        EvaluationItem(item="response_time", label="响应时间", score=9, max_score=10, comment="报警确认后 2 分钟内启动"),
        EvaluationItem(item="evacuation_efficiency", label="疏散效率", score=8, max_score=10, comment="全员撤离用时 28 分钟"),
        EvaluationItem(item="equipment_linkage", label="设备联动", score=10, max_score=10, comment="联动正常"),
        EvaluationItem(item="personnel_cooperation", label="人员配合", score=9, max_score=10, comment="指挥有序"),
    ]


# ==================== 测试 DrillEvent CRUD ====================

class TestDrillEventCRUD:
    """DrillEvent CRUD 操作测试"""

    async def test_create_drill(self, db_session: AsyncSession, drill_params):
        """测试创建演练事件"""
        drill = await drill_crud.create(db_session, **drill_params)

        assert drill is not None
        assert drill.id is not None
        assert drill.drill_name == drill_params["drill_name"]
        assert drill.drill_type == "evacuation"
        assert drill.status == "planned"
        assert len(drill.participants) == 3

    async def test_get_by_id(self, db_session: AsyncSession, drill_params):
        """测试根据 ID 查询演练"""
        drill = await drill_crud.create(db_session, **drill_params)
        retrieved = await drill_crud.get(db_session, drill.id)

        assert retrieved is not None
        assert retrieved.id == drill.id
        assert retrieved.drill_name == drill.drill_name

    async def test_get_nonexistent(self, db_session: AsyncSession):
        """查询不存在的演练返回 None"""
        assert await drill_crud.get(db_session, 99999) is None

    async def test_get_list_with_filters(self, db_session: AsyncSession):
        """测试演练列表查询与筛选"""
        for i in range(5):
            await drill_crud.create(
                db_session,
                drill_name=f"演练{i}",
                drill_type=DrillType.evacuation if i % 2 == 0 else DrillType.comprehensive,
                status=DrillStatus.completed if i < 3 else DrillStatus.planned,
                created_by=1,
            )

        # 查询全部
        all_drills, total = await drill_crud.get_list(db_session, skip=0, limit=50)
        assert total == 5
        assert len(all_drills) == 5

        # 按状态筛选
        planned_drills, count = await drill_crud.get_list(
            db_session, skip=0, limit=50, status_filter=DrillStatus.planned
        )
        assert count == 2
        assert all(d.status == "planned" for d in planned_drills)

        # 按类型筛选
        evacuation_drills, count = await drill_crud.get_list(
            db_session, skip=0, limit=50, drill_type_filter=DrillType.evacuation
        )
        assert count == 3

    async def test_get_list_pagination(self, db_session: AsyncSession):
        """测试分页查询"""
        for i in range(10):
            await drill_crud.create(
                db_session,
                drill_name=f"演练{i}",
                drill_type=DrillType.evacuation,
                created_by=1,
            )

        page1, total = await drill_crud.get_list(db_session, skip=0, limit=5)
        page2, _ = await drill_crud.get_list(db_session, skip=5, limit=5)
        assert total == 10
        assert len(page1) == 5
        assert len(page2) == 5
        # 两页无重复
        ids1 = {d.id for d in page1}
        ids2 = {d.id for d in page2}
        assert not (ids1 & ids2)

    async def test_update_drill(self, db_session: AsyncSession, drill_params):
        """测试更新演练信息"""
        drill = await drill_crud.create(db_session, **drill_params)

        updated = await drill_crud.update(
            db_session, drill.id,
            drill_name="更新后的演练名称",
            summary="本次演练总体顺利",
        )

        assert updated is not None
        assert updated.drill_name == "更新后的演练名称"
        assert updated.summary == "本次演练总体顺利"

    async def test_update_nonexistent(self, db_session: AsyncSession):
        """更新不存在的演练返回 None"""
        result = await drill_crud.update(db_session, 99999, drill_name="xxx")
        assert result is None

    async def test_delete_drill(self, db_session: AsyncSession, drill_params):
        """测试删除演练"""
        drill = await drill_crud.create(db_session, **drill_params)
        success = await drill_crud.delete(db_session, drill.id)

        assert success is True
        assert await drill_crud.get(db_session, drill.id) is None

    async def test_delete_drill_cascades_evaluation(
        self, db_session: AsyncSession, drill_params, evaluation_items
    ):
        """删除演练时级联删除评估"""
        from sqlalchemy import select

        drill = await drill_crud.create(db_session, **drill_params)
        await eval_crud.create(
            db_session,
            drill_id=drill.id,
            evaluator_id=1,
            items=evaluation_items,
        )

        await drill_crud.delete(db_session, drill.id)

        result = await db_session.execute(
            select(DrillEvaluation).where(DrillEvaluation.drill_id == drill.id)
        )
        assert result.scalar_one_or_none() is None


# ==================== 测试 DrillEvaluation CRUD ====================

class TestEvaluationCRUD:
    """DrillEvaluation CRUD 操作测试"""

    async def test_create_evaluation(
        self, db_session: AsyncSession, drill_params, evaluation_items
    ):
        """测试创建评估（总分自动计算）"""
        drill = await drill_crud.create(db_session, **drill_params)

        evaluation = await eval_crud.create(
            db_session,
            drill_id=drill.id,
            evaluator_id=1,
            items=evaluation_items,
        )

        assert evaluation is not None
        assert evaluation.drill_id == drill.id
        assert evaluation.total_score == sum(i.score for i in evaluation_items)

    async def test_unique_constraint_drill_id(
        self, db_session: AsyncSession, drill_params, evaluation_items
    ):
        """测试 drill_id 唯一性约束（每个演练只能有一个评估）"""
        from sqlalchemy.exc import IntegrityError

        drill = await drill_crud.create(db_session, **drill_params)

        await eval_crud.create(
            db_session, drill_id=drill.id, evaluator_id=1, items=evaluation_items
        )
        await db_session.commit()

        # 第二次创建应违反唯一约束
        with pytest.raises(IntegrityError):
            await eval_crud.create(
                db_session, drill_id=drill.id, evaluator_id=2, items=evaluation_items
            )
            await db_session.commit()
        await db_session.rollback()

    async def test_get_by_drill_id(
        self, db_session: AsyncSession, drill_params, evaluation_items
    ):
        """测试按演练 ID 查询评估"""
        drill = await drill_crud.create(db_session, **drill_params)
        await eval_crud.create(
            db_session, drill_id=drill.id, evaluator_id=1, items=evaluation_items
        )

        evaluation = await eval_crud.get_by_drill_id(db_session, drill.id)
        assert evaluation is not None
        assert evaluation.drill_id == drill.id

    async def test_update_evaluation_recalculates_score(
        self, db_session: AsyncSession, drill_params, evaluation_items
    ):
        """测试更新评估项后重新计算总分"""
        drill = await drill_crud.create(db_session, **drill_params)
        evaluation = await eval_crud.create(
            db_session, drill_id=drill.id, evaluator_id=1, items=evaluation_items[:2]
        )
        original_score = evaluation.total_score

        new_items = evaluation_items[:3]
        updated = await eval_crud.update(db_session, evaluation.id, items=new_items)

        assert updated.total_score == sum(i.score for i in new_items)
        assert updated.total_score != original_score


# ==================== 测试状态流转 ====================

class TestDrillStatusFlow:
    """演练状态流转测试"""

    async def test_execute_drill(self, db_session: AsyncSession, drill_params):
        """测试开始执行演练（planned → ongoing）"""
        drill = await drill_crud.create(db_session, **drill_params)

        executed = await drill_service.execute_drill(
            db_session, drill_id=drill.id, actual_start_at=datetime.now()
        )

        assert executed.status == "ongoing"
        assert executed.actual_start_at is not None

    async def test_complete_drill(self, db_session: AsyncSession, drill_params):
        """测试完成演练（ongoing → completed）"""
        drill = await drill_crud.create(db_session, **drill_params)
        await drill_service.execute_drill(
            db_session, drill_id=drill.id, actual_start_at=datetime.now()
        )

        completed = await drill_service.complete_drill(
            db_session,
            drill_id=drill.id,
            summary="演练按计划完成，参与人数 50 人，用时 30 分钟",
        )

        assert completed.status == "completed"
        assert "参与人数 50 人" in completed.summary
        assert completed.actual_end_at is not None

    async def test_cancel_drill(self, db_session: AsyncSession, drill_params):
        """测试取消演练（planned → cancelled）"""
        drill = await drill_crud.create(db_session, **drill_params)

        cancelled = await drill_service.cancel_drill(
            db_session, drill_id=drill.id, reason="天气原因取消"
        )

        assert cancelled.status == "cancelled"
        assert "天气原因取消" in cancelled.summary

    async def test_invalid_transition_completed_cannot_cancel(
        self, db_session: AsyncSession, drill_params
    ):
        """测试非法状态流转（completed 不能取消）"""
        drill = await drill_crud.create(db_session, **drill_params)
        await drill_service.execute_drill(
            db_session, drill_id=drill.id, actual_start_at=datetime.now()
        )
        await drill_service.complete_drill(
            db_session, drill_id=drill.id, summary="已完成"
        )

        with pytest.raises(ValueError, match="已完成"):
            await drill_service.cancel_drill(db_session, drill_id=drill.id)

    async def test_invalid_transition_planned_cannot_complete(
        self, db_session: AsyncSession, drill_params
    ):
        """测试非法状态流转（planned 不能直接完成）"""
        drill = await drill_crud.create(db_session, **drill_params)

        with pytest.raises(ValueError, match="执行中"):
            await drill_service.complete_drill(
                db_session, drill_id=drill.id, summary="直接完成"
            )

    async def test_invalid_transition_ongoing_cannot_execute(
        self, db_session: AsyncSession, drill_params
    ):
        """测试非法状态流转（ongoing 不能再次开始执行）"""
        drill = await drill_crud.create(db_session, **drill_params)
        await drill_service.execute_drill(
            db_session, drill_id=drill.id, actual_start_at=datetime.now()
        )

        with pytest.raises(ValueError, match="无法开始执行"):
            await drill_service.execute_drill(
                db_session, drill_id=drill.id, actual_start_at=datetime.now()
            )


# ==================== 测试参与人员管理 ====================

class TestParticipantManagement:
    """参与人员管理测试"""

    async def test_add_participant(self, db_session: AsyncSession, drill_params):
        """测试添加参与人员"""
        drill = await drill_crud.create(db_session, **drill_params)
        initial_count = len(drill.participants)

        updated = await drill_crud.add_participant(
            db_session, drill_id=drill.id, user_id=999, role="指挥员"
        )

        assert updated is not None
        assert len(updated.participants) == initial_count + 1
        new_p = next(p for p in updated.participants if p["user_id"] == 999)
        assert new_p["role"] == "指挥员"

    async def test_add_duplicate_participant_updates_role(
        self, db_session: AsyncSession, drill_params
    ):
        """测试添加已存在参与人员时更新角色而非重复添加"""
        drill = await drill_crud.create(db_session, **drill_params)
        existing_uid = drill.participants[0]["user_id"]
        initial_count = len(drill.participants)

        updated = await drill_crud.add_participant(
            db_session, drill_id=drill.id, user_id=existing_uid, role="疏散员"
        )

        assert len(updated.participants) == initial_count  # 未新增
        target = next(p for p in updated.participants if p["user_id"] == existing_uid)
        assert target["role"] == "疏散员"

    async def test_sign_in(self, db_session: AsyncSession, drill_params):
        """测试参与人员签到"""
        drill = await drill_crud.create(db_session, **drill_params)
        user_id = drill.participants[0]["user_id"]

        updated = await drill_crud.sign_in(
            db_session, drill_id=drill.id, user_id=user_id
        )

        assert updated is not None
        participant = next(p for p in updated.participants if p["user_id"] == user_id)
        assert participant["sign_in_at"] is not None

    async def test_sign_in_nonexistent_user(self, db_session: AsyncSession, drill_params):
        """测试未配置人员的签到应失败"""
        drill = await drill_crud.create(db_session, **drill_params)

        result = await drill_crud.sign_in(
            db_session, drill_id=drill.id, user_id=99999
        )
        assert result is None

    async def test_add_participant_nonexistent_drill(self, db_session: AsyncSession):
        """对不存在的演练添加参与人员返回 None"""
        result = await drill_crud.add_participant(
            db_session, drill_id=99999, user_id=1, role="参与者"
        )
        assert result is None


# ==================== 测试统计功能 ====================

class TestStatistics:
    """统计数据测试"""

    async def test_get_drill_statistics(self, db_session: AsyncSession):
        """测试演练统计"""
        for i in range(10):
            status = DrillStatus.completed if i < 8 else DrillStatus.planned
            await drill_crud.create(
                db_session,
                drill_name=f"演练{i}",
                drill_type=DrillType.evacuation,
                status=status,
                created_by=1,
            )

        stats = await drill_crud.get_stats(db_session)

        assert stats["total_drills"] == 10
        assert stats["completed_drills"] == 8
        assert stats["completion_rate"] == 80.0

    async def test_statistics_empty_db(self, db_session: AsyncSession):
        """空库统计不应报错"""
        stats = await drill_crud.get_stats(db_session)
        assert stats["total_drills"] == 0
        assert stats["completion_rate"] == 0.0
        assert stats["avg_score"] == 0.0


# ==================== 测试服务层边界条件 ====================

class TestServiceBoundaryConditions:
    """服务层边界条件测试"""

    async def test_execute_nonexistent_drill(self, db_session: AsyncSession):
        """测试执行不存在的演练"""
        with pytest.raises(ValueError, match="演练不存在"):
            await drill_service.execute_drill(
                db_session, drill_id=99999, actual_start_at=datetime.now()
            )

    async def test_complete_nonexistent_drill(self, db_session: AsyncSession):
        """测试完成不存在的演练"""
        with pytest.raises(ValueError, match="演练不存在"):
            await drill_service.complete_drill(
                db_session, drill_id=99999, summary="总结"
            )

    async def test_submit_duplicate_evaluation(
        self, db_session: AsyncSession, drill_params, evaluation_items
    ):
        """测试重复提交评估应拒绝"""
        drill = await drill_crud.create(db_session, **drill_params)

        await drill_service.submit_evaluation(
            db_session,
            drill_id=drill.id,
            evaluator_id=1,
            items=evaluation_items,
        )

        with pytest.raises(ValueError, match="请勿重复提交"):
            await drill_service.submit_evaluation(
                db_session,
                drill_id=drill.id,
                evaluator_id=2,
                items=evaluation_items,
            )

    async def test_submit_evaluation_nonexistent_drill(
        self, db_session: AsyncSession, evaluation_items
    ):
        """对不存在的演练提交评估应报错"""
        with pytest.raises(ValueError, match="演练不存在"):
            await drill_service.submit_evaluation(
                db_session,
                drill_id=99999,
                evaluator_id=1,
                items=evaluation_items,
            )


# ==================== 测试报告生成 ====================

class TestReportGeneration:
    """HTML 报告生成测试"""

    async def test_generate_report_html(
        self, db_session: AsyncSession, drill_params, evaluation_items
    ):
        """测试生成 HTML 报告（含评估）"""
        drill = await drill_crud.create(db_session, **drill_params)
        await drill_service.submit_evaluation(
            db_session,
            drill_id=drill.id,
            evaluator_id=1,
            items=evaluation_items,
            problems="疏散时对讲机信号不足",
            improvements="增加备用通讯设备",
            evaluation_summary="总体表现良好，细节待改进",
        )

        html = await drill_service.generate_report_html(db_session, drill.id)

        assert "消防演练评估报告" in html
        assert drill.drill_name in html
        assert str(evaluation_items[0].score) in html
        assert "疏散时对讲机信号不足" in html
        assert "增加备用通讯设备" in html
        assert "总体表现良好" in html
        assert "window.print()" in html  # 前端打印入口

    async def test_generate_report_html_without_evaluation(
        self, db_session: AsyncSession, drill_params
    ):
        """测试无评估时生成报告（占位提示）"""
        drill = await drill_crud.create(db_session, **drill_params)
        html = await drill_service.generate_report_html(db_session, drill.id)

        assert "暂无评估数据" in html

    async def test_generate_report_nonexistent(self, db_session: AsyncSession):
        """测试生成不存在演练的报告"""
        with pytest.raises(ValueError, match="演练不存在"):
            await drill_service.generate_report_html(db_session, 99999)
