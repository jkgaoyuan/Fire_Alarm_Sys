"""
消防演练模块数据库模型（3.8 FR-043）
=====================================
对应 PRD 章节：3.8 消防演练
模型清单：
1. DrillEvent - 演练事件主表
2. DrillEvaluation - 演练评估表
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    DateTime,
    Enum as SQLEnum,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.models.base import Base
from app.schemas.drill import DrillStatus, DrillType


class DrillEvent(Base):
    """
    演练事件主表
    对应表名：drill_events
    """
    
    __tablename__ = "drill_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="演练 ID")
    drill_name = Column(String(200), nullable=False, comment="演练名称")
    drill_type = Column(SQLEnum(DrillType), nullable=False, comment="演练类型")
    status = Column(SQLEnum(DrillStatus), default=DrillStatus.planned, comment="演练状态")

    # 计划信息
    planned_at = Column(DateTime, comment="计划执行时间")
    # ⚠️ 以下 5 列曾与代码/迁移长期漂移：模型里只有一个幻影列 `actual_at`，
    #    而 drills.py / schemas / 前端 / 建表迁移一致使用
    #    actual_start_at / actual_end_at / summary / photos / videos。
    #    后果是 `POST /drills` 在生产环境必然 500（AttributeError），
    #    「新增消防演练」整条链路不可用。已于 2026-09-16 对齐，
    #    并由迁移 `align_drill_columns` 把线上库补齐。
    actual_start_at = Column(DateTime, comment="实际开始时间")
    actual_end_at = Column(DateTime, comment="实际结束时间")
    location = Column(String(500), comment="演练地点")
    summary = Column(Text, comment="现场总结记录")
    photos = Column(JSON, comment="现场照片 [{url, caption}]")
    videos = Column(JSON, comment="现场视频 [{url, duration}]")

    # 参与人员配置（JSON 格式存储）
    # [
    #   {"user_id": 1, "role": "参与者", "sign_in_at": null},
    #   {"user_id": 2, "role": "指挥员", "sign_in_at": "2026-09-11 10:00:00"}
    # ]
    participants = Column(JSON, comment="参与人员列表")

    # 元数据
    created_by = Column(Integer, nullable=False, comment="创建人用户 ID")
    # 注：线上库还留着一个遗留列 `updated_by`（当前 ORM 与迁移均不使用）。
    # 不在此声明、也不在迁移里删除 —— 删列不可逆且无功能收益。
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 与评估的 1:1 关系（OQ-4）。此关系存在的**唯一目的**是把「删演练要连带删评估」
    # 写成 ORM 可读的声明 —— 此前 `drill_crud.delete` 的 docstring 声称
    # 「ORM 级联删除评估」，但模型里根本没有 relationship，于是评估行被留下成为孤儿，
    # 而 `get_stats` 的 `avg(total_score)` 不 join 演练表，孤儿分数继续污染平均分。
    #
    # `passive_deletes` 刻意**不开**：开了会让 ORM 不加载子行、只依赖数据库的
    # ON DELETE CASCADE，而测试库是 SQLite —— **SQLite 默认不强制外键**，
    # 于是级联在测试里根本不发生（实测：开了这个开关，`test_delete_drill_cascades_evaluation`
    # 仍红）。保持 ORM 显式级联，两个数据库都生效；数据库层的
    # `ondelete="CASCADE"` 作为绕过 ORM 的删除路径的兜底。
    evaluation = relationship(
        "DrillEvaluation",
        back_populates="drill",
        uselist=False,
        cascade="all, delete-orphan",
    )


class DrillEvaluation(Base):
    """
    演练评估表
    对应表名：drill_evaluations
    """
    
    __tablename__ = "drill_evaluations"

    # 唯一约束：`drill_id` 与演练 1:1（OQ-4）。此前只有应用层的 check-then-act
    # 守卫（`submit_evaluation` 先查后建 → 400），数据库没有兜底 —— 并发下两个请求
    # 可以都通过检查、各插一行，而 `get_by_drill_id` 用的是 `scalar_one_or_none()`，
    # 两行同 drill_id 会抛 MultipleResultsFound，**该演练的详情页从此永久 500
    # 且界面上没有任何删除评估的入口**。约束名与建表迁移里声明的一致。
    __table_args__ = (
        UniqueConstraint("drill_id", name="uq_drill_evaluations_drill_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="评估 ID")
    drill_id = Column(
        Integer,
        ForeignKey("drill_events.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联演练 ID",
    )
    drill = relationship("DrillEvent", back_populates="evaluation")

    # 评估内容（JSON 格式存储）
    # [
    #   {"item": "response_time", "label": "响应时间", "score": 8, "max_score": 10, "comment": "优秀"},
    #   ...
    # ]
    items = Column(JSON, nullable=False, comment="评估项打分列表")
    
    # 文本评价
    problems = Column(Text, comment="存在问题")
    improvements = Column(Text, comment="改进措施")
    evaluation_summary = Column(String(1000), comment="总体评估摘要")
    
    # 元数据
    # 同上：代码/schema/迁移统一使用 evaluator_id 与 total_score，
    # 模型此前是 evaluated_by 且缺 total_score，导致评估写入与统计端点坏掉。
    evaluator_id = Column(Integer, nullable=False, comment="评估人用户 ID")
    total_score = Column(Integer, comment="总分（各评估项得分之和）")
    evaluated_at = Column(DateTime, default=datetime.utcnow, comment="评估时间")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
