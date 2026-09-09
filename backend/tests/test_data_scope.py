"""
数据权限过滤单元测试
验证 apply_data_scope 的三种范围过滤正确性
"""

import pytest
from sqlalchemy import Column, ForeignKey, Integer, String, select

from app.models.base import Base
from app.models.organization import Organization
from app.models.user import User
from app.services.user_service import apply_data_scope


# 定义测试用 mock 设备表（添加到 Base.metadata，会被 db_engine fixture 自动建表）
class MockDevice(Base):
    __tablename__ = "test_devices"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)


@pytest.mark.asyncio
async def test_data_scope_all(client, db_session):
    """data_scope='all' 返回全部数据"""
    # 创建组织
    org = Organization(org_name="测试中心", org_type="building")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    # 创建用户（all 范围）
    from app.core.security import get_password_hash
    user = User(
        username="all_scope",
        password_hash=get_password_hash("All1234"),
        org_id=org.id,
        data_scope="all",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 插入 mock 数据
    dev1 = MockDevice(name="设备A", org_id=org.id, created_by=user.id)
    dev2 = MockDevice(name="设备B", org_id=None, created_by=None)
    db_session.add(dev1)
    db_session.add(dev2)
    await db_session.commit()

    query = select(MockDevice)
    filtered = await apply_data_scope(query, user, db_session)
    result = await db_session.execute(filtered)
    items = result.scalars().all()

    assert len(items) == 2


@pytest.mark.asyncio
async def test_data_scope_dept(client, db_session):
    """data_scope='dept' 仅返回同部门及子部门数据"""
    from app.core.security import get_password_hash

    # 构建组织架构：父部门 + 子部门
    parent_org = Organization(org_name="消防中心", org_type="building")
    db_session.add(parent_org)
    await db_session.commit()
    await db_session.refresh(parent_org)

    child_org = Organization(org_name="一分队", org_type="zone", parent_id=parent_org.id)
    db_session.add(child_org)
    await db_session.commit()
    await db_session.refresh(child_org)

    other_org = Organization(org_name="其他中心", org_type="building")
    db_session.add(other_org)
    await db_session.commit()
    await db_session.refresh(other_org)

    # 创建用户，所属父部门，数据范围 dept
    user = User(
        username="dept_scope",
        password_hash=get_password_hash("Dept1234"),
        org_id=parent_org.id,
        data_scope="dept",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 插入设备：父部门、子部门、其他部门
    dev_parent = MockDevice(name="父设备", org_id=parent_org.id, created_by=user.id)
    dev_child = MockDevice(name="子设备", org_id=child_org.id, created_by=user.id)
    dev_other = MockDevice(name="其他设备", org_id=other_org.id, created_by=user.id)
    db_session.add(dev_parent)
    db_session.add(dev_child)
    db_session.add(dev_other)
    await db_session.commit()

    query = select(MockDevice)
    filtered = await apply_data_scope(query, user, db_session)
    result = await db_session.execute(filtered)
    items = result.scalars().all()

    names = {d.name for d in items}
    assert "父设备" in names
    assert "子设备" in names
    assert "其他设备" not in names


@pytest.mark.asyncio
async def test_data_scope_self(client, db_session):
    """data_scope='self' 仅返回 created_by = user.id 的数据"""
    from app.core.security import get_password_hash

    org = Organization(org_name="测试中心", org_type="building")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    user_a = User(
        username="self_a",
        password_hash=get_password_hash("SelfA1234"),
        org_id=org.id,
        data_scope="self",
        status="active",
    )
    user_b = User(
        username="self_b",
        password_hash=get_password_hash("SelfB1234"),
        org_id=org.id,
        data_scope="self",
        status="active",
    )
    db_session.add(user_a)
    db_session.add(user_b)
    await db_session.commit()
    await db_session.refresh(user_a)
    await db_session.refresh(user_b)

    # 插入设备：user_a 创建、user_b 创建
    dev_a = MockDevice(name="A的设备", org_id=org.id, created_by=user_a.id)
    dev_b = MockDevice(name="B的设备", org_id=org.id, created_by=user_b.id)
    db_session.add(dev_a)
    db_session.add(dev_b)
    await db_session.commit()

    query = select(MockDevice)
    filtered = await apply_data_scope(query, user_a, db_session)
    result = await db_session.execute(filtered)
    items = result.scalars().all()

    names = {d.name for d in items}
    assert "A的设备" in names
    assert "B的设备" not in names
