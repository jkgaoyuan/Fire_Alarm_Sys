"""
组织架构 API 路由
GET    /organizations           扁平列表（供筛选下拉）
GET    /organizations/tree      组织架构树（供 el-cascader 区域选择）
POST   /organizations           创建组织节点（P2-010）
PUT    /organizations/{id}      更新组织节点（P2-010）
DELETE /organizations/{id}      删除组织节点（P2-010）
POST   /organizations/{id}/map-image    楼层平面图上传（B-17 / FR-015）
DELETE /organizations/{id}/map-image    移除楼层平面图

3.2 计划第五节称本接口「3.1 已提供」，实际不存在，故作为 F-9 区域选择器的前置补齐。
参考数据，登录即可访问（与 device-types 一致）；map-image 写接口需 monitor:config。
"""

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_permission
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import (
    MapImageOut,
    OrganizationCreate,
    OrganizationFlatOut,
    OrganizationUpdate,
)
from app.services import map_image_service
from app.services.monitor_service import get_org
from app.services.organization_service import (
    create_organization,
    delete_organization,
    get_organization_tree,
    get_organizations_flat,
    update_organization,
)

router = APIRouter()


@router.get("", response_model=dict)
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """返回扁平组织架构列表"""
    orgs = await get_organizations_flat(db)
    return {
        "code": 200,
        "message": "success",
        "data": [
            OrganizationFlatOut(
                id=o.id,
                parent_id=o.parent_id,
                org_name=o.org_name,
                org_type=o.org_type,
            ).model_dump()
            for o in orgs
        ],
    }


@router.get("/tree", response_model=dict)
async def organization_tree(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """返回组织架构树（叶子节点为安装区域）"""
    tree = await get_organization_tree(db)
    return {
        "code": 200,
        "message": "success",
        "data": tree,
    }


@router.post("", response_model=dict)
async def create_org(
    body: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("system:org:create")),
):
    """创建组织节点"""
    org = await create_organization(
        db,
        org_name=body.org_name,
        org_type=body.org_type,
        parent_id=body.parent_id,
        sort_order=body.sort_order,
    )
    return {
        "code": 200,
        "message": "创建成功",
        "data": OrganizationFlatOut(
            id=org.id,
            parent_id=org.parent_id,
            org_name=org.org_name,
            org_type=org.org_type,
        ).model_dump(),
    }


@router.put("/{org_id}", response_model=dict)
async def update_org(
    org_id: int,
    body: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("system:org:update")),
):
    """更新组织节点"""
    org = await db.get(Organization, org_id)
    if org is None:
        raise NotFoundError("组织节点不存在")

    org = await update_organization(
        db,
        org,
        org_name=body.org_name,
        org_type=body.org_type,
        parent_id=body.parent_id,
        sort_order=body.sort_order,
    )
    return {
        "code": 200,
        "message": "更新成功",
        "data": OrganizationFlatOut(
            id=org.id,
            parent_id=org.parent_id,
            org_name=org.org_name,
            org_type=org.org_type,
        ).model_dump(),
    }


@router.delete("/{org_id}", response_model=dict)
async def delete_org(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("system:org:delete")),
):
    """删除组织节点（有子节点或关联数据时拒绝）"""
    org = await db.get(Organization, org_id)
    if org is None:
        raise NotFoundError("组织节点不存在")

    await delete_organization(db, org)
    return {"code": 200, "message": "删除成功", "data": None}


def _map_image_out(org: Organization) -> dict:
    return MapImageOut(
        org_id=org.id,
        map_image_url=org.map_image_url,
        map_image_width=org.map_image_width,
        map_image_height=org.map_image_height,
        map_origin=org.map_origin,
    ).model_dump()


@router.post("/{org_id}/map-image", response_model=dict)
async def upload_map_image(
    org_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("monitor:config")),
):
    """
    上传楼层平面图（PNG/JPG/PDF 首页）。

    超过 MAP_IMAGE_MAX_WIDTH 等比压缩，因此必须同步回写 width/height，
    前端才能把 devices.map_x/map_y 的原图像素坐标正确归一化。
    """
    org = await get_org(db, org_id)
    if org is None:
        raise NotFoundError("组织节点不存在")

    content = await file.read()
    try:
        url, width, height = map_image_service.save_map_image(content, file.filename or "")
    except map_image_service.MapImageError as exc:
        return {"code": 400, "message": str(exc), "data": None}

    map_image_service.delete_map_image(org.map_image_url)
    org.map_image_url = url
    org.map_image_width = width
    org.map_image_height = height
    org.map_origin = org.map_origin or "top_left"
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return {
        "code": 200,
        "message": "上传成功",
        "data": _map_image_out(org),
    }


@router.delete("/{org_id}/map-image", response_model=dict)
async def delete_map_image_api(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("monitor:config")),
):
    """移除楼层平面图（同时删除已落盘文件）"""
    org = await get_org(db, org_id)
    if org is None:
        raise NotFoundError("组织节点不存在")

    map_image_service.delete_map_image(org.map_image_url)
    org.map_image_url = None
    org.map_image_width = None
    org.map_image_height = None
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return {"code": 200, "message": "删除成功", "data": _map_image_out(org)}
