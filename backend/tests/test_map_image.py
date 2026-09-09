"""
平面图上传与解析（3.3 B-17 / FR-015、FR-017 地图设置）测试

覆盖：超宽等比压缩并回写基准宽高、PDF 首页转 PNG、伪造 MIME/非图片/超限拒绝、
删除后子区域继承失效。存储目录改到 tmp，避免测试产物落进仓库。
"""

import io

import pytest
from PIL import Image

from app.services import map_image_service
from tests.device_helpers import auth_headers, create_device_type, create_device_user, create_org
from tests.monitor_helpers import MONITOR_PERMS, create_device

UPLOAD_URL = "/api/v1/organizations/{org_id}/map-image"
settings = map_image_service.settings
MAX_WIDTH = settings.MAP_IMAGE_MAX_WIDTH


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path / "storage"))
    return tmp_path / "storage"


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (240, 30, 40)).save(buffer, "PNG")
    return buffer.getvalue()


def _pdf(width: int = 200, height: int = 100) -> bytes:
    import pymupdf

    document = pymupdf.open()
    document.new_page(width=width, height=height)
    content = document.tobytes()
    document.close()
    return content


async def _upload(client, user, org_id, filename, content, mime="image/png"):
    return await client.post(
        UPLOAD_URL.format(org_id=org_id),
        headers=auth_headers(user),
        files={"file": (filename, content, mime)},
    )


@pytest.fixture
async def map_env(db_session):
    building = await create_org(db_session, "地图大楼")
    floor = await create_org(db_session, "3F", building)
    zone = await create_org(db_session, "3F 走廊", floor)
    device_type = await create_device_type(db_session)
    admin = await create_device_user(
        db_session, username="map_admin", perm_codes=MONITOR_PERMS, data_scope="all"
    )
    viewer = await create_device_user(
        db_session,
        username="map_viewer",
        perm_codes=["monitor:view"],
        data_scope="all",
    )
    device = await create_device(db_session, zone, device_type, "DM-001", map_x=120, map_y=80)
    return {
        "building": building,
        "floor": floor,
        "zone": zone,
        "admin": admin,
        "viewer": viewer,
        "device": device,
    }


async def test_wide_floor_plan_is_downscaled_and_basis_recorded(db_session, client, map_env):
    """超宽图压缩到基准宽度，宽高同步写回 organizations 作为点位归一化基准"""
    resp = await _upload(client, map_env["admin"], map_env["floor"].id, "3f.png", _png(3000, 1500))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200, body

    data = body["data"]
    assert (data["map_image_width"], data["map_image_height"]) == (MAX_WIDTH, MAX_WIDTH // 2)
    assert data["map_image_url"].startswith("/static/maps/") and data["map_image_url"].endswith(".png")
    assert data["map_origin"] == "top_left"

    saved = map_image_service.map_image_dir() / data["map_image_url"].rsplit("/", 1)[-1]
    assert saved.is_file()
    with Image.open(saved) as image:
        assert image.size == (MAX_WIDTH, MAX_WIDTH // 2)

    await db_session.refresh(map_env["floor"])
    assert map_env["floor"].map_image_url == data["map_image_url"]

    meta = await client.get(
        "/api/v1/monitor/map", params={"org_id": map_env["zone"].id},
        headers=auth_headers(map_env["admin"]),
    )
    result = meta.json()["data"]
    assert (result["resolved_org_id"], result["map_image_url"]) == (
        map_env["floor"].id,
        data["map_image_url"],
    )


async def test_pdf_first_page_converted_to_png(client, map_env):
    """PDF 平面图取首页渲染（zoom 2.0）后按 PNG 存储"""
    resp = await _upload(
        client, map_env["admin"], map_env["floor"].id, "plan.pdf", _pdf(), "application/pdf"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["map_image_url"].endswith(".png")
    assert (data["map_image_width"], data["map_image_height"]) == (400, 200)


async def test_forged_mime_and_oversize_rejected(client, map_env):
    """类型只认魔数、扩展名白名单与大小上限缺一不可，且不落盘"""
    org_id = map_env["floor"].id

    text_file = await _upload(client, map_env["admin"], org_id, "plan.png", b"not an image at all")
    assert text_file.json()["code"] == 400
    assert "文件类型" in text_file.json()["message"]

    wrong_ext = await _upload(client, map_env["admin"], org_id, "plan.exe", _png(20, 20))
    assert wrong_ext.json()["code"] == 400 and "扩展名" in wrong_ext.json()["message"]

    limit = settings.MAX_UPLOAD_SIZE_MB
    huge = map_image_service.PNG_MAGIC + b"\x00" * (limit * 1024 * 1024 + 1)
    oversize = await _upload(client, map_env["admin"], org_id, "huge.png", huge)
    assert oversize.json()["code"] == 400 and f"{limit}MB" in oversize.json()["message"]

    assert list(map_image_service.map_image_dir().glob("*")) == []


async def test_upload_requires_config_permission(client, map_env):
    """上传/删除平面图属 monitor:config，只读用户 403"""
    resp = await _upload(
        client, map_env["viewer"], map_env["floor"].id, "3f.png", _png(40, 40)
    )
    assert resp.status_code == 403

    delete = await client.delete(
        UPLOAD_URL.format(org_id=map_env["floor"].id), headers=auth_headers(map_env["viewer"])
    )
    assert delete.status_code == 403


async def test_delete_map_image_clears_basis_and_files(client, map_env, db_session):
    """删除平面图：基准列清空、文件移除，子区域不再继承到任何底图"""
    upload = await _upload(
        client, map_env["admin"], map_env["floor"].id, "3f.png", _png(800, 600)
    )
    url = upload.json()["data"]["map_image_url"]
    saved = map_image_service.map_image_dir() / url.rsplit("/", 1)[-1]
    assert saved.is_file()

    resp = await client.delete(
        UPLOAD_URL.format(org_id=map_env["floor"].id), headers=auth_headers(map_env["admin"])
    )
    assert resp.status_code == 200 and resp.json()["code"] == 200
    assert resp.json()["data"]["map_image_url"] is None
    assert saved.exists() is False

    await db_session.refresh(map_env["floor"])
    assert (map_env["floor"].map_image_width, map_env["floor"].map_image_height) == (None, None)

    meta = await client.get(
        "/api/v1/monitor/map", params={"org_id": map_env["zone"].id},
        headers=auth_headers(map_env["admin"]),
    )
    data = meta.json()["data"]
    assert data["map_image_url"] is None and data["resolved_org_id"] is None
