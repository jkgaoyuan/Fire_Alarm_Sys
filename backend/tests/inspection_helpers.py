"""
巡检域测试构造器（testing-guidelines 第三节：域内构造器放 tests/<域>_helpers.py）

不要在用例里手写 User(...) / InspectionPlan(...) 字面量，字段一多必然与模型漂移。
`create_org` 直接复用 device_helpers 的同名实现——组织树是跨域共用的，不该复制第二份。
"""
from datetime import date

from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.inspection import InspectionPlan, InspectionTask
from app.models.permission import Permission
from app.models.user import Role, User
from tests.device_helpers import create_org  # noqa: F401  （对外再导出，用例只 import 本模块）

INSPECTION_VIEW_PERM = "inspection:view"


async def create_inspection_user(
    db,
    username: str,
    perm_codes: list[str] | None = None,
    data_scope: str = "all",
    org=None,
) -> User:
    """
    创建绑定指定巡检权限码的用户。

    角色与权限的关联必须在 flush 之前完成，否则异步会话下 `role.permissions`
    会触发懒加载并抛 MissingGreenlet（testing-guidelines 第六节第 16 条）。
    """
    role = Role(role_code=f"role_{username}", role_name=username, is_builtin=False)
    for code in perm_codes or []:
        perm = (
            await db.execute(select(Permission).where(Permission.perm_code == code))
        ).scalar_one_or_none()
        if perm is None:
            perm = Permission(perm_code=code, perm_name=code, perm_type="button")
            db.add(perm)
        role.permissions.append(perm)

    user = User(
        username=username,
        password_hash=get_password_hash("Inspect1234"),
        real_name=username,
        status="active",
        data_scope=data_scope,
        org_id=org.id if org else None,
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


async def make_plan(
    db,
    *,
    plan_name: str,
    org_id: int | None = None,
    responsible_user_id: int | None = None,
    cycle_type: str = "daily",
    is_enabled: bool = True,
    start_date: date | None = None,
    end_date: date | None = None,
) -> InspectionPlan:
    """
    建一条巡检计划（绕过 API，直接落库）。

    `start_date` 默认今天；传 `end_date` 可限定计划有效期
    （自动生成会尊重这个窗口，见 `generate_daily_tasks`）。
    """
    plan = InspectionPlan(
        plan_name=plan_name,
        org_id=org_id,
        responsible_user_id=responsible_user_id,
        cycle_type=cycle_type,
        start_date=start_date or date.today(),
        end_date=end_date,
        is_enabled=is_enabled,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


async def make_task(
    db,
    *,
    plan_id: int,
    responsible_user_id: int | None,
    task_date: date | None = None,
    status: str = "pending",
) -> InspectionTask:
    """建一条巡检任务（绕过 API，直接落库）"""
    task = InspectionTask(
        plan_id=plan_id,
        task_date=task_date or date.today(),
        responsible_user_id=responsible_user_id,
        status=status,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


def task_ids(body: dict) -> set[int]:
    """从列表响应信封里取出任务 id 集合"""
    return {item["id"] for item in body["data"]["items"]}
