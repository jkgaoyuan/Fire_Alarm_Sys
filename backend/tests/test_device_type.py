"""
设备类型（FR-007）测试

覆盖：预置 8 种类型完整性、attribute_schema 非法定义容错、类型下拉框访问权限。
"""

import pytest

from app.models.user import User
from app.services.device_service import validate_attributes
from scripts.init_data import DEVICE_TYPES_DATA

PRESET_TYPE_CODES = {
    "smoke_detector",
    "heat_detector",
    "manual_alarm",
    "hydrant",
    "sprinkler",
    "exhaust_fan",
    "fire_door",
    "emergency_light",
}
SUPPORTED_FIELD_TYPES = {"string", "number", "select"}


@pytest.mark.asyncio
async def test_preset_device_types_complete():
    """预置类型必须为 8 种，且每种都有非空属性模板与合法字段类型"""
    assert len(DEVICE_TYPES_DATA) == 8
    assert {t["type_code"] for t in DEVICE_TYPES_DATA} == PRESET_TYPE_CODES

    for item in DEVICE_TYPES_DATA:
        assert item["type_name"]
        assert item["category"]
        schema = item["attribute_schema"]
        assert isinstance(schema, dict) and schema, f"{item['type_code']} 属性模板为空"
        for field, spec in schema.items():
            assert spec.get("label"), f"{item['type_code']}.{field} 缺少 label"
            assert spec.get("type") in SUPPORTED_FIELD_TYPES, (
                f"{item['type_code']}.{field} 使用了前端未渲染的字段类型"
            )
            if spec["type"] == "select":
                assert spec.get("options"), f"{item['type_code']}.{field} 缺少 options"


@pytest.mark.asyncio
async def test_validate_attributes_tolerates_bad_schema():
    """属性模板声明了不支持的类型 / 提交未知键时给出明确错误而不是抛异常"""
    schema = {
        "sensitivity": {"label": "灵敏度", "type": "select", "options": ["高", "低"]},
        "weird": {"label": "奇怪字段", "type": "array"},
    }

    assert validate_attributes(schema, {"sensitivity": "高"}) == []
    assert validate_attributes(schema, {"sensitivity": "极高"}) == ["灵敏度 取值必须是 ['高', '低'] 之一"]
    assert validate_attributes(schema, {"not_in_schema": 1}) == ["未知扩展属性: not_in_schema"]
    # 模板声明了前端不支持的类型 → 报错但不抛
    assert validate_attributes(schema, {"weird": [1, 2]}) == [
        "属性 weird 声明了不支持的字段类型 array"
    ]
    # 数字字段允许数字字符串（Excel 单元格常为文本）
    assert validate_attributes({"n": {"label": "数值", "type": "number"}}, {"n": "60"}) == []
    assert validate_attributes({"n": {"label": "数值", "type": "number"}}, {"n": "abc"}) == [
        "数值 必须为数字"
    ]


@pytest.mark.asyncio
async def test_device_types_list_requires_only_login(client, db_session, test_user):
    """类型下拉框登录即可访问（无 device 权限也能读），未登录则 401"""
    from tests.device_helpers import auth_headers, create_device_type

    await create_device_type(db_session, "smoke_detector", "烟感探测器")
    await create_device_type(db_session, "hydrant", "消火栓")

    resp = await client.get("/api/v1/device-types", headers=auth_headers(test_user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert {t["type_code"] for t in body["data"]} == {"smoke_detector", "hydrant"}
    assert body["data"][0]["attribute_schema"]

    resp = await client.get("/api/v1/device-types")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_device_type_detail_and_404(client, db_session, test_user):
    """类型详情返回 attribute_schema；不存在的 id 返回 404"""
    from tests.device_helpers import auth_headers, create_device_type

    device_type = await create_device_type(db_session, "fire_door", "防火门")

    resp = await client.get(
        f"/api/v1/device-types/{device_type.id}", headers=auth_headers(test_user)
    )
    assert resp.json()["data"]["type_name"] == "防火门"

    resp = await client.get("/api/v1/device-types/999999", headers=auth_headers(test_user))
    assert resp.json()["code"] == 404
