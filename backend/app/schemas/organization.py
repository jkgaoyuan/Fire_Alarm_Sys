"""
组织架构相关 Pydantic Schema
"""

from pydantic import BaseModel, Field


VALID_ORG_TYPES = ("building", "floor", "zone")


class OrganizationCreate(BaseModel):
    """创建组织节点"""

    org_name: str = Field(..., min_length=1, max_length=100)
    org_type: str = Field(..., pattern="^(building|floor|zone)$")
    parent_id: int | None = None
    sort_order: int = 0


class OrganizationUpdate(BaseModel):
    """更新组织节点（部分更新）"""

    org_name: str | None = Field(None, min_length=1, max_length=100)
    org_type: str | None = Field(None, pattern="^(building|floor|zone)$")
    parent_id: int | None = None
    sort_order: int | None = None


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
