"""
用户服务层单元测试
覆盖：get_user_with_roles、apply_data_scope 边界
"""

import pytest
from sqlalchemy import Column, ForeignKey, Integer, String, false, select

from app.models.base import Base
from app.models.organization import Organization
from app.models.user import User
from app.services.user_service import get_user_with_roles, apply_data_scope


# 辅助 mock 模型（用于 apply_data_scope）
class MockDevice(Base):
    __tablename__ = "mock_devices"

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)


# ---------------------------------------------------------------------------
# get_user_with_roles
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_user_with_roles_success(client, db_session):
    """应返回带角色和组织的用户"""
    from app.models.user import Role

    role = Role(role_code="chief", role_name="消防主管")
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    org = Organization(org_name="测试中心", org_type="building")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    user = User(username="u1", password_hash="hash", org_id=org.id)
    user.roles.append(role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    result = await get_user_with_roles(db_session, user.id)
    assert result is not None
    assert result.username == "u1"
    assert len(result.roles) == 1
    assert result.roles[0].role_code == "chief"
    assert result.org is not None
    assert result.org.org_name == "测试中心"


@pytest.mark.asyncio
async def test_get_user_with_roles_not_found(client, db_session):
    """不存在的用户应返回 None"""
    result = await get_user_with_roles(db_session, 99999)
    assert result is None


# ---------------------------------------------------------------------------
# apply_data_scope - all
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_apply_data_scope_all(client, db_session):
    """data_scope='all' 不应修改查询"""
    user = User(username="u", password_hash="hash", data_scope="all")
    query = select(MockDevice)
    filtered = await apply_data_scope(query, user, db_session)
    # 查询应未被修改（与原查询 str 相同）
    assert str(filtered) == str(query)


# ---------------------------------------------------------------------------
# apply_data_scope - self
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_apply_data_scope_self(client, db_session):
    """data_scope='self' 应追加 created_by 条件"""
    user = User(id=42, username="u", password_hash="hash", data_scope="self")
    query = select(MockDevice)
    filtered = await apply_data_scope(query, user, db_session)

    # 构建并执行验证
    org = Organization(org_name="o", org_type="building")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    dev1 = MockDevice(name="A的设备", org_id=org.id, created_by=42)
    dev2 = MockDevice(name="B的设备", org_id=org.id, created_by=99)
    db_session.add(dev1)
    db_session.add(dev2)
    await db_session.commit()

    result = await db_session.execute(filtered)
    items = result.scalars().all()
    assert len(items) == 1
    assert items[0].name == "A的设备"


@pytest.mark.asyncio
async def test_apply_data_scope_self_no_created_by_field(client, db_session):
    """data_scope='self' 但模型无 created_by 字段时不应报错"""
    class NoCreatedBy(Base):
        __tablename__ = "no_created_by"
        id = Column(Integer, primary_key=True)

    user = User(id=1, username="u", password_hash="hash", data_scope="self")
    query = select(NoCreatedBy)
    filtered = await apply_data_scope(query, user, db_session)
    # 应原样返回，不抛异常
    assert filtered is not None


# ---------------------------------------------------------------------------
# apply_data_scope - dept
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_apply_data_scope_dept(client, db_session):
    """data_scope='dept' 应过滤本部门及子部门"""
    # 组织架构
    parent = Organization(org_name="消防中心", org_type="building")
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    child = Organization(org_name="一分队", org_type="zone", parent_id=parent.id)
    db_session.add(child)
    await db_session.commit()
    await db_session.refresh(child)

    other = Organization(org_name="其他", org_type="building")
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    user = User(
        id=1, username="u", password_hash="hash", data_scope="dept", org_id=parent.id
    )

    dev1 = MockDevice(name="父设备", org_id=parent.id)
    dev2 = MockDevice(name="子设备", org_id=child.id)
    dev3 = MockDevice(name="其他设备", org_id=other.id)
    db_session.add(dev1)
    db_session.add(dev2)
    db_session.add(dev3)
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
async def test_apply_data_scope_dept_no_org_id(client, db_session):
    """data_scope='dept' 但用户无 org_id 时应返回空结果"""
    user = User(id=1, username="u", password_hash="hash", data_scope="dept", org_id=None)

    org = Organization(org_name="o", org_type="building")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    dev = MockDevice(name="设备", org_id=org.id)
    db_session.add(dev)
    await db_session.commit()

    query = select(MockDevice)
    filtered = await apply_data_scope(query, user, db_session)
    result = await db_session.execute(filtered)
    items = result.scalars().all()
    assert len(items) == 0


@pytest.mark.asyncio
async def test_apply_data_scope_dept_no_org_id_field(client, db_session):
    """data_scope='dept' 但模型无 org_id 字段时应原样返回"""
    class NoOrgId(Base):
        __tablename__ = "no_org_id"
        id = Column(Integer, primary_key=True)

    user = User(id=1, username="u", password_hash="hash", data_scope="dept", org_id=1)

    query = select(NoOrgId)
    filtered = await apply_data_scope(query, user, db_session)
    assert filtered is not None


@pytest.mark.asyncio
async def test_apply_data_scope_unknown_scope(client, db_session):
    """未知的 data_scope 应原样返回查询"""
    user = User(id=1, username="u", password_hash="hash", data_scope="unknown")
    query = select(MockDevice)
    filtered = await apply_data_scope(query, user, db_session)
    assert str(filtered) == str(query)
