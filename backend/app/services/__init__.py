"""
Services initialization
"""

# Import services to trigger any registration logic
from app.services.linkage_engine_service import linkage_engine
from app.services.linkage_executor import mock_executor
from app.services.inspection_service import InspectionService

__all__ = [
    'linkage_engine', 
    'mock_executor',
    # 3.6 巡检模块新增
    'InspectionService',
]
