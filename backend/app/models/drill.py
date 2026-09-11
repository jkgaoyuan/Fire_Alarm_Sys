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
    actual_at = Column(DateTime, comment="实际执行时间")
    location = Column(String(500), comment="演练地点")
    
    # 参与人员配置（JSON 格式存储）
    # [
    #   {"user_id": 1, "role": "参与者", "sign_in_at": null},
    #   {"user_id": 2, "role": "指挥员", "sign_in_at": "2026-09-11 10:00:00"}
    # ]
    participants = Column(JSON, comment="参与人员列表")
    
    # 元数据
    created_by = Column(Integer, nullable=False, comment="创建人用户 ID")
    updated_by = Column(Integer, comment="最后更新人用户 ID")
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
    evaluated_by = Column(Integer, nullable=False, comment="评估人用户 ID")
    evaluated_at = Column(DateTime, default=datetime.utcnow, comment="评估时间")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
