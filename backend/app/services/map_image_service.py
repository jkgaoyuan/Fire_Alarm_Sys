"""
平面图上传与压缩（3.3 B-17 / FR-015）

存储走本地卷（`backend/storage/map-images/`）+ StaticFiles，MinIO 延后（计划 12 节 C-2、A-10）；
届时只需替换本模块的 save/delete，接口与坐标约定不变。

坐标约定（计划 4.2）：`devices.map_x/map_y` 存的是**原图像素坐标**，
`organizations.map_image_width/height` 记录压缩后图片的基准尺寸，
前端按基准宽高归一化后再叠加到 Leaflet，因此压缩必须同步回写宽高，否则点位错位。
"""

import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings

settings = get_settings()

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# 与前端约定的可接受类型：PNG / JPEG / PDF（仅取首页）
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
PDF_MAGIC = b"%PDF"

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}


class MapImageError(Exception):
    """平面图处理失败（消息直接透出给前端）"""


def storage_dir() -> Path:
    root = Path(settings.STORAGE_DIR)
    return root if root.is_absolute() else BACKEND_ROOT / root


def map_image_dir() -> Path:
    path = storage_dir() / "map-images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def detect_kind(content: bytes) -> str:
    """按魔数判定类型（不信任客户端 MIME 与扩展名）"""
    if content.startswith(PNG_MAGIC):
        return "png"
    if content.startswith(JPEG_MAGIC):
        return "jpeg"
    if content.startswith(PDF_MAGIC):
        return "pdf"
    raise MapImageError("文件类型不合法，仅支持 PNG / JPG / PDF")


def _max_bytes() -> int:
    return settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


def save_map_image(content: bytes, filename: str) -> tuple[str, int, int]:
    """
    校验并落盘一张平面图，返回 (`/static/maps/xxx` 相对 URL, 宽, 高)。

    超宽（>MAP_IMAGE_MAX_WIDTH）等比压缩；PDF 先转 PNG。
    """
    if not content:
        raise MapImageError("文件内容为空")
    if len(content) > _max_bytes():
        raise MapImageError(f"文件超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")
    _check_extension(filename)

    kind = detect_kind(content)
    if kind == "pdf":
        image = _pdf_to_image(content)
    else:
        image = _open_image(content)

    image, scaled = _downscale(image)
    ext = "png" if kind in ("pdf", "png") else "jpg"
    filename_out = f"{uuid.uuid4().hex}.{ext}"
    target = map_image_dir() / filename_out

    try:
        if ext == "jpg":
            image.convert("RGB").save(target, "JPEG", quality=settings.MAP_IMAGE_JPEG_QUALITY)
        else:
            image.save(target, "PNG", optimize=True)
    except OSError as exc:
        raise MapImageError(f"图片写入失败: {exc}") from exc
    finally:
        image.close()

    width, height = scaled
    return f"/static/maps/{filename_out}", width, height


def _check_extension(filename: str) -> None:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise MapImageError("扩展名不受支持，仅允许 .png / .jpg / .jpeg / .pdf")


def _open_image(content: bytes):
    import io

    try:
        return Image.open(io.BytesIO(content))
    except (UnidentifiedImageError, OSError) as exc:
        raise MapImageError(f"图片解析失败: {exc}") from exc


def _pdf_to_image(content: bytes):
    """PDF 取第 1 页渲染为位图（PRD 6.2 附件仅要求可读，切片方案已延期）"""
    import io

    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - 依赖缺失属于部署问题
        raise MapImageError("服务端未安装 PDF 解析库") from exc

    document = None
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
        if document.page_count == 0:
            raise MapImageError("PDF 无可用页面")
        page = document.load_page(0)
        zoom = 2.0
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return image
    except MapImageError:
        raise
    except Exception as exc:  # noqa: BLE001 - PyMuPDF 对损坏 PDF 抛的是通用异常
        raise MapImageError(f"PDF 解析失败: {exc}") from exc
    finally:
        if document is not None:
            document.close()


def _downscale(image):
    """超过基准宽度时等比压缩，返回 (图片, 最终宽高)"""
    limit = settings.MAP_IMAGE_MAX_WIDTH
    width, height = image.size
    if width <= limit or width == 0:
        return image, (width, height)
    ratio = limit / width
    target = (int(limit), max(1, int(round(height * ratio))))
    return image.resize(target, Image.LANCZOS), target


def delete_map_image(url: str | None) -> bool:
    """
    按 URL 删除文件。仅接受本模块生成的 /static/maps/ 路径，
    且解析后必须仍位于存储目录内，防止越权删除任意文件。
    """
    if not url or not url.startswith("/static/maps/"):
        return False
    base = map_image_dir().resolve()
    target = (base / Path(url).name).resolve()
    if target.parent != base or not target.is_file():
        return False
    target.unlink()
    return True
