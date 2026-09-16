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
    Integer,
    String,
    Text,
    DateTime,
    Enum as SQLEnum,
    JSON,
)
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


class DrillEvaluation(Base):
    """
    演练评估表
    对应表名：drill_evaluations
    """
    
    __tablename__ = "drill_evaluations"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="评估 ID")
    drill_id = Column(Integer, nullable=False, comment="关联演练 ID")
    
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
