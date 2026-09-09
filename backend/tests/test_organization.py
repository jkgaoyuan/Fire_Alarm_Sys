"""
组织架构接口测试（3.2 F-9 区域选择器前置依赖 P0-009）

覆盖：扁平列表、树形嵌套与排序、脏父节点不丢子树、未登录拒绝。
"""

import pytest

from tests.device_helpers import auth_headers, create_org


@pytest.mark.asyncio
async def test_organizations_flat_list(client, db_session, test_user):
    """/organizations 返回扁平节点，含 parent_id 供前端自行组装"""
    root = await create_org(db_session, "消防监控中心")
    await create_org(db_session, "A 栋", parent=root)
    await create_org(db_session, "B 栋", parent=root)

    resp = await client.get("/api/v1/organizations", headers=auth_headers(test_user))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 3
    assert {"id", "parent_id", "org_name", "org_type"} <= set(data[0])
    assert data[0]["parent_id"] is None
    assert {item["parent_id"] for item in data[1:]} == {root.id}


@pytest.mark.asyncio
async def test_organizations_tree_nesting_and_order(client, db_session, test_user):
    """树按 sort_order 排序，叶子节点 children 为空数组（el-cascader 需要）"""
    root = await create_org(db_session, "消防监控中心")
    building_b = await create_org(db_session, "B 栋", parent=root)
    building_a = await create_org(db_session, "A 栋", parent=root)
    building_a.sort_order = -1
    await db_session.commit()
    await create_org(db_session, "B 栋 1F", parent=building_b)

    tree = (
        await client.get("/api/v1/organizations/tree", headers=auth_headers(test_user))
    ).json()["data"]

    assert len(tree) == 1
    assert tree[0]["org_name"] == "消防监控中心"
    assert [c["org_name"] for c in tree[0]["children"]] == ["A 栋", "B 栋"]
    assert [c["org_name"] for c in tree[0]["children"][1]["children"]] == ["B 栋 1F"]
    assert tree[0]["children"][0]["children"] == []


@pytest.mark.asyncio
async def test_organizations_tree_promotes_orphans(client, db_session, test_user):
    """parent_id 指向不存在节点时该子树提升为根，不能静默丢失"""
    orphan = await create_org(db_session, "脏数据区域")
    orphan.parent_id = 999999
    await db_session.commit()

    tree = (
        await client.get("/api/v1/organizations/tree", headers=auth_headers(test_user))
    ).json()["data"]
    assert [node["org_name"] for node in tree] == ["脏数据区域"]


@pytest.mark.asyncio
async def test_organizations_require_login(client):
    """未登录访问组织架构返回 401"""
    assert (await client.get("/api/v1/organizations")).status_code == 401
    assert (await client.get("/api/v1/organizations/tree")).status_code == 401
