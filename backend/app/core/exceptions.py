"""
自定义异常类
统一认证与权限相关异常
"""

from datetime import datetime


class AuthError(Exception):
    """认证基础异常"""

    def __init__(
        self,
        code: int,
        message: str,
        data: dict | None = None,
    ):
        self.code = code
        self.message = message
        self.data = data or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "data": self.data,
            "timestamp": int(datetime.utcnow().timestamp()),
        }


class PermissionDenied(AuthError):
    """权限不足"""

    def __init__(self, message: str = "无权限访问", data: dict | None = None):
        super().__init__(403, message, data)


class AccountLocked(AuthError):
    """账户已锁定"""

    def __init__(self, locked_until: datetime | None = None):
        data = {}
        if locked_until:
            from app.core.security import utc_to_cst_iso
            data["locked_until"] = utc_to_cst_iso(locked_until)
        super().__init__(4003, "账户已锁定", data)
