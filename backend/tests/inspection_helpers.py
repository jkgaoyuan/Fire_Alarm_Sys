"""
巡检域测试构造器（testing-guidelines 第三节：域内构造器放 tests/<域>_helpers.py）

不要在用例里手写 User(...) / InspectionPlan(...) 字面量，字段一多必然与模型漂移。
`create_org` 直接复用 device_helpers 的同名实现——组织树是跨域共用的，不该复制第二份。
"""
from datetime import date

from app.models.inspection import InspectionPlan, InspectionTask
from tests.auth_helpers import auth_headers, create_user_with_perms  # noqa: F401
from tests.device_helpers import create_org  # noqa: F401  （对外再导出，用例只 import 本模块）

INSPECTION_VIEW_PERM = "inspection:view"


async def create_inspection_user(
    db,
    username: str,
    perm_codes: list[str] | None = None,
    data_scope: str = "all",
    org=None,
):
    """
    建一个绑定指定巡检权限码的用户。

    实现已并入 tests/auth_helpers.py（原先这里是与
    test_api_contract_regressions.make_user_with_perms 几乎逐行相同的副本）。
    保留本函数作为域内入口，调用方不必改。
    """
    return await create_user_with_perms(
        db, username, perm_codes, data_scope=data_scope, org=org
    )


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
