---
   
  # Claude 开发进度归档协议和构建规范

  > 本文件只保留**协议定义**、**最近 3 条进度摘要**和**滚动待办池**。
  > 完整历史会话记录见 `.claude/sessions/*.md`，技术决策见 `.claude/decisions.md`。

  ---

  ## 构建规范
  所有 Dockerfile 必须内置大陆镜像源替换（sed 修改 sources.list / 配置 registry），确保无外部依赖即可构建。默认使用阿里云/清华源，多阶段构建每个阶段都要处理。

  ---
  
  ## 引用规范（执行任务前必读）
  
  ### 核心引用文件（优先级从高到低）
  
  1. **生成测试用例前**：先读取 `./testing-guidelines.md`
     - 遵循设计方法、优先级定义、ID 命名体系
     - 可复用的测试侧假设追加到该文件（P2-001 已补齐）
  
  2. **开始业务模块开发前**：先读取 `.claude/decisions.md`
     - DEC-004: 业务表统一加 `created_by`
     - DEC-005: 新页面须登记 `viewComponents` 映射表
  
  3. **前后端 API 集成时**：先阅读 `docs/plan/API_RESPONSE_FORMAT_SPECIFICATION.md`
     - 统一响应格式约定 `{code, message, data, timestamp}`
     - 避免格式不一致导致的解析错误（第 3.4 章节教训）
    
  4. **Celery 技术栈说明**：参考项目根目录 `消防监控管理系统_PRD_v2.0.md` 的 `2.2 Celery 引入时机说明`
     - 3.1~3.6 阶段：暂不引入 Celery，使用 FastAPI `lifespan` + `asyncio.create_task()` 处理定时任务
     - 3.9 统计报表阶段：评估是否引入 Celery（若需跨多个服务协调任务或大数据量导出）
    
  5. **需要查询项目架构或技术细节时**：查阅记忆系统
     - 数据库 Schema: `project_info > project_architecture > Fire Alarm System permission database schema conventions`
     - 环境配置：`project_info > project_environment_configuration`
     - 技术栈：`project_info > project_tech_stack`
  
  ---
  
  ### 🎨 AI 协作协议：API 开发与数据交互约束
  
  #### **一、后端 API 开发约束**
  
  **1. 所有 API 必须返回统一响应格式**
  
  ```json
  {
    "code": 200,
    "message": "success",
    "data": {
      "items": [],
      "total": 0,
      "page": 1,
      "page_size": 10
    },
    "timestamp": 1789015029
  }
  ```
  
  ✅ **正确示例**:
  ```python
  @router.get(
      "",
      response_model=Response[LinkagePlanPagination],
      summary="获取预案列表"
  )
  async def get_linkage_plans(...):
      return Response(
          code=200,
          message="success",
          data=LinkagePlanPagination(items=[], total=0, page=1, page_size=10)
      )
  ```
  
  ❌ **错误示例**（禁止）:
  ```python
  @router.get("", response_model=LinkagePlanPagination)
  async def get_linkage_plans(...):
      return LinkagePlanPagination(items=[], total=0)  # 缺少包装层
  ```
  
  **2. SQLAlchemy 2.0 规范**
  
  ```python
  # ✅ 正确的 count 查询
  from sqlalchemy import func
  count_stmt = select(func.count()).select_from(stmt.subquery())
  total = (await db.execute(count_stmt)).scalar_one_or_none()
  
  # ❌ 错误的 count 查询（Subquery 无 count 方法）
  count_stmt = select(stmt.subquery().count())  # AttributeError!
  ```
  
  **3. Router Prefix 配置最佳实践**
  
  ```python
  # 在 app/api/v1/linkage_plans.py 中
  router = APIRouter(tags=["Linkage Plans"])  # ⭐ 不要在这里加 prefix
  
  # 在 app/api/v1/__init__.py 中
  router.include_router(linkage_plans.router, prefix="/linkage-plans", tags=["Linkage Plans"])
  # ⭐ prefix 只应在聚合文件中添加
  ```
  
  **验证方式**:
  ```bash
  # 检查 OpenAPI schema 是否有重复路径
  curl http://localhost:8000/openapi.json | jq '.paths[] | select(test("linkage"))'
  # ✅ 应该看到：/api/v1/linkage-plans
  # ❌ 不应该看到：/api/v1/linkage-plans/linkage-plans
  ```
  
  **4. 权限验证配置**
  
  ```python
  from app.core.dependencies import require_permission, get_current_active_user
  
  @router.get("")
  async def endpoint(...,
      user: Annotated[User, Depends(get_current_active_user)],
      _: User = Depends(require_permission("linkage:view"))  # ⭐ 明确指定权限码
  ):
      pass
  ```
  
  **常见权限码**: 
  - `linkage:view` / `linkage:create` / `linkage:update` / `linkage:delete`
  - `device:view` / `device:create` / `device:update`
  - `emergency:view` / `emergency:manage`
  
  ---
  
  #### **二、前端组件开发约束**
  
  **1. 统一的响应处理模式**
  
  ```javascript
  // ✅ 正确模式
  const res = await LinkageApi.getLinkagePlans(params)
  if (res.code === 200 && res.data) {
    plans.value = res.data.items || []
    pagination.total = res.data.total || 0
  } else {
    ElMessage.error(res.message || '获取列表失败')
  }
  
  // ❌ 错误模式（混用不同格式）
  if (res && Array.isArray(res.items)) {  // 假设 API 返回裸数据对象
    plans.value = res.items  // 违反统一格式约定
  }
  ```
  
  **2. API 调用封装**
  
  ```javascript
  // src/api/linkage.js
  export function getLinkagePlans(params) {
    return request({
      url: '/linkage-plans',  // 不带 /api/v1 前缀
      method: 'get',
      params,
    })
  }
  ```
  
  **3. 加载状态与错误处理**
  
  ```vue
  <script setup>
  const loading = ref(false)
  
  async function loadPlans() {
    loading.value = true
    try {
      const res = await apiCall()
      if (res.code === 200) {
        // 成功处理
      } else {
        ElMessage.error(res.message)
      }
    } catch (error) {
      console.error('加载失败:', error)
      ElMessage.error(error.message || '操作失败')
    } finally {
      loading.value = false
    }
  }
  </script>
  ```
  
  ---
  
  #### **三、数据格式一致性检查清单**
  
  **代码审查时必须确认**:
  
  **后端审查项**:
  - [ ] 是否使用了统一的 `Response` 包装类？
  - [ ] 所有 endpoint 是否返回 `{code, message, data}` 格式？
  - [ ] 分页 API 包含 `total`, `page`, `page_size`？
  - [ ] SQL count 语句符合 SQLAlchemy 2.0 规范？
  - [ ] Router prefix 没有重复（如 `/linkage-plans/linkage-plans`）？
  - [ ] 权限验证是否正确配置？
  
  **前端审查项**:
  - [ ] 是否检查了 `res.code === 200`？
  - [ ] 是否通过 `res.data.items` 访问数据？
  - [ ] 是否在 `catch` 块中捕获错误？
  - [ ] 是否有加载状态指示？
  - [ ] 表单提交后是否刷新列表？
  
  **API 路由审查项**:
  - [ ] OpenAPI Schema 是否正确生成？
  - [ ] 路径是否有重复？
  - [ ] Tags 是否一致？
  
  ---
  
  #### **四、向 AI 描述需求的 Prompt 模板**
  
  当你需要 AI 帮助开发新功能时，使用以下模板：
  
  ```
  请帮我实现 XXXX 功能，要求：
  
  1. **后端 API 约束**:
     - 使用统一的 `Response` 包装器返回 `{code, message, data}` 格式
     - 添加权限验证：`xxx:view` / `xxx:create`
     - 如果是列表接口，支持分页参数 `page`, `page_size`
     - SQLAlchemy 2.0 规范：count 查询用 `select(func.count()).select_from(stmt.subquery())`
     - Router prefix 只在 `__init__.py` 中添加，不要在 router 文件中重复
  
  2. **前端约束**:
     - 从 `src/api/xxx.js` 导入 API 方法
     - 检查 `res.code === 200` 后再处理数据
     - 通过 `res.data.items` 访问列表数据
     - 添加 loading 状态和错误提示
     - 表单提交后刷新列表
  
  3. **数据格式约定**:
     - 响应格式：`{code: 200, message: "success", data: {items: [], total: 0}, timestamp: ...}`
     - 不要直接返回业务对象（如 `return ItemList(...)`），要包装成 `Response(ItemList(...))`
  
  4. **审查要点**:
     - 检查 path 是否有重复（如 `/xxx/xxx`）
     - 检查权限码是否正确
     - 检查 SQLAlchemy count 语法
  ```
  
  ---
  
  #### **五、已知问题与经验教训**
  
  **教训 1**: API 响应格式不一致导致前端解析失败
  - **场景**: 3.4 联动预案模块的后端直接返回业务对象
  - **现象**: 前端弹出"获取预案列表失败"，但 API 实际返回 200
  - **根因**: 后端返回 `{items, total}`，前端期望 `{code: 200, data: {...}}`
  - **⚠️ 原记录的「修复」是错的**: 当时改的是**前端**——把检查逻辑写成
    `if (res && Array.isArray(res.items))` 去适配违规的后端。那不是修复，是把
    偏离固化进前端：口径从此分裂，后续 3.4/3.6/3.7 三个模块都跟着返回裸数据
    （`repair.py` 11 个、`linkage_plans.py` 7 个、`linkage_logs.py` 2 个端点）。
    更糟的是**前端拦截器对两种形状都放行**，组件读 `res.data` 拿到 undefined 后被
    `|| {}` 兜底，页面显示 0 而**不报错**——维修统计页四项指标长期恒为 0 即此。
  - **正确修复（2026-09-13 已执行）**: 改**后端**，让它返回统一信封；
    前端随之改回 `if (res.code === 200 && res.data)`。
    并加了自动化守卫 `tests/test_api_envelope_contract.py`（AST 静态扫描全部
    119 个路由，任何端点返回裸数据即失败），因为这条约定此前只靠人记。
  - **预防**: 所有新增 API 必须使用统一响应包装器。
    **遇到格式不一致时，先问「哪一边违反了规范」，而不是「怎样让两边都能跑」**——
    后者每次都会选择改前端，因为前端好改。
  
  **教训 2**: Subquery 对象无 count() 方法
  - **场景**: SQLAlchemy 2.0 分页查询中的总数统计
  - **现象**: `AttributeError: 'Subquery' object has no attribute 'count'`
  - **修复**: 改用 `select(func.count()).select_from(stmt.subquery())`
  - **预防**: 使用 SQLAlchemy 2.0 标准写法，参考官方文档
  
  **教训 3**: Router prefix 嵌套导致路径重复
  - **场景**: `linkage_plans.py` 和 `__init__.py` 都添加了 `/linkage-plans`
  - **现象**: OpenAPI Schema 显示 `/api/v1/linkage-plans/linkage-plans`
  - **修复**: 移除 `linkage_plans.py` 中的 prefix，只在 `__init__.py` 保留
  - **预防**: Router 定义中不设置 prefix，只在聚合文件中添加
  
  **教训 4**: 后端代码修改后需重启服务才能生效
  - **场景**: 移除了权限检查后仍然报 403
  - **原因**: uvicorn 的热重载没有生效（可能是缓存问题）
  - **修复**: 停止并重新启动 uvicorn 进程
  - **预防**: 修改权限、路由等关键代码后手动重启服务验证
  
  ---
 
  ---


  ## 一、归档触发条件

  | 类型 | 条件 | 归档深度 |
  |------|------|----------|
  | **主动** | 用户说"退出"、"保存"、"结束"、"bye"或要求总结/保存进度 | 完整归档 |
  | **主动** | 单次回复后检测到会话即将终止 | 完整归档 |
  | **兜底** | 连续 10 分钟无用户新消息，或单轮响应超过 5 分钟 | 轻量归档（仅记录时间、分支、未提交变更、进行中任务标题） |

  ---

  ## 二、执行步骤

  1. **审计代码变更**
     - 运行 `git status --short` 和 `git diff --stat`（或等效检查）
     - 区分**已提交变更**（有 commit hash）和**未提交变更**（working tree）
     - 如无代码变更，跳过"代码变更清单"，仅记录对话内容进度

  2. **总结进度**
     - 提取：已完成 / 进行中 / 阻塞项
     - 对比上次归档的测试数据，计算增量（+N）

  3. **写入独立会话文件**
     - 路径：`.claude/sessions/YYYY-MM-DD-HHMM.md`
     - 按第三节"会话文件格式"填写

  4. **更新索引与待办池**
     - 在 `CLAUDE.md` 的"📋 最近进度"区域顶部插入新摘要，保留最多 **3 条**
     - 超出 3 条的旧摘要移至 `.claude/sessions/index.md`
     - 同步更新"🎯 滚动待办池"：将本次产生的后续任务按 P0/P1/P2 纳入，并更新已有任务状态

  5. **向用户汇报**
     - 3 句话总结本次成果
     - 1 句话说明待办池当前最高优先级项

  ---

  ## 三、会话文件格式（`.claude/sessions/YYYY-MM-DD-HHMM.md`）

  ### 1. 元信息头部
  ```markdown
  ---
  session_date: 2026-08-03 14:30
  branch: main
  commit: a1b2c3d  (若无则为 "未提交")
  status: completed | interrupted | timed_out
  ---

  2. 变更摘要

  一句话概括本次核心成果。

  3. 代码变更

  - 优先引用 commit：如有提交，直接写 commit hash + message，不再重复文件表格
  - **Commit**: `a1b2c3d` feat: add notification bell dropdown
  - **范围**: `frontend/src/components/` + `frontend/src/api/hooks.ts`
  - **Diff 摘要**: 新增 NotificationsBell 组件，接入 useNotifications hook，Badge 未读数轮询
  - 仅在以下情况使用文件表格：未提交变更、跨 3 个以上目录的零散修改、无法用一个 commit 概括的批量重构
  | 操作 | 文件路径 | 说明 |
  |------|----------|------|
  | 修改 | `backend/app/main.py` | 临时调试端口 |

  4. 构建与测试（必须含增量对比）

  记录命令 + 结果 + 与上次的增量：
  - **后端**: `pytest` 152 passed (+2 较上次, 新增 test_auth.py 2)
  - **前端**: `vitest run` 41 passed (+2 较上次)
  - **Docker**: `docker compose build` 成功

  5. 当前进度（统一状态符号）

  ┌──────┬────────────────────────────────┐
  │ 符号 │              含义              │
  ├──────┼────────────────────────────────┤
  │ [x]  │ 已完成（已提交并通过验证）     │
  ├──────┼────────────────────────────────┤
  │ [~]  │ 进行中（有未提交代码或待验证） │
  ├──────┼────────────────────────────────┤
  │ [ ]  │ 待开始                         │
  ├──────┼────────────────────────────────┤
  │ [-]  │ 已放弃 / 决定不做              │
  └──────┴────────────────────────────────┘

  示例：
  - [x] Task 1：登录页重构
  - [~] Task 2：看板拖拽乐观更新（剩余回滚测试未写）
  - [ ] Task 3：WebSocket 实时通知

  6. 关键决策（ADR，跨会话需同步到 .claude/decisions.md）

  记录"为什么选择方案 A 而不是 B"，以及 workaround：
  - **DEC-042**: 降级 pytest-asyncio 1.4.0 → 0.23.8
    - **原因**: 1.4.0 移除对 `@pytest.fixture` 的 async 支持，与现有 40+ 测试不兼容
    - **影响范围**: `tests/backend/conftest.py`
    - **回滚条件**: 待 pytest-asyncio 2.x 兼容后统一升级，预计 2026 Q4 评估

  7. 环境偏差（结构化，必填）

  - **Python**: 3.10.10（计划 3.12，因 SQLAlchemy 限制暂缓）
  - **Node**: 20.11.0（正常）
  - **依赖变更**: pytest 9.1.1 → 8.4.2, pytest-asyncio 1.4.0 → 0.23.8
  - **其他**: 无

  8. 阻塞点与风险

  - **阻塞**: 前端 `msw` 与 Vitest 3 不兼容，拦截器未生效（P1）
  - **风险**: Docker 构建时 npm 源偶发超时，已加 `--maxsockets 1` 缓解

  ---

  ## 📋 最近进度

- **2026-09-14 23:11 归档（刷新后用户名回退「用户」+ 登录响应 `roles` 死字段清理）**：一个用户可见缺陷 + 一处「同一份状态两个写入方」的实例。**缺陷**（`210b6b7b`）：登录后右上角显示真实姓名，**F5 刷新即变成字面量「用户」**。根因链——`authStore.userInfo` 是**纯内存**态，而 `accessToken` 会从 localStorage 恢复（`stores/auth.js:9`），刷新后 token 恢复使守卫放行导航，但 `userInfo` 重新初始化为 `ref(null)`，而它的填充函数 `fetchUserInfo()`（`stores/auth.js:29`）**在全仓库应用代码里没有任何调用方**（只有它自己的单测在调，`stores/__tests__/auth.spec.js:61`）→ `AppHeader.vue:9` 的三段兜底 `userInfo?.real_name || userInfo?.username || '用户'` 落到最后一档。登录瞬间正常，是因为 `login()` 用登录响应的 `data.user` 填了一次（`stores/auth.js:22`）——**两条路径只有一条有填充**，这正是缺陷能长期存在的原因。修法：`initializeRoutes()` 的 `initPromise` 由「只跑 `generateRoutes()`」改为**顺序** `await fetchUserInfo()` → `await generateRoutes()`；**顺序刻意放在前**，因为 `isRoutesLoaded` 在 `generateRoutes()` 末尾才置位，若用户信息在其后失败会卡在「路由已就绪、用户为空」的半初始化态——守卫见 `isRoutesLoaded === true` 直接跳过重试，`userInfo` 永远为 null（等于把缺陷埋得更深）；且**不吞异常**（吞掉它正是教训 1 的形态：静默显示兜底文案而非报错）。**清理**（`6d84d03b`）：登录响应返回 `["chief"]`（字符串数组）而 `/users/me` 返回 `[{id, role_code, role_name}]`（对象数组），两者都写进同一个 `userInfo` → 两个写入方、两种形状。经查该字段**两端零消费者**（前端唯一 `userInfo` 读取点只取 real_name/username；全前端唯一 `roles` 消费点 `OrderList.vue:201` 遍历的是派单候选人列表而非 userInfo；后端测试只断言 access_token/username/real_name）→ 移除 `roles`，但**保留 `id`/`username`/`real_name`**（这三个不是死字段，删了登录瞬间没名字可显示）。**验证**：前端 `vitest run` 50 files / **350 passed**（起点基线 45/315，增量含并发会话；本会话新增 3 条，router spec 13→16）、`npm run build` 成功（router 新增 import 无循环依赖）、`test_auth.py` **7 passed**（改前 6 passed/1 failed，失败信息即结论：`'roles': ['roleholder_role']` 确实在响应里）、认证+用户+角色+权限相邻套件 **82 passed**；前端 3 条与后端 1 条用例均**先写后改**并确认改动前打红。⚠️ **后端全量套件刻意未跑**——P1-012 的不稳定（38/40/38 failed、收集数 441/451/454 浮动）使跑出的数字无法判断是否本改动引入，只会污染结论；改用「定向套件 + 全仓库引用清查」两条确定性证据（grep 出的所有 `user.roles` 均为 ORM 访问，登录响应载荷只有 `auth.py:74` 与 `stores/auth.js:21-22` 两个消费者）。⚠️ **P1-012 已从「测试噪声」升级为「基础设施问题」**：这是它第二次实际妨碍验证工作（首次是 2026-09-13 讨论守卫价值时）。⚠️ 归档时工作区仍有 peer 会话未提交的 2 个文件（`report_export_service.py`/`test_report_export.py`，导出文件同名覆盖 → 改 `task_no` 前缀），本会话全程未触碰，暂存时逐个 `git add` 未带走。**新增 DEC-022/DEC-023**。会话文件见 `.claude/sessions/2026-09-14-2311.md`。

- **2026-09-13 21:15 归档（统一信封 20→0 + 联动越权修复 + 权限码审计接线 + FR-033 巡检调度）**：把「API 统一信封」这条**只靠人记的约定**从 20 个违规收敛到 0 并装上静态守卫，过程中挖出**两条未登录即可读的越权**。**信封迁移**（`cb4d91de`/`14a31932`/`b8e860de`，共 20 个端点）：`linkage_logs` 2 + `linkage_plans` 7 + `repair` 11，全仓库 119 个端点口径归零；新增 `tests/test_api_envelope_contract.py`（AST 扫全部路由，返回裸数据即失败，文件/流式下载与 204 天然豁免）。**关键判断转向**：此前三处格式不一致都是改**前端**去适配裸后端（把偏离固化进前端，导致 3.4/3.6/3.7 三个模块跟着返回裸数据），本次改为改**后端**——因为 `request.js` 响应拦截器**对两种形状都放行**，裸返回**不报错**，组件读 `res.data` 得 `undefined` 再被 `|| {}` 兜底，**页面显示 0 而一切正常**，维修统计页四项指标恒为 0 就是这么漏了几个月。**越权修复**：`3c20c3e0`/`2f5df161` —— 联动日志与联动预案列表端点**完全没有鉴权**，未登录即可读取（预案含 `actions` 配置）。**权限审计**：`a66da2f7` repair 域 11 个端点接上 `repair:*` 权限码并补数据范围（`repair_service.repair_scope_condition()`，self 口径是「我报的/我修的/我验收的/我建的」，dept 经 `Device.org_id` 折算）——此前 `repair:*` 5 个码在 `init_data.py` 定义了也逐角色授予了，却**没有任何端点校验**（代码用手写 `role_code=="chief"` 判断），后果是「授予/撤销这些码」是**空操作**，RBAC 看起来生效实际没接线；新增 `tests/test_permission_coverage.py` 守卫（含 `UNENFORCED_ALLOWLIST` 10 条：7 条口径不符 + 3 条孤儿码）；`d35e5e46` 合并四份重复的 `make_xxx_user` 构造器到 `tests/auth_helpers.py`。**FR-033**（`781cd92f`/`8bee12bb`/`cfa68893`）：`InspectionScheduler` **全仓库无人引用**（`git log -S InspectionScheduler -- app/main.py` 为空），主循环里只有 `# ... 具体生成逻辑待补充` 加一句 `print`——「每日凌晨自动生成当日任务」实际只能靠人工点按钮，B-3 漏检扫描同样从未跑过；已按 `tasks/offline_monitor.py` 模式重写并接进 lifespan，新增 `app/core/timezone.py`（业务时区：容器跑 UTC，按本地时间算 00:05 实为北京 08:05，且 `date.today()` 产出错误日期；**只用于调度器，不动容器 TZ**）、补 `(plan_id, task_date)` 唯一约束 + 迁移（模型注释声称有、实际不存在，`WORKERS>1` 下必然双写）、`generate_daily_tasks()` 尊重计划有效期与 `cycle_type`、SAVEPOINT 逐计划隔离失败、`8bee12bb` 修 `generate_tasks_for_plan` 只 flush 不 commit 导致「接口说生成 N 条、库里 0 行」；18 条用例。**前端**：`762579a1` 清 10 条红灯（Node 22+ 实验性 Web Storage 在 `globalThis` 上定义 `localStorage` getter，缺 `--localstorage-file` 时返回 `undefined`，遮蔽 jsdom 的），`57d7f1cf` 维修统计页从裸对象改回读信封 `res.data`。**文档**：`7c606c02`/`74cc4d23` 更正 3.6 测试报告的失效口径。**验证**：后端 `pytest -q` 38 failed / 355 passed / 60 skipped（**⚠️ 不稳定**：本会话三次运行为 38/342、40/350、38/355，**连收集到的用例总数都在变**（441/451/454）→ **「基线 38 条」这类单点数字已不可用于判断回归**）、前端 `vitest run` 45 files / **315 passed**（本会话起点为 10 条红灯 / 305）、容器实测 FR-033 启动补跑生成 2 条且重启后 `新建 0，已存在 2`（幂等成立）、`alembic_version = add_inspection_task_plan_date_uq` 且唯一约束在真实 PG 中存在、信封+权限两个守卫 7 passed、分类器 6/6 正确。**新增 DEC-018~DEC-020**。⚠️ **发现两条疑似真实产品缺陷**（非测试问题，已核实代码事实但未追影响面，落 drill/emergency 域）：`app/services/emergency_service.py:392` `NameError: name 'update' is not defined`（该文件只 `from sqlalchemy import select, func`）、`app/crud/drill_crud.py:230` `DrillEvaluation` 无 `total_score` 字段（真实字段为 `id/drill_id/items/problems/improvements/evaluation_summary/...`）。⚠️ 本会话进行期间有 peer 会话 `backend-3f` 在**同一仓库**并发改动（`repair.py`/`users.py`/`user_service.py`/`OrderList.vue` 等 8 文件 + 1 新建），于 20:59 提交为 `2382140a`；本会话全程未触碰其文件，其归档文件 `2026-09-13-2100.md` 亦未被覆盖。会话文件见 `.claude/sessions/2026-09-13-2115.md`。

- **2026-09-13 21:00 归档（补齐「开始维修」+ 维修操作列权限口径统一 + repair 响应构造归一）**：修复 3.7 维修工单的一处**真缺陷**——状态机表里 `assigned → repairing`、`returned → repairing` 两条转移定义了却无任何实现，而 `crud.complete()` 要求 `status == "repairing"`，于是工单永久停在「已派单」、「完成维修」按钮（`v-if="row.status === 'repairing'"`）永不显示，`pending → completed` 整条闭环走不通（前端 `handleStartRepair` 是个只弹「开始维修功能待实现」的桩函数）。**后端**：`crud.start()` 查 `REPAIR_ORDER_STATUS_TRANSITIONS` 判可转移性（不硬编码状态串）、`PUT /repair-orders/{id}/start`（`repair:repair` + 归属检查，口径与 `/complete` 一致）、`GET /users` 新增可选 `permission` 参数（按权限码过滤候选人，条件同时作用于 items 与 count）；**前端**：`handleStartRepair` 接真实接口、「重新维修」由 `/complete` 改接 `/start`（原先必然 400）、操作列全部改 `v-permission` 判权限码（派单 `repair:assign`、验收 `repair:accept`），删除 `isChief`/`authStore` 角色码判断、派单候选人下拉框带 `permission=repair:repair`；**重构**：`repair.py` 8 份重复的 25 行字段映射收敛为 `_order_out()`，615 → 467 行。**验证**：后端 `pytest -q` 38 failed / 355 passed（改动前 342，**+13** = 新增 10 + 3；5 个失败桶与改动前逐一相同）、前端 `vitest run` 45 files / 315 passed（repair 目录 14 → 24）、`npm run build` 成功；4 组变异验证（拆守卫逐条打红对应用例）。**commit `2382140a`**（9 文件 +682/-227）。**实测澄清一条误判**：主管的 `system:user` 本就存在（`init_data.py` 的 `bind_permissions(chief_role, list(perm_map.values()))` 绑定全部已定义权限码），用临时 SQLite 实跑 `init_data.py` 两遍确认 chief 76/76、差集为空、幂等——故**未**往 `ROLE_PERM_MAP["chief"]` 加死代码。新增 DEC-014~DEC-017。⚠️ 本次归档**只覆盖这一个提交**，当天其余 23 个提交（信封迁移、权限审计、巡检调度 FR-033、设备回收站等）无会话文件，归档链路有 3 天断档。会话文件见 `.claude/sessions/2026-09-13-2100.md`。


> 更早摘要（早于 2026-09-13 21:00）已移至 `.claude/sessions/index.md`。

  ---
  四、滚动待办池（CLAUDE.md 中维护，跨会话累积）

  ▎ 不是每次新建，而是滚动更新已有条目。已完成的条目保留 1 次归档后移除。

  ### 🎯 滚动待办池

> 3.1 的 10 条已完成项与 3.2 的 9 条已完成项（P0-009~P0-015、P1-004~P1-005）均已移出本池，归档见 `.claude/sessions/index.md`。
> 3.2 消防设备档案已于 2026-09-09 02:18 交付（`pytest` 119 / `vitest` 88 / build OK / 容器端到端通过），容器级 E2E 已于 02:47 固化为可重跑模块 `backend/tests/e2e/test_device_api_e2e.py`（`-m e2e`，31 passed + 1 xfailed）。
> **3.3 实时监控与电子地图已于 2026-09-09 05:45 交付**（`pytest` 159 / `vitest` 106 / build OK / e2e 47+1 xfailed / M1 帧延迟 P95 0.111s），E2E 固化在 `tests/e2e/test_monitor_e2e.py`（16 条）。
> **P1 级全部收尾项已于 2026-09-09 22:21 完成并移出本池**（P1-003 登录日志审计、P1-006 Alembic baseline、P1-007 单资源数据权限、P1-008 3.3 压测），连同 P2-001/P2-004/P2-009 一并归档于 `.claude/sessions/index.md`。池内剩余为 P0 联调收尾与 P2 级技术债。
> **2026-09-13 21:00 清池**：P0-016、P2-002、P2-003、P2-005、P2-006、P2-007 六条自 2026-09-09 起滞留池中的 `[x]` 条目已按维护规则移出，移出清单见 `.claude/sessions/2026-09-13-2100.md`。
> **2026-09-13 21:15 补录**：信封迁移/权限审计/FR-033 三个方向的会话摘要已回填（`.claude/sessions/2026-09-13-2115.md`），并据此新增 P1-010~P1-012、P2-014；P1-009 由 `[ ]` 改为 `[~]`（14/23 已补）。
> **2026-09-14 23:11 归档**：本次**无新增待办条目**。两处改动（`210b6b7b` 修用户名回退 / `6d84d03b` 清登录响应 `roles`）均已闭环并各带先写后改的回归用例；唯一被否的备选（删 `stores/auth.js:22` 的冗余写入）属「单一来源 vs 冗余兜底」的取舍而**非缺陷**，记在会话文件的 `[-]` 中，不入池。P1-012 备注已更新（该条随后被同日复核推翻，见下）。
> **2026-09-14 追记（复核 P1-012 后）**：归档后的实测复核产出三条结论——① **「套件不稳定」前提未复现**（`--collect-only` ×2 各 478 条、用例集合 diff 为空；全量 ×3 均为 `38 failed/379 passed/60 skipped/1 xfailed`，478 自洽，且两次的 `FAILED` 列表**逐条相同**）；② **38 条失败实为 6 个根因**，其中 23 条是同一个 SQLite 环境问题；③ **P1-011 从「待判定」升为确认的产品缺陷**，含一个**必然 500** 的端点 `GET /api/v1/drills/statistics`。据此改写了 P1-011 / P1-012 的备注，并新增 **P1-013**（notifications / emergency 两域因 `BigInteger` 主键在 SQLite 下不自增而测试零覆盖）。故本次归档**最终新增 1 条待办**——上段的「无新增」以本追记为准。

| ID | 事项 | 优先级 | 状态 | 引入会话 | 备注 |
|----|------|--------|------|----------|------|
| P1-009 | 补 2026-09-13 未归档会话的摘要（**部分完成**） | P1 | [~] | 2026-09-13 | 当天 24 个提交原有 23 个无摘要。`2026-09-13-2115.md` 已回填 **14 个**（信封迁移 `cb4d91de`/`14a31932`/`b8e860de`、联动越权 `3c20c3e0`/`2f5df161`、权限审计 `d35e5e46`/`b24f877c`/`a66da2f7`、巡检 FR-033 `cfa68893`/`8bee12bb`/`781cd92f`、前端 `762579a1`/`57d7f1cf`、文档 `7c606c02`/`74cc4d23`）。**剩余 8 个**（12:11–16:50，属更早会话）仍缺：设备回收站 `926d3196`、15 处契约缺陷 `36dad38a`、巡检计划操作列 `87054c62`、`2483f726`、`7f1ff579`、`bf9c2e6e`、`1af88f63`、`3fe01c7a`；`.claude/sessions/2026-09-11-0030.md` 仍未写入最近进度。补档来源：`git log` + 各提交的详细 commit message |
| P1-010 | `emergency_service.py` 少 import `update` 导致 NameError | P1 | [ ] | 2026-09-13 | 实测报错 `NameError: name 'update' is not defined`，位置 `app/services/emergency_service.py:392`。**该文件顶部只有 `from sqlalchemy import select, func`**，函数内只局部 import 了模型。⚠️ **影响面未确认**——需先确认哪个端点会走到此处（若是通知已读链路，则是线上 500）。2026-09-13 由测试套件失败暴露，非新引入。修法：补 `update` 到顶部 import 并加回归用例 |
| P1-011 | drill / emergency 域引用不存在的模型字段（已定性为产品缺陷） | P1 | [ ] | 2026-09-13 | **2026-09-14 复核已定性：不是「模型缺字段」，是代码用了不存在的名字，且写入方与读取方都错。** `DrillEvaluation` 真实字段为 `evaluated_by`（`models/drill.py:80`，注释「评估人用户 ID」），而 `evaluator_id` 出现在十几处**生产代码**：`crud/drill_crud.py:274/287`、`services/drill_service.py:110/128`、`api/v1/drills.py:565` 三处**构造**；`drills.py:237/538/580` **读取**；`schemas/drill.py:144` 还把它暴露给前端 → 演练评估的**写入链路与详情返回均坏**（7 条用例 `TypeError: 'evaluator_id' is an invalid keyword argument`）。`crud/drill_crud.py:230` 的 `total_score` 由真实端点 **`GET /api/v1/drills/statistics`（`api/v1/drills.py:202-213`，需 `drill:stat`）** 调用 → **该端点必然 500**。同类（本次新发现）：`EmergencyTimeline` 无 `user_id`，真实字段是 `operator_id`（`models/emergency.py:49`）。⚠️ **待决策（ADR 级）**：`evaluator_id` 与 `evaluated_by` 哪个是正名——schema 与 API 已把 `evaluator_id` 暴露给前端，故**改模型名（含迁移）影响面小于改十几处代码 + schema + 前端**；但 `evaluated_by` 可能与其他表命名更一致。**原记录（2026-09-13）**：实测三处：`app/crud/drill_crud.py:230` 用 `DrillEvaluation.total_score`，而该模型真实字段只有 `id/drill_id/items/problems/improvements/evaluation_summary/evaluated_by/evaluated_at/created_at/updated_at`；`app/services/drill_service.py:95` 访问 `DrillEvent.summary`、`:192` 访问 `DrillEvent.actual_start_at`，均不存在。另有一批 `TypeError: 'evaluator_id' / 'user_id' is an invalid keyword argument for <Model>`（约 8 条，测试与模型漂移）。需先判定「是模型缺字段」还是「代码引用了废弃字段」，再决定补模型还是改代码 |
| P1-012 | 后端全量套件的 38 条失败需分类清零（**「不稳定」前提未复现**） | P1 | [ ] | 2026-09-13 | **2026-09-14 复核：前提未复现，且 38 条只有 6 个根因。** 证据：`--collect-only` ×2 各 **478** 条、用例集合 `diff` **为空**；全量运行 ×3 均为 `38 failed / 379 passed / 60 skipped / 1 xfailed`（38+379+60+1=478 自洽、**零 ERROR**），且其中两次的 `FAILED` 列表**逐条相同**——是**集合级**比对，不只是计数相同。原记录的 441/451/454（passed 342/350/355）更可能是**那三次运行之间工作树在加用例**（总数与 passed 同步单调增长：+10/+3 与 +8/+5），而非收集不确定 → **建议停止把「基线 38 条」当作不稳定证据，改为「未复现」**。38 条的根因分解：**① 23 条** = `BigInteger` 主键在 SQLite 下不自增（→ 已立 **P1-013**）；**② 7 条** = drill `evaluator_id` 无此字段；**③ 4 条** = drill `total_score`/`summary`/`actual_start_at` 不存在；**④ 1 条** = `EmergencyTimeline.user_id` 应为 `operator_id`（②③④ 均归 **P1-011**，且都是**生产代码缺陷**）；**⑤ 2 条** = `SQLite DateTime type only accepts Python datetime`；**⑥ 1 条** = 测试自身 `object EmergencyEvent can't be used in 'await' expression`（**测试 bug**）。真正的风险仍在：**任何新增守卫的告警都会被既存红淹没**。**先修不稳定，再逐类清零**。**原记录（2026-09-13）**：实测三次结果不同：`38 failed/342 passed`、`40 failed/350 passed`、`38 failed/355 passed`，**连收集到的用例总数都在变**（441/451/454）。后果：**「基线 38 条」这类单点数字已不可用于判断回归**，且任何新增守卫的告警都会被淹没在既存红里（2026-09-13 讨论「回归守卫有啥用」时确认这是守卫价值的主要威胁）。已按 `--tb=line` 分四类（SQLite `BIGINT PRIMARY KEY` 自增 ~22、测试与模型漂移 ~8、疑似真实产品缺陷 ~6、其余）。**先修不稳定，再逐类清零**。⚠️ **2026-09-14 第二次实际妨碍验证**：本会话改动落在 auth 域（`auth_service.py` 移除登录响应 `roles`），因无法用全量套件的数字判断回归，只能改用「定向套件 + 全仓库引用清查」两条证据。它已从「测试噪声」升级为**阻碍其它验证工作的基础设施问题**，建议提升优先级。⚠️ **2026-09-14 追记**：该「升级为基础设施问题」的判断建立在「套件不稳定」之上，而同日复核显示**不稳定未复现**——**妨碍是真实的，但成因不是套件不确定**，而是这 38 条既存红从未按根因分类：新守卫的告警落进去无法分辨。正确的下一步因此**不是「修稳定性」，而是按根因清零**（P1-013 的 23 条 + P1-011 的 12 条 + 余下 3 条） |
| P1-013 | notifications / emergency 两域测试**零覆盖**——`BigInteger` 主键在 SQLite 下不自增 | P1 | [ ] | 2026-09-14 | 实测 23 条用例恒失败，根因单一：`models/emergency.py` 三张表用 `Column(BigInteger, primary_key=True, autoincrement=True)`——`EmergencyEvent`:18 / `EmergencyTimeline`:44 / `Notification`:66。**SQLite 只对 `INTEGER PRIMARY KEY` 自增，`BIGINT PRIMARY KEY` 不自增** → 实测 `sqlite3.IntegrityError: NOT NULL constraint failed: notifications.id`（`emergency_events.id`、`emergency_timelines.id` 同样）。PostgreSQL 下 `BIGINT + autoincrement` 走 sequence 正常，**故生产不受影响**；但测试里 `test_notifications.py` 13 条仅 1 条能过、emergency 三文件 11 条同卡在此 → 两域**实际零覆盖**，而这正是 **P1-010 那条 `emergency_service.py:392` NameError 无法判定影响面**的原因。**修法（推荐①）**：① 在 `app/models/types.py` 增一个 `json_type()` 的同族函数——该模块**就是为此而建**，头部注释已写明「生产环境为 PostgreSQL，测试环境为 SQLite……JSONB 在 SQLite 上不可用，需 with_variant 降级」，即**这一类问题此前已被解决过一次，`BigInteger` 只是漏了**——返回 `BigInteger().with_variant(Integer, "sqlite")`，三处主键改用它：SQLite 见 `INTEGER PRIMARY KEY` 即自增、PG 仍 `BIGINT`，**只改测试 DDL，生产零变化**；② 测试改跑真实 PostgreSQL（成本高且拖慢多数用例）。**修完再评估 P1-010**。另：`models/user.py:10` 的 `BigInteger` 是未使用的 import |
| P2-011 | 派单候选人列表对 `system:user` 的解耦 | P2 | [ ] | 2026-09-13 | 候选人走 `GET /users`（需 `system:user`），而派单按钮按 `repair:assign` 门控。今天不成立（只有 chief 持有 `repair:assign`，chief 在 init_data 中绑定全部权限码）。若把 `repair:assign` 授予无 `system:user` 的角色，会出现「看得到按钮、点开候选人列表为空/403」。修法：在 repair 域新增由 `repair:assign` 守卫的候选人端点（如 `GET /repair-orders/repairers`），并撤下 `GET /users` 的 `permission` 参数。见 DEC-016 |
| P2-012 | `init_data` 主管全量授权缺回归守卫 | P2 | [ ] | 2026-09-13 | `bind_permissions(chief_role, list(perm_map.values()))`（「主管 = 全部已定义权限码」）这一机制无测试钉住，被改成硬编码名单不会被发现。2026-09-13 已实测确认其当前正确（chief 76/76、差集为空、二次运行「新增 0 个」）。用户当时选择暂不加守卫，故保留为待办。做法：subprocess + 临时 SQLite 跑 `scripts/init_data.py` 后断言差集为空（`-m e2e` 风格） |
| P2-013 | 其他页面的 `role_code` 判断排查 | P2 | [ ] | 2026-09-13 | 本次只把 `repair/OrderList.vue` 的 `role_code === 'chief'` 改为权限码（DEC-015）。后端 `a66da2f7` 已把 repair 域迁到权限码，其他域是否也残留「前端判角色、后端判权限码」的两套口径未做排查。排查方式：`grep -rn "role_code" frontend/src/ --include=*.vue` 逐处比对后端对应端点的 `require_permission` |
| P2-014 | 权限守卫里 3 个孤儿权限码的去留 | P2 | [ ] | 2026-09-13 | `tests/test_permission_coverage.py` 的 `UNENFORCED_ALLOWLIST` 中 `alarm:handle` / `device:repair` / `monitor:confirm` 三个码在 `init_data.py` 定义了、也授予了角色，但**没有任何端点引用**（另有 7 条是「端点验更粗的 menu 码」的口径不符，非同类问题）。需决定：删除这三个码（连同角色的授权绑定），还是补上对应端点的校验。当前是永久豁免名单，天然会烂成垃圾桶——已加 `test_allowlist_is_not_stale` 拦新增，但存量三条仍在 |
| P2-015 | `GET /inspection-records` 无任何数据范围过滤 | P2 | [ ] | 2026-09-14 | 该端点只有权限码门禁（`inspection:view`），**不叠加 data_scope**。实测维保员（`data_scope=self`）返回**全部** 16 条记录，含 `created_by` 为他人的。`3.6-设备巡检 - 权限测试用例补充.md` 的 TC-PERM-005 明确要求「维保人员只能看到 created_by=self 的巡检记录」，**该规格从未实现**（已在文档中标注）。⚠️ 定口径前先想清楚**锚在哪**：`created_by` 是提交动作的执行者，记录的实际「归属」更可能是 `inspected_by`（参照任务域用 `responsible_user_id` 而非 `created_by` 的理由，见 DEC-012/DEC-021 与 testing-guidelines 第 8 条）。还要连 FR-036「记录归档，支持按设备/人员/时间筛选查询」一起看：归档类数据的可见性未必该按人收窄 |
| P2-016 | 文档里 `self` 口径的收敛 | P2 | [ ] | 2026-09-14 | DEC-012/DEC-021 之后，各域 `self` 锚点已分裂为四种（设备降级 dept、报警降级 dept、任务锚 `responsible_user_id`、维修锚四字段 OR），散落在 4 个域 + `testing-guidelines` + 3.1/3.2/3.6 三份计划里。本次已就地更正 6 处（3.6 计划权限矩阵、3.6 权限用例 TC-PERM-004/005、3.1 `apply_data_scope` 说明、3.2 联调验证方法、testing-guidelines 第 8 条、3.9 OQ-1 措辞），但**没有一个单一出处**。建议在 `docs/plan/` 下建一份「数据权限口径对照表」作为唯一入口，各域文档改为引用它 |
| P2-017 | 组织子树递归 CTE 仍有 5 份内联副本 | P2 | [ ] | 2026-09-14 | `resolve_descendant_org_ids` 已从 `monitor_service` 迁到 `organization_service`（统一入口，2026-09-14），但仍有 5 处各自内联同一段递归 CTE：`core/dependencies.py:143`、`inspection_service.py:81`、`repair_service.py:51`、`statistics_service.py:401`、`user_service.py:82`。其中 `core/dependencies.py` 的 `get_data_scope_filter` 是**死代码**（零调用，只有一句 docstring 提到），可连同 `user_service.apply_data_scope`（生产代码亦已零调用，`app/` 内 0 处，仅剩 10 处直接单测它自身的用例）一并评估删除 |
| P2-018 | `GET /alarm-linkage-logs` 无任何数据范围过滤 | P2 | [ ] | 2026-09-16 | 该端点只有权限码门禁（`linkage:view`），**不叠加 data_scope**，与 P2-015 同类。此前不显眼是因为**联动日志页根本不存在**——后端列表/详情/导出三个端点与 `frontend/src/api/linkage.js` 的封装一直都在，但 `getLinkageLogs` 零调用方、没有任何视图消费；2026-09-16 新建 `frontend/src/views/linkage/Logs.vue` 并登记菜单（`init_data.py` 的 `linkage:log` + `utils/menu.js` 的 `viewComponents`）后，该问题才真正暴露给用户：任何持有 `linkage:view` 的角色都能看到**全部组织**的联动日志，含 `plan_name` / `target_device_name` / `result_message`。⚠️ 定口径前先想清楚**锚在哪**：日志既不是「我报的」也不是「我修的」，且 `AlarmLinkageLog` **根本没有 `created_by` 列**（实测列清单无此项；日志由引擎代系统写入，该字段概念上就不适用）——天然归属应是**触发它的那条告警所属组织**（`alarm.org_id`），退一步也可取 `plan.org_id`；可参照报警域既有的 `alarm_service.visible_org_ids`（:53）与 `scope_by_org`（:58）。⚠️ 三个端点要一起修：`/export` 与 `/{log_id}` 同样无过滤，**导出尤其要紧**——它把符合条件的全部日志落成 CSV |


  维护规则：
  - 新任务从会话摘要中提取，按优先级插入
  - 状态更新时同步修改 [] 符号，不要重复添加同名任务
  - 已完成（[x]）的任务在下一次归档时从池中移除，移入对应会话文件的"已完成"列表
  - **标记 `[ ]` 待开始或 `[-]` 已放弃前，必须先 grep 代码确认确实未实现**。P1-001 曾在 W1 的 B-3 中随登录接口一并落地（锁定 + 日志），却因状态未回填而被连续两次归档误记为「已延期 / 决定不做」，导致真实缺口（日志查询 API）被掩盖
  - 引入依赖外部接口的任务时，须核实该接口是否真实存在，不得沿用计划文档中的「已提供」标注（P0-009 即因计划误标而漏登）

  ---
  五、文件结构规范

  .claude/
  ├── CLAUDE.md              # 本协议 + 最近 3 条摘要 + 滚动待办池
  ├── decisions.md           # 跨会话关键决策（ADR）索引
  ├── sessions/
  │   ├── index.md           # 超出 3 条的历史摘要索引（按时间倒序）
  │   ├── 2026-07-26-1630.md
  │   ├── 2026-07-26-1702.md
  │   └── ...

  ---
  六、兜底归档的轻量格式

  当触发"兜底"条件（超时/断线）时，不要求完整格式，只需在 .claude/sessions/ 写入：

  ---
  session_date: 2026-08-03 15:45
  branch: main
  commit: 未提交
  status: timed_out
  ---

  ### 会话中断
  - **原因**: 用户 10 分钟无响应 / 网络超时 / 单轮响应截断
  - **进行中任务**: Task 3 WebSocket 通知（写到 `frontend/src/stores/notifications.ts` 第 42 行）
  - **未提交变更**: `frontend/src/stores/notifications.ts`（M 未暂存）
  - **下次恢复建议**: 继续完成 notifications store 的 `useWebSocket` hook 接入

  ---
  七、清理与归档过期记录的机制

  - 自动：每次新归档时，CLAUDE.md 只保留最近 3 条摘要，旧摘要按日期追加到 .claude/sessions/index.md
  - 手动：每满 30 条会话文件，建议将最早 10 条压缩为 .claude/sessions/archive-2026-Q3.md
  - 保留期限：所有 .claude/sessions/*.md 保留至少 90 天，之后可归档到 archive/

  ---
