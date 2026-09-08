"""
服务导出入口
"""

from app.services.auth_service import (
    authenticate_user,
    create_token_pair,
    is_account_locked,
    login_user,
    logout_user,
    record_login_log,
    refresh_access_token,
    save_token_whitelist,
)
from app.services.permission_service import (
    build_menu_tree,
    get_permission_tree,
    get_user_permissions,
)
from app.services.role_service import (
    bind_permissions,
    create_role,
    delete_role,
    get_role_permissions,
    get_roles_with_pagination,
    update_role,
)
from app.services.user_service import apply_data_scope, get_user_with_roles

__all__ = [
    "authenticate_user",
    "create_token_pair",
    "is_account_locked",
    "login_user",
    "logout_user",
    "record_login_log",
    "refresh_access_token",
    "save_token_whitelist",
    "build_menu_tree",
    "get_user_permissions",
    "get_permission_tree",
    "get_user_with_roles",
    "apply_data_scope",
    "create_role",
    "update_role",
    "delete_role",
    "get_role_permissions",
    "bind_permissions",
    "get_roles_with_pagination",
]
