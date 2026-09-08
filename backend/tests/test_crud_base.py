"""
通用 CRUD 基类单元测试
覆盖：get、get_multi、create、update、delete
"""

import pytest
from sqlalchemy import Column, Integer, String, select

from app.crud.base import CRUDBase
from app.models.base import Base


# 定义测试模型
class TestItem(Base):
    __tablename__ = "test_items"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)


@pytest.fixture
def item_crud():
    return CRUDBase(TestItem)


@pytest.mark.asyncio
async def test_crud_get(client, db_session, item_crud):
    """get 应返回指定 ID 的对象"""
    obj = TestItem(name="测试项", description="描述")
    db_session.add(obj)
    await db_session.commit()
    await db_session.refresh(obj)

    result = await item_crud.get(db_session, obj.id)
    assert result is not None
    assert result.name == "测试项"
    assert result.description == "描述"


@pytest.mark.asyncio
async def test_crud_get_not_found(client, db_session, item_crud):
    """get 不存在的 ID 应返回 None"""
    result = await item_crud.get(db_session, 99999)
    assert result is None


@pytest.mark.asyncio
async def test_crud_get_multi(client, db_session, item_crud):
    """get_multi 应返回分页结果"""
    for i in range(5):
        db_session.add(TestItem(name=f"item_{i}"))
    await db_session.commit()

    items = await item_crud.get_multi(db_session, skip=0, limit=3)
    assert len(items) == 3
    assert items[0].name == "item_0"


@pytest.mark.asyncio
async def test_crud_get_multi_skip(client, db_session, item_crud):
    """get_multi skip 应生效"""
    for i in range(3):
        db_session.add(TestItem(name=f"item_{i}"))
    await db_session.commit()

    items = await item_crud.get_multi(db_session, skip=1, limit=10)
    assert len(items) == 2
    assert items[0].name == "item_1"


@pytest.mark.asyncio
async def test_crud_create(client, db_session, item_crud):
    """create 应创建对象并返回"""
    from pydantic import BaseModel

    class ItemCreate(BaseModel):
        name: str
        description: str | None = None

    schema = ItemCreate(name="新建项", description="新描述")
    obj = await item_crud.create(db_session, obj_in=schema)

    assert obj.id is not None
    assert obj.name == "新建项"
    assert obj.description == "新描述"


@pytest.mark.asyncio
async def test_crud_update_with_schema(client, db_session, item_crud):
    """update 使用 Pydantic schema 应更新字段"""
    from pydantic import BaseModel

    obj = TestItem(name="旧名称", description="旧描述")
    db_session.add(obj)
    await db_session.commit()
    await db_session.refresh(obj)

    class ItemUpdate(BaseModel):
        name: str | None = None
        description: str | None = None

    schema = ItemUpdate(name="新名称")
    updated = await item_crud.update(db_session, db_obj=obj, obj_in=schema)

    assert updated.name == "新名称"
    assert updated.description == "旧描述"  # 未更新字段保持不变


@pytest.mark.asyncio
async def test_crud_update_with_dict(client, db_session, item_crud):
    """update 使用 dict 应更新字段"""
    obj = TestItem(name="旧名称", description="旧描述")
    db_session.add(obj)
    await db_session.commit()
    await db_session.refresh(obj)

    updated = await item_crud.update(
        db_session, db_obj=obj, obj_in={"name": "字典更新"}
    )

    assert updated.name == "字典更新"
    assert updated.description == "旧描述"


@pytest.mark.asyncio
async def test_crud_delete(client, db_session, item_crud):
    """delete 应删除对象并返回被删除对象"""
    obj = TestItem(name="待删除")
    db_session.add(obj)
    await db_session.commit()
    await db_session.refresh(obj)

    deleted = await item_crud.delete(db_session, id=obj.id)
    assert deleted is not None
    assert deleted.name == "待删除"

    # 再次 get 应返回 None
    result = await item_crud.get(db_session, obj.id)
    assert result is None


@pytest.mark.asyncio
async def test_crud_delete_not_found(client, db_session, item_crud):
    """delete 不存在的 ID 应返回 None"""
    result = await item_crud.delete(db_session, id=99999)
    assert result is None
