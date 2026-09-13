"""
鉴权测试的通用构造器。

仓库里已经有三份几乎相同的 `make_xxx_user(db, username, perm_codes)`：
`test_api_contract_regressions.make_user_with_perms`、
`inspection_helpers.create_inspection_user`、以及本模块。新建测试请用这里的版本，
不要再抄第四份。

（那两份历史副本暂未合并——它们各自嵌在已交付的测试里，合并属独立清理，
不夹在功能迁移中间做。）
"""

from app.core.security import create_access_token, get_password_hash
from app.models.permission import Permission
from app.models.user import Role, User


async def create_user_with_perms(
    db,
    username: str,
    perm_codes: list[str],
    *,
    data_scope: str = "all",
    org_id: int | None = None,
    password: str = "Test1234",
) -> User:
    """
    建一个只持有指定权限码的用户。

    角色与权限的关联必须在 flush **之前**完成，否则异步会话下
    `role.permissions` 会触发懒加载并抛 MissingGreenlet
    （testing-guidelines 第六节第 16 条）。
    """
    role = Role(role_code=f"{username}_role", role_name=username, is_builtin=False)
    for code in perm_codes:
        role.permissions.append(
            Permission(perm_code=code, perm_name=code, perm_type="api")
        )
    db.add(role)
    await db.flush()

    user = User(
        username=username,
        password_hash=get_password_hash(password),
        real_name=username,
        status="active",
        data_scope=data_scope,
        org_id=org_id,
    )
    user.roles.append(role)
    db.add(user)
    await db.commit()
    await db.refresh(user, ["roles"])
    return user


def auth_headers(user: User) -> dict:
    """该用户的 Authorization 头"""
    token = create_access_token(data={"sub": str(user.id), "jti": f"jti-{user.id}"})
    return {"Authorization": f"Bearer {token}"}
