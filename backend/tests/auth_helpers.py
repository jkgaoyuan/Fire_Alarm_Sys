"""
鉴权测试的通用构造器。

仓库里已经有三份几乎相同的 `make_xxx_user(db, username, perm_codes)`：
`test_api_contract_regressions.make_user_with_perms`、
`inspection_helpers.create_inspection_user`、以及本模块。新建测试请用这里的版本，
不要再抄第四份。

（那两份历史副本暂未合并——它们各自嵌在已交付的测试里，合并属独立清理，
不夹在功能迁移中间做。）
"""

from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.permission import Permission
from app.models.user import Role, User


async def create_user_with_perms(
    db,
    username: str,
    perm_codes: list[str] | None = None,
    *,
    data_scope: str = "all",
    org=None,
    org_id: int | None = None,
    password: str = "Test1234",
    perm_type: str = "api",
) -> User:
    """
    建一个只持有指定权限码的用户。

    角色与权限的关联必须在 flush **之前**完成，否则异步会话下
    `role.permissions` 会触发懒加载并抛 MissingGreenlet
    （testing-guidelines 第六节第 16 条）。

    `org`（组织对象）与 `org_id` 二者传其一即可——历史副本里两种写法都有，
    统一后都接受，免得调用方为了换个函数就改一片。

    **权限码先查再建**：`permissions.perm_code` 有唯一约束，而一个用例里常常
    建多个共享同一权限码的用户（如数据范围用例建 4 个都带 inspection:view）。
    无条件 `Permission(...)` 会在第二个用户上撞约束。
    两份历史副本里只有一份做对了这件事，合并时按对的那份来。
    """
    role = Role(role_code=f"{username}_role", role_name=username, is_builtin=False)
    for code in perm_codes or []:
        perm = (
            await db.execute(select(Permission).where(Permission.perm_code == code))
        ).scalar_one_or_none()
        if perm is None:
            perm = Permission(perm_code=code, perm_name=code, perm_type=perm_type)
            db.add(perm)
        role.permissions.append(perm)
    db.add(role)
    await db.flush()

    user = User(
        username=username,
        password_hash=get_password_hash(password),
        real_name=username,
        status="active",
        data_scope=data_scope,
        org_id=org.id if org is not None else org_id,
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
