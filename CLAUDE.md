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
  
  4. **需要查询项目架构或技术细节时**：查阅记忆系统
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
  - **修复**: 修改前端检查逻辑 `if (res && Array.isArray(res.items))`
  - **预防**: 所有新增 API 必须使用统一响应包装器
  
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

- **2026-09-09 23:02 归档（P2-008 多 worker WS 推送 + P2-010 组织树 CRUD）**：修复两项 P2 技术债，共 11 文件变更 + 1 新建测试文件未提交。**P2-008**：`entrypoint.sh` 支持 `WORKERS` 环境变量（>1 时 `uvicorn --workers`）；消费者组名改为 per-process（`ws-fanout-{hostname}-{pid}`），修正共享组竞争消费导致多 worker 只有一进程收到消息的缺陷；WS broadcaster 改为 lifespan eager 启动；`/health` 新增 `ws_connections` 与 `ws_broadcaster` 指标；docker-compose 增加 `WORKERS` 与 `backend_storage` 卷。**P2-010**：新增 `POST/PUT/DELETE /api/v1/organizations` CRUD 端点（权限码 `system:org:create/update/delete`）；`org_type` 校验为 building/floor/zone；删除保护子节点与关联设备/用户；`init_data.py` 补齐菜单与权限码 seed；10 条守护用例全部通过。**验证结果**：`pytest -q` 181 passed (+10) / 48 skipped。会话文件见 `.claude/sessions/2026-09-09-2302.md`。

- **2026-09-09 22:21 归档（P1 收尾：登录日志审计 + Alembic 基线 + 3.3 性能压测）**：完成剩余全部 P1 项与相关 P2 项，共 20 个文件变更未提交。**P1-003** 新增 `GET /api/v1/login-logs`（分页 + 用户名/状态/时间范围筛选，权限码 `system:log:view`）、前端 `views/system/LoginLog.vue` 审计页、6 条后端守护用例；**P1-006** 生成 Alembic baseline 迁移 `54d02fd0cebb`，覆盖 11 张表及 JSONB/索引，本地 PostgreSQL 已 `stamp head`；**P1-007** 在设备详情/更新/退役/删除/历史/轨迹/导出接口叠加数据权限范围，越权返回 404，新增 6 条守护用例并移除 e2e 的 `xfail`；**P1-008** 新增 `backend/scripts/benchmark_3_3.py`，地图视口 1000/5000 点位 P95=121ms/268ms，WS 100 条/s 推送 P95=981ms/P99=1026ms，均通过验收线。**验证结果**：`pytest -q` 171 passed / 48 skipped，`npm run build` 成功。P2-004（`.claude/decisions.md` 与 `sessions/index.md` 纳入版本控制）与 P2-009（3.3 结论回写 PRD/ADR）同步收口。本次同时清理了用户级记忆索引中一条已废弃条目。会话文件见 `.claude/sessions/2026-09-09-2221.md`。

- **2026-09-09 05:45 归档（3.3 实时监控与电子地图：计划 → 实现 → 验证）**：先按 PRD v2.0 §3.3 产出 `docs/plan/3.3-实时监控与电子地图-开发计划.md`（一致性复查：A 类 18 / B 类 7 / C 类 8 / OQ 7，OQ 全部按建议默认落地），再实现 B-12~B-19 与 F-12~F-18。**验证结果全为实测，原始日志存 `docs/test/raw/*-3.3.*`：`pytest` 159 passed + 48 skipped（3.3 新增 39 条，8 个文件）、`vitest` 19 files / 106 passed（新增 18 条）、`npm run build` 退出码 0、`E2E_BASE_URL=... pytest tests/e2e` 47 passed + 1 xfailed（新增 `test_monitor_e2e.py` 16 条，两轮 19.78s / 17.30s 结果一致）**。里程碑 M1 帧延迟实测 `n=10 p50=0.081s p95=0.111s max=0.111s`（预算 P95 ≤ 2s、红线 3s）；会话清理后 `dashboard` 全 0、未收敛报警 0、`storage/map-images/` 空。**两个真实缺陷**：① e2e teardown 顺序错误使上报型报警永不收敛（必须「上报 normal → 复位 → 删设备」）；② `frontend/nginx.conf` 缺 `/static/` 反代且 `/ws` 未设长连接超时 → 底图与实时推送在浏览器侧**静默失效**（返回 `200 text/html`）。计划 §八 的镜像依赖告警再次复现（新增 `pillow` 未 build → `ModuleNotFoundError` 崩溃循环）。**新增端点**：`/monitor/{report,ws-ticket,dashboard,alarms/recent,map,map/devices}`、`/alarms*`（列表/详情/confirm/silence/reset）、`/organizations/{id}/map-image`（+DELETE）、`/devices/{id}/trajectory[/export]`、`/ws/devices`；`alarms` 表 + 4 权限码由 `create_all` 与 `scripts/sql/3_3_alter.sql` 双路径落地（旧库必须手工执行该 SQL，P1-006 未收口）。交付后回填计划第十五节「实现偏离」27 项、新建 `docs/test/3.3-...测试执行结果.md`（逐条结果 + 缺陷根因与守护用例映射 + 验收边界）、`testing-guidelines.md` 断言陷阱 9 → 14 条并补 E2E/前端约定。**2026-09-09 后续提交**：本次交付内容已随 `41e0b1c 3.3功能` 进入版本库；`.claude/` 仍被 `.gitignore` 排除，会话归档与 ADR 未随该提交入库（后由 P2-004 处理）。

> 更早摘要（2026-09-09 02:47 及之前）已移至 `.claude/sessions/index.md`。

  ---
  四、滚动待办池（CLAUDE.md 中维护，跨会话累积）

  ▎ 不是每次新建，而是滚动更新已有条目。已完成的条目保留 1 次归档后移除。

  ### 🎯 滚动待办池

> 3.1 的 10 条已完成项与 3.2 的 9 条已完成项（P0-009~P0-015、P1-004~P1-005）均已移出本池，归档见 `.claude/sessions/index.md`。
> 3.2 消防设备档案已于 2026-09-09 02:18 交付（`pytest` 119 / `vitest` 88 / build OK / 容器端到端通过），容器级 E2E 已于 02:47 固化为可重跑模块 `backend/tests/e2e/test_device_api_e2e.py`（`-m e2e`，31 passed + 1 xfailed）。
> **3.3 实时监控与电子地图已于 2026-09-09 05:45 交付**（`pytest` 159 / `vitest` 106 / build OK / e2e 47+1 xfailed / M1 帧延迟 P95 0.111s），E2E 固化在 `tests/e2e/test_monitor_e2e.py`（16 条）。
> **P1 级全部收尾项已于 2026-09-09 22:21 完成并移出本池**（P1-003 登录日志审计、P1-006 Alembic baseline、P1-007 单资源数据权限、P1-008 3.3 压测），连同 P2-001/P2-004/P2-009 一并归档于 `.claude/sessions/index.md`。池内剩余为 P0 联调收尾与 P2 级技术债。

| ID | 事项 | 优先级 | 状态 | 引入会话 | 备注 |
|----|------|--------|------|----------|------|
| P0-016 | 前后端联调：设备档案全流程验收（收尾） | P0 | [x] | 2026-09-09 | **已完成**。主管账号「新增→编辑→导入→退役→历史」全流程与三类角色 401/403 抽样已在真实 PostgreSQL 容器验证通过；主管/值班员/维保 × 10 端点权限矩阵与 `all`/`dept`/`self` 可见量差异已固化为 `pytest -m e2e` 自动化用例（02:47）。「1000+ 设备分页流畅」性能验证已通过：新增 `backend/scripts/benchmark_device_pagination.py`，1200 设备下第 1/10/50 页 P50≈13ms、P95≈18ms；5000 设备下 P50≈15ms、P95≈21ms，全部远低于 100ms，分页流畅达标 |
| P2-002 | 清理 pytest warning | P2 | [x] | 2026-09-09 | **已完成**（commit `64c7916`）。159 条 warning 全部清除：9 处 Pydantic `class Config` → `model_config = ConfigDict`（6 个 schema 文件）、`TestDevice`/`TestItem` 重命名避免 pytest 误采集、`AsyncClient(app=...)` → `ASGITransport`、`per-request cookies` → `client.cookies.set()` |
| P2-003 | PRD 3.3+ 后续模块排期 | P2 | [x] | 2026-09-09 | **已完成**。已按 3.3 计划模板补齐 PRD 第 3.4 ~ 3.10 章前后端开发计划：`docs/plan/3.4-报警联动-开发计划.md`、`3.5-火警确认与应急处置-开发计划.md`、`3.6-设备巡检-开发计划.md`、`3.7-故障维修-开发计划.md`、`3.8-消防演练-开发计划.md`、`3.9-统计报表-开发计划.md`、`3.10-系统配置与运维-开发计划.md`。每份计划均含需求范围、现状基线、总体设计、数据库设计、API 清单、前后端任务分解、依赖与里程碑、测试策略、风险与 PRD 一致性检查（A/B/C）、需产品确认事项及实现偏离节。 |
| P2-005 | 部署前替换 JWT `SECRET_KEY` | P2 | [x] | 2026-09-09 | **已完成（文档澄清）**。`backend/.env.example` 已追加醒目注释，说明占位 `SECRET_KEY`/`DEVICE_REPORT_KEY` 在公网/演示/生产环境必须替换，并给出 `openssl rand -hex 32` 生成方式及禁止提交 `.env` 的提醒。运行时强校验留待后续若部署风险再补 |
| P2-006 | 软删除设备占用编码的提示语误导 | P2 | [x] | 2026-09-09 | **已完成**。`device_service` 唯一性校验改为返回冲突记录 `(id, is_deleted)`；新建/更新/导入遇到 `is_deleted=True` 时返回「设备编码已被已删除档案占用: XXX」并附带 `POST /api/v1/devices/{id}/restore` 恢复入口。新增 `restore_device` 服务与 `/devices/{id}/restore` 端点，恢复前校验编码不与未删除档案冲突。单元测试覆盖新建撞已删、导入撞已删、正常恢复三类场景，`pytest` 全绿 |
| P2-007 | 镜像依赖与 `requirements.txt` 漂移无校验 | P2 | [x] | 2026-09-09 | **已完成**（commit `9bf98ed`）。`entrypoint.sh` 在启动 uvicorn 前校验 18 个关键运行时依赖的可导入性；缺失时提前退出并提示「执行 `docker compose build backend` 后重试」，避免 `ModuleNotFoundError` 导致的崩溃循环 |

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
