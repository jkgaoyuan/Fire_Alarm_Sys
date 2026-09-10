# API 响应格式规范 (3.4-报警联动功能)

## 📋 概述

### 目的
统一前后端数据交互格式，避免因格式不一致导致的集成错误。

### 适用范围
- 所有新增的 API 接口（前端 + 后端）
- 现有接口的重构优化
- AI 辅助开发时的代码生成规范

---

## 🎯 核心原则

### **原则 1: 所有 API 必须返回统一的响应格式**

```json
{
  "code": 200,          // HTTP 状态码或业务状态码 (200 成功，400 错误，401 未授权，403 权限不足，500 服务器错误)
  "message": "success", // 提示信息（中文）
  "data": {             // 业务数据对象（可以是 null、数组、对象等）
    "items": [],        // 列表数据
    "total": 0,         // 总数
    "page": 1,          // 当前页码
    "page_size": 10     // 每页大小
  },
  "timestamp": 1789015029 // 请求时间戳（Unix 秒级）
}
```

---

## 🔧 后端实现规范

### 1️⃣ **使用统一的响应包装器**

#### ✅ **推荐方式：自定义 Response 类**

创建 `app/core/responses.py`:

```python
from typing import Any, Generic, TypeVar
from pydantic import BaseModel

DataT = TypeVar('DataT', bound=BaseModel)


class Response(BaseModel, Generic[DataT]):
    """统一响应格式"""
    code: int = 200
    message: str = "success"
    data: DataT | None = None
    timestamp: int = Field(default_factory=lambda: int(time.time()))


class PaginatedResponse(Response):
    """分页响应的增强版本"""
    
    class Config:
        schema_extra = {
            "example": {
                "code": 200,
                "message": "success",
                "data": {
                    "items": [{"id": 1, "name": "示例"}],
                    "total": 10,
                    "page": 1,
                    "page_size": 10
                },
                "timestamp": 1789015029
            }
        }
```

#### ✅ **在 API endpoint 中使用**

```python
from app.core.responses import Response

@router.get(
    "",
    response_model=Response[LinkagePlanPagination],
    summary="获取预案列表"
)
async def get_linkage_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("linkage:view")),  # 添加权限检查
):
    # ... 业务逻辑 ...
    
    return Response(
        code=200,
        message="success",
        data=LinkagePlanPagination(
            items=items,
            total=total or 0,
            page=page,
            page_size=page_size,
        )
    )
```

#### ✅ **处理错误响应**

```python
from fastapi import HTTPException

@router.post(
    "",
    response_model=Response[LinkagePlanOut],
    summary="创建新预案"
)
async def create_linkage_plan(
    plan: LinkagePlanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("linkage:create")),
):
    try:
        # 验证必填字段
        if not plan.plan_name or not plan.trigger_alarm_type:
            raise HTTPException(
                status_code=400,
                detail={"code": 400, "message": "预案名称和触发类型不能为空"}
            )
        
        # 创建预案...
        new_plan = await linkage_plan_crud.create(db, plan)
        
        return Response(
            code=200,
            message="创建成功",
            data=LinkagePlanOut.model_validate(new_plan)
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"创建预案失败：{str(e)}")
        raise HTTPException(status_code=500, detail={"code": 500, "message": "服务器内部错误"})
```

---

### 2️⃣ **分页响应规范**

```python
from pydantic import BaseModel, Field
from typing import List, Any


class PaginationMeta(BaseModel):
    """分页元数据"""
    total: int = Field(description="总记录数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页大小")
    total_pages: int = Field(description="总页数")


class PaginatedData(BaseModel):
    """分页数据结构"""
    items: List[Any] = Field(description="当前页数据项")
    meta: PaginationMeta = Field(description="分页元数据")


# 使用示例
class LinkagePlanPagination(PaginatedData):
    items: List[LinkagePlanOut]
    meta: PaginationMeta
```

---

## 🖥️ 前端调用规范

### 1️⃣ **统一的响应处理逻辑**

在 `src/utils/request.js` 的响应拦截器中：

```javascript
// 响应拦截器
request.interceptors.response.use(
  (response) => {
    const { data } = response
    
    // 如果返回的是直接的数据对象（没有 code 字段），视为错误
    if (!data || typeof data.code !== 'number') {
      console.error('API 响应格式错误:', response.config.url, data)
      return Promise.reject({
        code: 500,
        message: '服务器响应格式异常',
        data: null
      })
    }
    
    // 成功响应
    if (data.code === 200) {
      return data
    }
    
    // 业务错误
    return Promise.reject(data)
  },
  async (error) => {
    // ... 错误处理逻辑
  }
)
```

---

### 2️⃣ **组件中的数据获取模式**

✅ **推荐的组件编写方式**:

```vue
<script setup lang="ts">
import * as LinkageApi from '@/api/linkage'

// 加载预案列表
async function loadPlans() {
  loading.value = true
  try {
    const res = await LinkageApi.getLinkagePlans(params)
    
    // ✅ 统一处理格式
    if (res.code === 200 && res.data) {
      plans.value = res.data.items || []
      pagination.total = res.data.total || 0
      
      // 可选：显示 success 提示
      // ElMessage.success(res.message || '获取成功')
    } else {
      // ✅ 错误提示
      ElMessage.error(res.message || '获取预案列表失败')
    }
  } catch (error) {
    console.error('加载预案列表失败:', error)
    ElMessage.error(error.message || '获取预案列表失败')
  } finally {
    loading.value = false
  }
}
</script>
```

❌ **错误的编写方式**（应避免）:

```javascript
// ❌ 没有检查 res.code
if (res && Array.isArray(res.items)) {
  // 这种写法假设 API 返回的是裸数据对象，违反规范
}

// ❌ 直接使用 res.data.items 而不检查 res.code
plans.value = res.data.items  // 如果 res.code !== 200，会导致逻辑错误
```

---

## 🚨 常见错误模式与解决方案

### 错误模式 1: 后端直接返回业务数据

```python
# ❌ 错误
@router.get("", response_model=LinkagePlanPagination)
async def get_linkage_plans(...):
    return LinkagePlanPagination(items=[], total=0)  # 缺少包装层

# ✅ 正确
@router.get("", response_model=Response[LinkagePlanPagination])
async def get_linkage_plans(...):
    return Response(
        code=200,
        message="success",
        data=LinkagePlanPagination(items=[], total=0)
    )
```

---

### 错误模式 2: 前端混用两种响应格式

```javascript
// ❌ 错误：假设 API 返回的是裸数据
if (res && Array.isArray(res.items)) {
  plans.value = res.items
}

// ✅ 正确：始终使用统一格式
if (res.code === 200 && res.data) {
  plans.value = res.data.items || []
}
```

---

### 错误模式 3: API endpoint 签名不一致

```python
# ❌ 错误：有的用 response_model，有的直接返回 dict
@router.get("", response_model=DeviceListOut)
async def list_devices(...):
    return {"code": 200, "data": {...}}  # 签名和返回值不匹配

# ✅ 正确：保持一致
@router.get("", response_model=Response[DeviceListOut])
async def list_devices(...):
    return Response(code=200, message="success", data=...)
```

---

## ✅ 代码审查清单 (AI 开发时必须检查)

当你让 AI 生成 API 相关代码时，请务必检查以下项：

### **后端代码检查项**

- [ ] 是否使用了统一的 `Response` 包装类？
- [ ] 所有 API endpoint 是否都返回 `{code, message, data}` 格式？
- [ ] 分页 API 是否包含 `total`, `page`, `page_size` 字段？
- [ ] 权限验证是否正确配置（如 `require_permission()`）？
- [ ] SQL 查询的 count 语句是否符合 SQLAlchemy 2.0 规范？
- [ ] 错误处理是否返回合适的 `HTTPException`？
- [ ] 是否导入了必要的依赖（如 `func.count`）？

### **前端代码检查项**

- [ ] 是否从统一的 API 模块导入（如 `@/api/linkage`）？
- [ ] 是否检查了 `res.code === 200` 后再处理数据？
- [ ] 是否在 `catch` 块中捕获并提示错误？
- [ ] 是否避免了直接访问 `res.items` 而不是 `res.data.items`？
- [ ] 是否有加载状态指示（loading）？
- [ ] 表单提交后是否刷新列表？

### **API 路由检查项**

- [ ] Router prefix 是否重复（如 `/linkage-plans/linkage-plans`）？
- [ ] 是否在 `__init__.py` 中正确注册了 router？
- [ ] 标签（tags）是否一致？
- [ ] OpenAPI Schema 是否正确生成？

---

## 🔍 验证方法

### **1. 手动测试 API**

```bash
# 获取 OpenAPI Schema
curl http://localhost:8000/openapi.json | jq '.paths[] | select(.|test(test("linkage")))'

# 测试具体 endpoint
curl -X GET "http://localhost:8000/api/v1/linkage-plans?page=1&page_size=10" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### **2. 浏览器 Console 验证**

```javascript
// 检查 API 路径
fetch('http://localhost:8000/openapi.json')
  .then(r => r.json())
  .then(data => {
    const paths = Object.keys(data.paths).filter(p => p.includes('linkage'));
    console.log('✅ Linkage API Paths:', paths);
    
    // 验证没有重复路径
    const hasDuplicates = paths.some(p => 
      p.split('/').filter(x => x.includes('linkage')).length > 1
    );
    console.log(hasDuplicates ? '❌ 有重复路径' : '✅ 路径正常');
  });

// 测试 API 响应格式
fetch('http://localhost:8000/api/v1/linkage-plans?page=1&page_size=10')
  .then(r => r.json())
  .then(data => {
    console.log('✅ 响应结构:', JSON.stringify(data, null, 2));
    console.assert(data.code === 200, '应该有 code: 200');
    console.assert(data.data, '应该有 data 对象');
  });
```

---

## 📝 最佳实践示例

### **完整的 CRUD API 模板**

```python
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from typing import Optional
from app.api.v1._common import Response  # 统一响应包装器
from app.models.linkage import LinkagePlan
from app.schemas.linkage import LinkagePlanPagination, LinkagePlanCreate, LinkagePlanOut
from app.crud.linkage import linkage_plan_crud
from app.core.dependencies import get_current_active_user, require_permission
from app.models.user import User
from app.db.session import AsyncSession

router = APIRouter(tags=["Linkage Plans"])


@router.get(
    "",
    response_model=Response[LinkagePlanPagination],
    summary="获取预案列表"
)
async def get_linkage_plans(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页大小"),
    org_id: Optional[int] = None,
    fire_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("linkage:view")),  # ⭐ 权限验证
):
    """分页查询联动预案列表"""
    
    # 构建查询条件
    stmt = select(LinkagePlan)
    if org_id is not None:
        stmt = stmt.where(LinkagePlan.org_id == org_id)
    if fire_type is not None:
        stmt = stmt.where(LinkagePlan.fire_type == fire_type)
    
    # 查询总数
    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one_or_none()
    
    # 查询数据
    skip = (page - 1) * page_size
    stmt = stmt.order_by(LinkagePlan.created_at.desc()).offset(skip).limit(page_size)
    results = (await db.execute(stmt)).scalars().all()
    
    # 返回统一格式的响应
    return Response(
        code=200,
        message="success",
        data=LinkagePlanPagination(
            items=[LinkagePlanOut.model_validate(plan) for plan in results],
            total=total or 0,
            page=page,
            page_size=page_size,
        )
    )
```

---

## 🎓 AI 协作规范

### **Prompt 模板：让 AI 生成正确的 API 代码**

当你在项目中让 AI 开发新功能时，可以使用以下 prompt：

```
请帮我创建一个 API endpoint，要求如下：

1. **使用统一的响应格式**:
   - 必须返回 `{code, message, data, timestamp}` 格式
   - 使用 `Response` 包装器
   
2. **添加权限验证**:
   - 根据场景选择合适的权限代码（如 `linkage:view`, `device:create`）
   
3. **分页支持**（如果是列表接口）:
   - 参数：`page`, `page_size`
   - 返回：`items`, `total`, `page`, `page_size`
   
4. **SQLAlchemy 2.0 规范**:
   - count 查询使用：`select(func.count()).select_from(stmt.subquery())`
   - 不要使用 ORM 风格的 `.count()` 方法
   
5. **错误处理**:
   - 使用 `HTTPException` 抛出错误
   - 验证必填字段，返回 400 错误

6. **代码审查点**:
   - 检查 router prefix 是否重复
   - 检查响应模型是否正确定义
   - 检查是否需要导入额外的依赖
```

---

## 📚 相关文件

- `backend/app/core/responses.py` - 统一响应格式定义
- `backend/app/core/dependencies.py` - 权限依赖注入
- `frontend/src/utils/request.js` - 统一响应拦截器
- `docs/test/3.4-linkage-integration-test-report.md` - 集成测试报告

---

## 🔄 持续改进

本规范将在每次发现类似 bug 时进行更新。如果发现新的模式错误或改进建议，请贡献 PR。

---

**最后更新于**: 2026-09-10  
**维护人**: Qoder AI Assistant  
**版本**: v1.0