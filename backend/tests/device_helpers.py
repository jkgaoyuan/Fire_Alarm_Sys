"""
3.2 设备档案测试共用工具

构造组织架构 / 设备类型 / 带权限用户，并生成认证头。
"""

from uuid import uuid4

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.device import Device
from app.models.device_type import DeviceType
from app.models.organization import Organization
from app.models.user import User
from tests.auth_helpers import create_user_with_perms

ALL_DEVICE_PERMS = [
    "device:view",
    "device:create",
    "device:update",
    "device:delete",
    "device:retire",
]


async def create_org(db, org_name: str, parent: Organization | None = None) -> Organization:
    """创建一个组织节点"""
    org = Organization(
        org_name=org_name,
        org_type="floor" if parent else "building",
        parent_id=parent.id if parent else None,
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


async def make_device(
    db,
    *,
    org_id: int,
    device_code: str | None = None,
    device_name: str = "测试设备",
) -> Device:
    """
    建一台设备（绕过 API 直接落库，只为给其它域提供 device_id 外键）。

    原先定义在 `tests/repair_helpers.py`，但巡检记录同样需要它——设备是跨域
    共用对象，放在设备域 helper 里，各域直接 import，不必跨域引用。
    `repair_helpers` 保留同名再导出，既有调用方不受影响。
    """
    device = Device(
        device_code=device_code or f"DEV-{uuid4().hex[:8].upper()}",
        device_name=device_name,
        org_id=org_id,
        status="normal",
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


async def create_device_type(
    db,
    type_code: str = "smoke_detector",
    type_name: str = "烟感探测器",
    attribute_schema: dict | None = None,
) -> DeviceType:
    """创建一个设备类型"""
    device_type = DeviceType(
        type_code=type_code,
        type_name=type_name,
        category="detector",
        attribute_schema=attribute_schema
        or {
            "sensitivity": {
                "label": "灵敏度",
                "type": "select",
                "options": ["高", "中", "低"],
            },
            "detection_area": {"label": "探测面积(㎡)", "type": "number"},
        },
    )
    db.add(device_type)
    await db.commit()
    await db.refresh(device_type)
    return device_type


async def create_device_user(
    db,
    username: str = "deviceuser",
    perm_codes: list[str] | None = None,
    data_scope: str = "all",
    org: Organization | None = None,
) -> User:
    """
    创建绑定指定设备权限码的用户（一次性建图后提交，避免异步懒加载）。

    实现已并入 tests/auth_helpers.py——这原本是全仓库第四份几乎相同的
    `make_xxx_user`。保留本函数作为设备域入口，调用方不必改；
    默认密码与 perm_type 沿用设备域原有的取值。
    """
    return await create_user_with_perms(
        db,
        username,
        perm_codes,
        data_scope=data_scope,
        org=org,
        password="Device1234",
        perm_type="button",
    )


def auth_headers(user: User) -> dict:
    """生成 Bearer 认证头"""
    token = create_access_token(data={"sub": str(user.id), "jti": f"jti-{user.id}"})
    return {"Authorization": f"Bearer {token}"}


def device_payload(type_id: int, org_id: int, code: str = "DEV-001") -> dict:
    """创建设备请求体"""
    return {
        "device_code": code,
        "device_name": "1F大厅烟感A01",
        "type_id": type_id,
        "org_id": org_id,
        "manufacturer": "霍尼韦尔",
        "model": "XLS-PS",
        "brand": "Honeywell",
        "install_date": "2025-03-15",
        "warranty_expire_date": "2028-03-15",
        "maintain_cycle": 90,
        "status": "normal",
        "map_x": 120.5,
        "map_y": 340.2,
        "attributes": {"sensitivity": "高", "detection_area": 60},
    }
