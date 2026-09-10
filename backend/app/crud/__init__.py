"""
CRUD 模块导出
"""

from app.crud.alarm import alarm_crud
from app.crud.device import device_crud
from app.crud.inspection import (
    inspection_plan_crud,
    inspection_task_crud,
    inspection_record_crud,
)
from app.crud.login_log import login_log_crud
from app.crud.role import role_crud
from app.crud.user import user_crud

__all__ = [
    "user_crud",
    "role_crud",
    "login_log_crud",
    "device_crud",
    "alarm_crud",
    # 3.6 巡检模块新增
    "inspection_plan_crud",
    "inspection_task_crud",
    "inspection_record_crud",
]
