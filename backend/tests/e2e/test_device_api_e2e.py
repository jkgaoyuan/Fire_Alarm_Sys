"""
3.2 消防设备档案 —— 端到端回归用例

区别于 `tests/test_device_*.py`（SQLite 内存库 + ASGI 进程内调用），本模块通过 HTTP 访问
**真实运行的后端服务 + PostgreSQL + Redis**，覆盖单测环境无法验证的行为：
JSONB 落库与反序列化、Numeric 精度、递归 CTE 数据范围、Excel 导入的事务与回滚、
以及三类角色的权限矩阵。

默认跳过，须显式给出服务地址：

    docker compose up -d
    E2E_BASE_URL=http://localhost:8000/api/v1 python -m pytest -m e2e -v

依赖 `backend/scripts/init_data.py` 的预置数据：8 种设备类型、根组织节点，
以及 admin / duty01 / maint01 三个种子账号。设备编码带随机运行前缀，用例结束后按前缀逻辑删除。
"""

import io
import json

import pytest
from openpyxl import Workbook, load_workbook

from tests.e2e.common import XLSX_MIME, device_payload, find_by_keyword, total_of

pytestmark = pytest.mark.e2e

TEMPLATE_HEADERS = [
    "设备编码*", "设备名称*", "类型编码", "区域ID", "厂商", "型号", "品牌", "规格",
    "安装日期", "质保到期日", "维护周期(天)", "状态", "X坐标", "Y坐标", "备注",
    "扩展属性(JSON)",
]

# 各类型 attribute_schema 中真实存在的扩展属性，切换 type_id 时必须一并换掉 attributes
TYPE_ATTRIBUTES = {
    "smoke_detector": {"sensitivity": "高", "detection_area": 60},
    "hydrant": {"has_nozzle": "是", "design_flow": 20},
}


# ==================== fixtures ====================


@pytest.fixture
def device(make_device) -> dict:
    """函数级单台设备，避免退役/删除等状态变更在用例间互相污染"""
    return make_device()


def build_xlsx(rows: list[list]) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "设备档案"
    ws.append(TEMPLATE_HEADERS)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def import_row(code: str, type_code: str, attributes: dict, org_id: int, name: str = ""):
    return [
        code, name or f"导入设备{code}", type_code, org_id,
        None, None, None, None, "2025-04-01", None, 180, "normal", 88.5, 120.0, "",
        json.dumps(attributes, ensure_ascii=False) if attributes else None,
    ]


def upload(chief, buf: io.BytesIO, filename: str = "devices.xlsx") -> dict:
    resp = chief.post("/devices/import", files={"file": (filename, buf, XLSX_MIME)})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ==================== 模型与参考数据 ====================


def test_seeded_device_types_exposed(types):
    """8 种预置设备类型可读，attribute_schema 在 PostgreSQL 侧以 JSONB 正常反序列化"""
    assert len(types) == 8, sorted(types)
    assert {"smoke_detector", "hydrant", "manual_alarm"} <= set(types)
    schema = types["smoke_detector"]["attribute_schema"]
    assert isinstance(schema, dict) and schema["sensitivity"]["type"] == "select"
    assert schema["sensitivity"]["options"] == ["高", "中", "低"]


def test_device_type_detail(chief, types):
    """类型详情返回完整 schema，供前端动态表单渲染"""
    detail = chief.unwrap("GET", f"/device-types/{types['hydrant']['id']}")
    assert detail["type_code"] == "hydrant"
    assert set(detail["attribute_schema"]) == {"has_nozzle", "design_flow", "outlet_count"}


def test_organization_tree_available(chief, org_id):
    """组织树可用且首节点为根（F-9 区域级联与 dept 数据范围的硬依赖）"""
    tree = chief.unwrap("GET", "/organizations/tree")
    assert tree[0]["id"] == org_id
    assert tree[0]["org_name"]
    assert "children" in tree[0]


# ==================== 建档 CRUD 与校验 ====================


def test_create_device_roundtrip(chief, device, types, org_id):
    """创建后 JSONB 扩展属性、Numeric 坐标、空值与建档人均按原样回读"""
    assert device["attributes"] == {"sensitivity": "高", "detection_area": 60}
    assert device["map_x"] == 120.5
    assert device["map_y"] == 340.25, "Numeric 坐标不得丢失精度"
    assert device["warranty_expire_date"] == "2028-03-15"
    assert device["creator_name"] == "系统管理员"
    assert device["type_name"] == "烟感探测器"
    assert device["org_id"] == org_id

    detail = chief.unwrap("GET", f"/devices/{device['id']}")
    assert detail["device_code"] == device["device_code"]

    blank = chief.unwrap(
        "POST",
        "/devices",
        json=device_payload(
            device["device_code"] + "-B", types, org_id,
            warranty_expire_date=None, attributes={},
        ),
    )
    assert blank["warranty_expire_date"] is None, "未填日期应回读为 null 而非空串"
    assert blank["attributes"] == {}


def test_duplicate_device_code_rejected(chief, device, types, org_id):
    """编码唯一性由服务端裁决，重复即 400"""
    resp = chief.post(
        "/devices", json=device_payload(device["device_code"], types, org_id)
    )
    assert resp.status_code == 400
    assert f"设备编码已存在: {device['device_code']}" in resp.json()["message"]


def test_attribute_enum_violation_reports_options(chief, types, org_id, prefix):
    """扩展属性枚举越界要给出字段级原因（表单与导入明细共用）"""
    payload = device_payload(
        f"{prefix}-ENUM", types, org_id, attributes={"sensitivity": "极高"}
    )
    resp = chief.post("/devices", json=payload)
    assert resp.status_code == 400
    message = resp.json()["message"]
    assert "扩展属性校验失败" in message and "取值必须是" in message


def test_unknown_attribute_key_rejected(chief, types, org_id, prefix):
    """未在 schema 中声明的扩展属性键一律拒绝，防脏数据入库"""
    payload = device_payload(
        f"{prefix}-UNK", types, org_id,
        type_id=types["hydrant"]["id"], attributes={"material": "铸铁", "diameter": 65},
    )
    resp = chief.post("/devices", json=payload)
    assert resp.status_code == 400
    assert "未知扩展属性" in resp.json()["message"]


def test_combined_filters_and_pagination(chief, types, org_id, prefix):
    """关键词 + 类型 + 状态 + 组织 + 品牌 + 分页可组合叠加"""
    tag = f"{prefix}-FLT"
    for code, type_key in (("A", "smoke_detector"), ("B", "smoke_detector"), ("C", "hydrant")):
        chief.unwrap(
            "POST",
            "/devices",
            json=device_payload(
                f"{tag}-{code}", types, org_id,
                type_id=types[type_key]["id"], attributes=TYPE_ATTRIBUTES[type_key],
            ),
        )

    page1 = chief.unwrap("GET", "/devices", params={"keyword": tag, "page_size": 2})
    assert (page1["total"], len(page1["items"]), page1["page"]) == (3, 2, 1)
    page2 = chief.unwrap("GET", "/devices", params={"keyword": tag, "page_size": 2, "page": 2})
    assert len(page2["items"]) == 1
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})

    smoke = chief.unwrap("GET", "/devices", params={"keyword": tag, "type_id": types["smoke_detector"]["id"]})
    assert smoke["total"] == 2 and {i["type_name"] for i in smoke["items"]} == {"烟感探测器"}
    assert total_of(chief, tag, type_id=types["hydrant"]["id"]) == 1
    assert total_of(chief, tag, org_id=org_id) == 3
    assert total_of(chief, tag, status="fault") == 0
    assert total_of(chief, tag, brand="无此品牌") == 0
    assert total_of(chief, f"{tag}-A") == 1


def test_retire_is_terminal_and_hidden_by_default(chief, device):
    """退役后为终态：禁止再编辑；默认列表隐藏，include_retired 可见"""
    resp = chief.post(f"/devices/{device['id']}/retire", json={"reason": "到龄退役"})
    assert resp.status_code == 200 and resp.json()["data"]["status"] == "retired"

    rejected = chief.put(f"/devices/{device['id']}", json={"device_name": "改名"})
    assert rejected.status_code == 400 and "退役" in rejected.json()["message"]

    code = device["device_code"]
    assert total_of(chief, code, include_retired=False) == 0, "默认列表应隐藏已退役设备"
    assert total_of(chief, code, include_retired=True) == 1


def test_history_timeline(chief, types, org_id, prefix):
    """历史记录按时间倒序聚合状态变更，并显式声明尚未上线的数据源"""
    created = chief.unwrap(
        "POST", "/devices", json=device_payload(f"{prefix}-HIS", types, org_id)
    )
    chief.post(f"/devices/{created['id']}/retire", json={"reason": "改造停用"})

    history = chief.unwrap("GET", f"/devices/{created['id']}/history", params={"limit": 50})
    assert history["device_code"] == created["device_code"]
    assert history["total"] == 2
    latest, filing = history["items"]
    assert latest["title"] == "状态变更：正常 → 已退役" and latest["detail"] == "改造停用"
    assert filing["title"] == "建档：正常" and filing["detail"] == "设备建档"
    assert latest["operator"] == "系统管理员"
    # 3.4/3.7 接入后四类数据源全部可聚合，`unavailable_sources` 已移除
    assert "unavailable_sources" not in history


def test_update_device_persists(chief, device):
    """更新写库后详情一致，状态变更会追加一条留痕"""
    updated = chief.unwrap(
        "PUT",
        f"/devices/{device['id']}",
        json={"device_name": "改名后的设备", "status": "fault", "attributes": {"sensitivity": "低"}},
    )
    assert updated["device_name"] == "改名后的设备"
    assert updated["status"] == "fault"
    assert updated["attributes"] == {"sensitivity": "低"}
    assert chief.unwrap("GET", f"/devices/{device['id']}")["device_name"] == "改名后的设备"

    titles = [i["title"] for i in chief.unwrap("GET", f"/devices/{device['id']}/history")["items"]]
    assert "状态变更：正常 → 故障" in titles


def test_status_field_rejects_retired_on_update(chief, device):
    """退役必须走 /retire 以便留痕，PUT 直接写 retired 应被拒绝"""
    resp = chief.put(f"/devices/{device['id']}", json={"status": "retired"})
    assert resp.status_code == 400 and "retire" in resp.json()["message"]


def test_soft_deleted_device_code_remains_reserved(chief, device, types, org_id):
    """逻辑删除的设备仍占用编码（防唯一约束冲突），但列表任何视图都查不到它"""
    code = device["device_code"]
    assert chief.delete(f"/devices/{device['id']}").json()["message"] == "删除成功"

    assert total_of(chief, code) == 0
    assert chief.post("/devices", json=device_payload(code, types, org_id)).status_code == 400
    # 详情/历史的「不存在」走统一响应体 code，HTTP 仍为 200
    assert chief.get(f"/devices/{device['id']}").json()["code"] == 404


# ==================== 鉴权与权限矩阵 ====================


def test_request_without_token_rejected(client):
    """无 Token 访问业务 API 返回 401"""
    assert client.get("/devices").status_code == 401


def test_readonly_role_can_read_everything(chief, duty, device):
    """值班员（dept）：列表、详情、历史、类型、组织树均可读"""
    assert total_of(duty, device["device_code"]) == 1
    assert duty.unwrap("GET", f"/devices/{device['id']}")["id"] == device["id"]
    assert duty.unwrap("GET", f"/devices/{device['id']}/history")["device_id"] == device["id"]
    assert len(duty.unwrap("GET", "/device-types")) == 8
    assert duty.unwrap("GET", "/organizations/tree")


@pytest.mark.parametrize("role", ["duty", "maint"])
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/devices/{id}/retire", {"reason": "越权测试"}),
        ("PUT", "/devices/{id}", {"device_name": "越权改名"}),
        ("DELETE", "/devices/{id}", None),
        ("GET", "/devices/import/template", None),
    ],
)
def test_write_operations_forbidden_for_readonly_roles(role, method, path, body, request, device):
    """值班员 / 维保执行写操作一律 403，且数据未被改动"""
    api = request.getfixturevalue(role)
    url = path.replace("{id}", str(device["id"]))
    resp = api.request(method, url, json=body) if body is not None else api.request(method, url)
    assert resp.status_code == 403
    assert "缺少权限" in resp.json()["message"]
    assert api.unwrap("GET", f"/devices/{device['id']}")["device_code"] == device["device_code"]


def test_import_forbidden_without_create_permission(duty, org_id, prefix):
    """导入受 device:create 保护"""
    buf = build_xlsx([import_row(f"{prefix}-NOIMP", "hydrant", {"has_nozzle": "是"}, org_id)])
    resp = duty.post("/devices/import", files={"file": ("d.xlsx", buf, XLSX_MIME)})
    assert resp.status_code == 403 and "device:create" in resp.json()["message"]


def test_self_scope_hides_others_devices(maint, device):
    """维保（self）的列表看不到主管建档的设备"""
    assert total_of(maint, device["device_code"]) == 0


def test_detail_should_respect_data_scope(maint, device):
    """超出自身数据范围的设备按 ID 不可读（P1-007）"""
    assert maint.get(f"/devices/{device['id']}").status_code == 404


# ==================== Excel 批量导入 ====================


def test_import_template_is_valid_workbook(chief):
    """模板含固定 16 列与填写说明页，可被导入接口原样回读"""
    resp = chief.get("/devices/import/template")
    assert resp.status_code == 200
    assert XLSX_MIME in resp.headers["content-type"]

    workbook = load_workbook(io.BytesIO(resp.content))
    assert workbook.sheetnames == ["设备档案", "填写说明"]
    assert [c.value for c in workbook["设备档案"][1]] == TEMPLATE_HEADERS

    hint = "\n".join(
        str(cell.value) for row in workbook["填写说明"].iter_rows() for cell in row if cell.value
    )
    for code in ("smoke_detector", "hydrant", "manual_alarm"):
        assert code in hint, "填写说明应列出可用类型编码"


def test_import_all_valid_rows(chief, types, org_id, prefix):
    """全部合法时逐行建档，类型解析正确且每行都留下建档留痕"""
    tag = f"{prefix}-OK"
    result = upload(chief, build_xlsx([
        import_row(f"{tag}-1", "hydrant", {"has_nozzle": "是", "design_flow": 20}, org_id),
        import_row(f"{tag}-2", "manual_alarm", {"material": "铝合金"}, org_id),
        import_row(f"{tag}-3", "smoke_detector", {"sensitivity": "中"}, org_id),
    ]))
    assert (result["total"], result["success"], result["failed"]) == (3, 3, 0)
    assert result["rolled_back"] is False

    items = find_by_keyword(chief, tag)["items"]
    assert len(items) == 3
    by_code = {i["device_code"]: i for i in items}
    assert by_code[f"{tag}-1"]["type_name"] == "消火栓"
    assert by_code[f"{tag}-1"]["attributes"] == {"has_nozzle": "是", "design_flow": 20}
    assert by_code[f"{tag}-3"]["creator_name"] == "系统管理员"

    history = chief.unwrap("GET", f"/devices/{by_code[f'{tag}-2']['id']}/history")
    assert history["total"] == 1, "导入的设备同样要有建档留痕"
    assert history["items"][0]["title"] == "建档：正常"
    assert history["items"][0]["detail"] == "批量导入建档"


def test_import_partial_failure_keeps_valid_rows(chief, org_id, prefix):
    """失败率未超阈值时合法行照常入库，失败行给出行号与原因"""
    tag = f"{prefix}-PF"
    result = upload(chief, build_xlsx([
        import_row(f"{tag}-1", "hydrant", {"has_nozzle": "否"}, org_id),
        import_row(f"{tag}-2", "not_a_type", {}, org_id),
        import_row(f"{tag}-3", "smoke_detector", {"sensitivity": "极高"}, org_id),
        import_row(f"{tag}-4", "smoke_detector", {}, org_id),
    ]))
    assert (result["total"], result["success"], result["failed"]) == (4, 2, 2)
    assert result["rolled_back"] is False

    reasons = {f["device_code"]: f for f in result["failures"]}
    assert reasons[f"{tag}-2"]["row"] == 3
    assert "设备类型不存在" in reasons[f"{tag}-2"]["reason"]
    assert "扩展属性校验失败" in reasons[f"{tag}-3"]["reason"]
    assert total_of(chief, tag) == 2


def test_import_rolls_back_when_failure_rate_exceeds_threshold(chief, org_id, prefix):
    """失败率 >50% 整批回滚，一行都不落库"""
    tag = f"{prefix}-RB"
    before = total_of(chief, tag)
    result = upload(chief, build_xlsx([
        import_row(f"{tag}-1", "hydrant", {"has_nozzle": "是"}, org_id),
        import_row(f"{tag}-2", "bogus_a", {}, org_id),
        import_row(f"{tag}-3", "bogus_b", {}, org_id),
        import_row(f"{tag}-4", "hydrant", {}, org_id, name="   "),
    ]))
    assert result["rolled_back"] is True
    assert (result["total"], result["success"]) == (4, 0)
    assert "超过 50%" in result["message"]
    assert total_of(chief, tag) == before == 0, "回滚后不得留下任何一行"


def test_import_duplicate_code_in_file_and_db(chief, device, org_id, prefix):
    """同一文件内重复编码与撞库中已有编码都要逐行判失败，其余行照常入库"""
    tag = f"{prefix}-DUP"
    result = upload(chief, build_xlsx([
        import_row(f"{tag}-1", "hydrant", {"has_nozzle": "是"}, org_id),
        import_row(f"{tag}-2", "hydrant", {"has_nozzle": "是"}, org_id),
        import_row(f"{tag}-1", "hydrant", {"has_nozzle": "是"}, org_id),
        import_row(device["device_code"], "hydrant", {"has_nozzle": "是"}, org_id),
    ]))
    assert (result["total"], result["success"], result["failed"]) == (4, 2, 2)
    assert result["rolled_back"] is False
    assert [(f["row"], f["device_code"]) for f in result["failures"]] == [
        (4, f"{tag}-1"),
        (5, device["device_code"]),
    ]
    assert "设备编码已存在" in result["failures"][0]["reason"]


def test_import_rejects_bad_files(chief, prefix):
    """非 Excel 内容、只有表头的空表、缺必需列都返回 400 而不是 500"""
    csv = io.BytesIO("a,b\n1,2".encode())
    resp = chief.post("/devices/import", files={"file": ("a.csv", csv, "text/csv")})
    assert resp.status_code == 400 and "Excel" in resp.json()["message"]

    resp = chief.post(
        "/devices/import", files={"file": ("e.xlsx", build_xlsx([]), XLSX_MIME)}
    )
    assert resp.status_code == 400 and "没有可导入的数据行" in resp.json()["message"]

    narrow = io.BytesIO()
    wb = Workbook()
    wb.active.append(["设备编码*", "厂商"])
    wb.active.append([f"{prefix}-NOCOL", "缺列"])
    wb.save(narrow)
    narrow.seek(0)
    resp = chief.post("/devices/import", files={"file": ("n.xlsx", narrow, XLSX_MIME)})
    assert resp.status_code == 400
    assert "缺少必需列" in resp.json()["message"]
