"""
Services initialization
"""

# Import services to trigger any registration logic
from app.services.linkage_engine_service import linkage_engine
from app.services.linkage_executor import mock_executor

__all__ = ['linkage_engine', 'mock_executor']
