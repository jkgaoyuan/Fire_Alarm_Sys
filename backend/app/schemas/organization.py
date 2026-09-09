"""
组织架构相关 Pydantic Schema
"""

from pydantic import BaseModel


class OrganizationFlatOut(BaseModel):
    """组织架构扁平节点（供列表筛选下拉使用）"""

    id: int
    parent_id: int | None = None
    org_name: str
    org_type: str | None = None


class MapImageOut(BaseModel):
    """
    平面图配置结果（FR-015）。

    width/height 为**压缩后**图片的像素基准尺寸，前端据此把 devices.map_x/map_y
    （原图像素坐标）归一化后再叠加到 Leaflet，缺失会导致点位错位。
    """

    org_id: int
    map_image_url: str | None = None
    map_image_width: int | None = None
    map_image_height: int | None = None
    map_origin: str | None = None
