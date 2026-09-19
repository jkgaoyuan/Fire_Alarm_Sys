# 跨会话关键决策索引（ADR）

> 按协议第三节第 6 条，各会话文件中的「关键决策」需同步至本文件。
> 每条记录：决策内容 / 原因 / 影响范围 / 回滚条件（如有）。
> 编号在会话文件中首次分配；DEC-004 为 2026-09-09 审计时从 `2026-09-07-2250.md` 未编号决策追溯补号。

---

## DEC-001：Refresh Token 完全由后端 httpOnly Cookie 承载

- **决策**: 前端不存储、不读取 Refresh Token，仅由后端 `Set-Cookie: httpOnly; Secure; SameSite=Strict` 下发。
- **原因**: 防止 XSS 窃取 Refresh Token；Access Token 短时效（60 min）+ Refresh Token 长时效（7 d）分离暴露面。
- **影响范围**: `backend/app/api/v1/auth.py`、`frontend/src/utils/request.js`、`frontend/src/utils/auth.js`
- **来源会话**: 2026-09-07 22:50（提出）、2026-09-08 20:36（实现，编号 DEC-001）
- **回滚条件**: 无。若未来需支持非浏览器客户端（移动端 / 第三方集成），需另设 Token 通道，不改动本决策。

## DEC-002：Token 刷新采用「主动检查 + 401 兜底」双保险

- **决策**: 请求拦截器主动检查 `exp - now < 300s` 先刷新再发原请求；401 响应仅作兜底触发刷新。
- **原因**: 纯被动刷新会导致每个会话的首个请求出现 401 闪错，用户体验差且易被误判为鉴权失败。
- **影响范围**: `frontend/src/utils/request.js`（含并发刷新锁，避免多请求同时触发刷新）
- **来源会话**: 2026-09-08 20:36
- **回滚条件**: 无。

## DEC-003：v-permission 默认行为为 CSS 隐藏

- **决策**: `v-permission` 无权限时默认 `display: none`，可选 `remove` / `disabled` 修饰符改变行为；支持字符串与数组两种入参。
- **原因**: 直接移除 DOM 会导致布局跳动，隐藏可保持视觉稳定；`disabled` 用于需要提示「无权限」而非「不存在」的场景。
- **影响范围**: `frontend/src/directives/permission.js`、`frontend/src/components/PermissionButton.vue`
- **来源会话**: 2026-09-08 20:36
- **回滚条件**: 若安全审计要求无权限元素不得存在于 DOM（防前端探测），改为默认 `remove`。

## DEC-004：所有业务表统一追加 `created_by` 外键

- **决策**: 业务表统一增加 `created_by BIGINT REFERENCES users(id)`，作为数据权限 `self` 范围的过滤依据；`dept` 范围依据 `org_id`。
- **原因**: 数据权限（`all` / `dept` / `self`）需要在 SQL 层过滤，而非应用层裁剪；统一字段可让 `get_data_scope_filter` 复用于所有业务表，避免逐表定制。
- **影响范围**: `backend/app/models/base.py` 及后续所有业务模型、`backend/app/core/dependencies.py`（`data_scope_filter`）
- **来源会话**: 2026-09-07 22:50（原为未编号决策，2026-09-09 追溯补号 DEC-004）
- **回滚条件**: 无。**3.2 设备档案及后续所有业务表必须遵循本约定**，否则数据权限失效。

## DEC-005：生产构建组件加载使用显式映射表而非 `import.meta.glob`

- **决策**: 动态菜单的组件解析改为显式 `viewComponents` 映射表，替代 `import.meta.glob('@/views/**/*.vue')`。
- **原因**: Vite 生产构建后 `import.meta.glob` 的 key 与开发环境 `@/views/...` 不完全一致，动态菜单生成时 `modules[`@/${component}`]` 为 `undefined`，触发 `TypeError: t[l.component] is not a function`，表现为登录后跳转白屏。
- **影响范围**: `frontend/src/utils/menu.js`
- **来源会话**: 2026-09-09 00:39
- **回滚条件**: 未来 Vite 版本稳定支持生产环境一致的 glob key，或改用基于路由名称的映射机制。
- **连带约束**: 新增业务页面时必须同步在 `viewComponents` 中登记，否则菜单可点击但页面空白。

## DEC-006：3.2 数据表沿用 `Base.metadata.create_all`，暂不引入 Alembic 迁移

- **决策**: `device_types` / `devices` / `device_status_logs` 三张新表不写 Alembic 版本文件，依赖应用启动时的 `create_all` 建表；`alembic/versions/` 保持为空。
- **原因**: 3.1 全量开发即未产出任何迁移版本（`versions/` 空目录），项目实际约定是 `create_all` + 开发期容器重建。单独为 3.2 补一条迁移会造成「迁移链没有基线、首条迁移无处 downgrade」的悬空状态。计划文档 B-8 要求的「Alembic 迁移」按此偏离。
- **影响范围**: `backend/app/models/base.py`、`backend/app/models/device.py`、`backend/app/models/device_type.py`；`backend/app/core/database.py`（建表入口）
- **来源会话**: 2026-09-09 02:18
- **回滚条件**: **正式发版前必须补一次 Alembic 基线**（`alembic revision --autogenerate` 覆盖现有全部表并 `stamp` 已有库），否则生产环境无可控升级路径。已登记为待办。
- **执行记录**: 2026-09-09 已生成基线迁移 `backend/alembic/versions/2026_09_09_2141-54d02fd0cebb_baseline.py`（revision `54d02fd0cebb`），覆盖截至 3.3 的全部表与索引；本地 PostgreSQL 开发库已 `alembic stamp head`。本决策的「暂不引入」状态结束，后续模型变更改为常规 Migration 链扩展。

## DEC-007：预置数据脚本必须幂等

- **决策**: `backend/scripts/init_data.py` 全部步骤改为按唯一键 get-or-create（角色/菜单/按钮权限/权限绑定/设备类型/用户），已存在则跳过，仅补缺失项；用户已存在时不重置密码。
- **原因**: `scripts/entrypoint.sh` 在容器每次启动时都会执行该脚本，而原实现假定空库、直接 `add` + `commit`，第二次启动即抛 `duplicate key value violates unique constraint "roles_role_code_key"` 并导致后端容器崩溃循环。
- **影响范围**: `backend/scripts/init_data.py`、`backend/scripts/entrypoint.sh`；**3.3+ 模块新增 Seed 数据时必须沿用 get-or-create，禁止直插**
- **来源会话**: 2026-09-09 02:18
- **回滚条件**: 若改为「仅首次启动初始化」（引入哨兵表或环境变量），可放宽幂等要求，但需保证容器重建后仍可执行。

## DEC-008：前端测试环境 inline element-plus，浮层用内联 overlayStub

- **决策**: `vite.config.js` 的 `test.server.deps.inline` 加入 `element-plus`；组件测试不使用 `global.stubs.teleport`，改用 `__tests__/mount.js` 中的 `overlayStub()` 把 `ElDrawer` / `ElDialog` 替换为内联渲染并补发 `open` 事件的占位组件。
- **原因**: 两个都是阻塞级坑。(1) Node 直接加载 element-plus 的 ESM 产物时，async-validator 的 CJS 默认导出被解析成命名空间对象，`new AsyncValidator()` 抛错被吞，**所有 `el-form` 校验静默返回「通过」**，必填与异步唯一性校验的测试全部假阳性通过；交给 Vite 转译才有 interop。(2) `stubs: { teleport: true }` 会让 ElSelect 的下拉 popper 进入 `Maximum recursive updates exceeded` 无限递归（单文件最多 66 次未处理拒绝）。
- **影响范围**: `frontend/vite.config.js`、`frontend/src/views/device/__tests__/mount.js`；后续所有含表单/抽屉/对话框的组件测试
- **来源会话**: 2026-09-09 02:18
- **回滚条件**: element-plus 或 vitest 升级后若 ESM 互操作恢复正常，可移除 inline 配置；`overlayStub` 在引入 `@vue/test-utils` 的 teleport 友好方案后可替换。
- **连带约束**: 断言按钮可见性须过滤 `display:none`（DEC-003 的 `v-permission` 只隐藏不移除 DOM）；`ElMessageBox` 渲染在组件树之外，须局部 mock；表单错误文案有 100ms 防抖，断言前用 `vi.waitFor`。

## DEC-009：实时推送采用 Redis Stream + 每进程独立消费者组扇出

- **决策**: 设备状态/报警实时推送使用 Redis Stream（`ws:devices:stream`）作为持久化队列；每个 uvicorn worker 启动时创建以自己标识命名的消费者组，读取后按用户 `org_id` 数据范围过滤并 WebSocket 推送。断线重连客户端通过 `XRANGE` 补发最近 500 条，超过上限则下发 `resync_required` 让前端主动刷新。
- **原因**: PRD 2.2 写 Redis Stream、9 风险表写 Redis Pub/Sub，两者混用；Stream + 消费者组既能做多实例广播（等价 Pub/Sub），又保留消息历史支持重连补发，避免单独维护两套机制。
- **影响范围**: `backend/app/services/ws_broadcaster.py`、`backend/app/api/v1/ws_devices.py`、`backend/app/core/lifespan.py`、`frontend/src/utils/websocket.js`
- **来源会话**: 2026-09-09 05:45（3.3 实时监控与电子地图交付）
- **回滚条件**: 若未来引入 Celery / 专用消息队列，可保留 Stream 作为 broker，仅替换消费侧。

## DEC-010：WebSocket 认证使用一次性 Ticket 而非直接 Bearer Token

- **决策**: 浏览器建立 WebSocket 前，先通过 HTTP `POST /api/v1/monitor/ws-ticket` 申请一次性 Ticket（Redis TTL 60 秒），连接时以 query `?ticket=...` 携带；服务端握手阶段 `GETDEL` 校验 Ticket 并解析出用户身份。
- **原因**: 浏览器 WebSocket 无法设置标准 `Authorization` 头；若把长期 Access Token 放进 URL query，会被 nginx/access_log 记录，存在泄露风险。Ticket 短命且一次性，泄露窗口极小。
- **影响范围**: `backend/app/api/v1/monitor.py`（`ws-ticket` 端点）、`backend/app/api/v1/ws_devices.py`（握手校验）、`frontend/src/utils/websocket.js`
- **来源会话**: 2026-09-09 05:45
- **回滚条件**: 若安全评审要求改用 `Sec-WebSocket-Protocol` 子协议携带 Token，可在握手阶段兼容实现，但需同步调整前端与服务端解析逻辑。

## DEC-011：报警/设备复位在无硬件回读时要求显式「已物理恢复」并审计留痕

- **决策**: 复位接口 `POST /api/v1/alarms/{id}/reset` 要求请求体显式携带 `physical_restored: bool`；无论真假都写入 `alarms.reset_physical_restored`、`reset_by`、`reset_at`。系统仅以最近一次 `normal` 上报 + `last_report_at` 新鲜度作为辅助判定，不强制阻塞复位。
- **原因**: FR-016.2 要求「仅当设备物理状态恢复正常后」才能复位，但 3.3 尚未接入 MQTT 硬件回读，无法自动判定；强制阻塞会导致功能不可用。显式勾选 + 审计字段为后续责任追溯提供数据基础。
- **影响范围**: `backend/app/services/alarm_service.py`（`reset_alarm`）、`backend/app/schemas/alarm.py`、`frontend/src/views/alarm/AlarmCenter.vue`
- **来源会话**: 2026-09-09 05:45
- **回滚条件**: MQTT 接入后，可在服务端增加「必须收到设备 `normal` 状态报文」的硬性前置，同时保留审计字段。

## DEC-012：报警数据权限按设备归属区域过滤，`self` 范围在报警场景降级为 `dept`

- **决策**: `alarms` 表冗余 `org_id`（写入时从 `devices.org_id` 快照），实时监控、报警列表、报警详情、WS 推送全部按 `alarm.org_id ∈ 用户可见 org_id 集合` 过滤；`data_scope='self'` 的用户在报警相关接口视为 `dept`。
- **原因**: 自动上报产生的报警 `created_by` 为 NULL，若继续按 `created_by` 过滤，`self` 用户将永远看不到任何报警，直接违反 FR-013/014。设备归属区域是报警最稳定的权限维度。
- **影响范围**: `backend/app/services/monitor_service.py`、`backend/app/services/alarm_service.py`、`backend/app/services/ws_broadcaster.py`
- **来源会话**: 2026-09-09 05:45
- **回滚条件**: 若产品确认 `self` 用户在报警中心应仅看自己手动创建的报警（不含自动上报），可恢复 `created_by` 过滤并单独处理自动上报可见性。

## DEC-013：3.6 巡检模块使用 FastAPI lifespan + asyncio 后台任务替代 Celery

- **决策**: 3.1~3.6 阶段暂不引入 Celery，所有定时任务（巡检任务生成、漏检扫描）均通过 FastAPI `lifespan` + `asyncio.create_task()` 实现。
- **原因**: 
  1. 系统规模较小（≤10,000 设备），单进程 asyncio 定时任务已满足需求
  2. 减少外部依赖（Celery + Redis broker），降低部署复杂度
  3. PRD v2.0 第 2.2 节已明确此技术路线
- **影响范围**:
  - `backend/app/main.py`: lifespan 事件中注册 `inspection_scheduler` 后台任务
  - `backend/services/inspection_scheduler.py`: 实现任务生成与漏检扫描逻辑
  - `backend/models/inspection_tasks`: 唯一约束 `(plan_id, task_date)` 防止多 worker 重复生成
- **来源会话**: 2026-09-10 审计 3.6 开发计划（DEC-013）
- **回滚条件**: 
  1. 3.9 统计报表阶段需跨多个服务协调异步任务时，可引入 Celery
  2. 监控发现重复任务生成且数据库约束不足兜底时，评估集成 `aioredis` 分布式锁
  3. 设备规模扩张至 >50,000 或并发任务数 >100 时重新评估

## DEC-014：维修工单流转的权限口径与检查顺序沿用 `/complete`，不叠加数据范围

- **决策**: `PUT /repair-orders/{id}/start` 采用「路由依赖 `require_permission("repair:repair")` + 端点内归属检查（`repairer_id == current_user.id`）」两道闸，**不叠加** `repair_scope_condition`；检查顺序为**先归属（403）后状态（400）**，与既有 `/complete` 完全一致。
- **原因**:
  1. `repair:repair` 是「维修填报」类操作，与 `/complete` 同属一类；口径不一致会导致同一动作在不同端点行为分裂
  2. 「这一单归不归你」比数据范围更精确——数据范围用于**读**（列表/详情），归属用于**写**
  3. 顺序不一致会造成「同一张工单在 start 与 complete 上得到不同的拒绝码」，前端无法统一处理
- **影响范围**: `backend/app/api/v1/repair.py`（`start_repair_order`）、`backend/app/crud/repair.py`（`start`）
- **来源会话**: 2026-09-13 21:00
- **已知后果**: `pending` 且未指派的工单对**所有人**返回 403（归属检查先拦），而非 400。这是刻意保留的：未指派即无归属，不存在「负责人可越权跳步」的路径。状态机的第二道闸（400）用于拦截「已指派却仍是 pending」的异常数据，已单独用例钉住（TC-RP-019）。
- **回滚条件**: 若产品要求维修人只能操作本部门工单（而非仅本人负责的），在端点叠加 `repair_scope_condition` 即可。

## DEC-015：前端操作列一律用 `v-permission` 判权限码，废弃 `role_code` 判断

- **决策**: 维修工单列表操作列的按钮可见性，全部由权限码驱动——派单 `repair:assign`、验收通过/退回 `repair:accept`、开始/完成/重新维修 `repair:repair`。`isChief`（`role_code === 'chief'`）判断整体删除。
- **原因**: 后端已于 `a66da2f7` 把 `role_code == "chief"` 换成 `repair:assign` / `repair:accept` 权限码，**前端未跟进**，形成两套口径。后果双向：主管被撤销 `repair:assign` 后前端仍显示按钮（点击才 403）；非 chief 角色被授予 `repair:assign` 后按钮反被前端藏起来——授予/撤销角色权限在前端毫无效果，与 `repair:*` 接线前的「空操作码」是同一类缺陷。
- **影响范围**: `frontend/src/views/repair/OrderList.vue`
- **来源会话**: 2026-09-13 21:00
- **未完成部分**: 其他页面是否仍有 `role_code` 判断未做排查（见该会话文件的「阻塞点与风险」）。
- **回滚条件**: 不需要回滚；若某按钮确实应按角色而非权限码控制，应改为新增对应权限码并授予角色，而不是在前端判角色码。

## DEC-016：候选人过滤走 `GET /users` 新增可选 `permission` 参数，不新建 repair 域端点

- **决策**: 为「派单候选人下拉框只列能真正接手的人」，在既有 `GET /users` 上新增可选 `permission` 查询参数（按角色折算的权限码过滤，与 `/users/me/permissions` 同口径）；条件同时作用于 `items` 与 `count`。
- **原因**:
  1. 「谁持有某权限码」是可复用能力，后续其他模块的候选人下拉框还会用到，不值得为每个域各建一个端点
  2. 省略该参数时行为完全不变，对既有调用方（用户管理页等）向后兼容
  3. 复用既有分页/搜索实现，避免在 repair 域重复一份用户列表查询
- **影响范围**: `backend/app/api/v1/users.py`、`backend/app/services/user_service.py`
- **来源会话**: 2026-09-13 21:00
- **已知残留耦合**: `GET /users` 需要 `system:user` 权限，因此派单能力间接依赖它。当前不构成缺口——只有 chief 持有 `repair:assign`，而 chief 在 `init_data.py` 中绑定全部权限码（含 `system:user`）。若将来把 `repair:assign` 授予一个没有 `system:user` 的角色，会出现「看得到派单按钮、点开候选人列表为空/403」。
- **回滚/演进条件**: 若上述耦合成为现实，改为在 repair 域新增由 `repair:assign` 守卫的候选人端点（如 `GET /repair-orders/repairers`），并把该参数从 `GET /users` 撤下。

## DEC-017：响应信封必须在端点内保持字面量，不得抽成辅助函数

- **决策**: 统一信封 `Response(code=..., message=..., data=...)` 必须字面量写在每个路由函数体内。可以抽 `data` 部分的构造（如本次的 `_order_out(order)`），但**不能**抽成 `return _envelope(db_obj)` 这样的整体辅助函数。
- **原因**: `backend/tests/test_api_envelope_contract.py` 是 **AST 静态扫描**，`_classify` 只认两类形态：字面量 `Response(code=...)` 调用，或含 `code` 键的手写 dict。调用辅助函数会被判为 `bare`（裸返回）而失败。该守卫刻意**不做**「已知返回信封的辅助函数」白名单——那等于给它开一个可以返回任何东西的后门，守卫就失去意义了。
- **影响范围**: `backend/app/api/v1/repair.py`（2026-09-13 重构时实测踩中：抽出 `_order_envelope()` 后 7 个端点全部被判 `bare`，守卫立刻变红）
- **来源会话**: 2026-09-13 21:00
- **回滚条件**: 不适用。若将来确实需要整体抽取，正确做法是增强守卫（例如让它能追踪辅助函数的返回语句），而不是加白名单。

## DEC-018：响应信封不一致时**一律改后端**，不改前端去适配

- **决策**: 遇到「后端裸返回、前端按信封读」的不一致，改正**后端**返回统一信封；前端随之写回 `if (res.code === 200 && res.data)`。
- **原因**:
  1. 偏离的源头在后端（违反了 `docs/plan/API_RESPONSE_FORMAT_SPECIFICATION.md`），改前端等于把偏离固化进调用方
  2. **改前端不会报错，只会静默显示错数据**：`frontend/src/utils/request.js` 的响应拦截器对两种形状都放行（`if (data && typeof data.code === 'number') return data` 之后还有 `return data`），组件读 `res.data.items` 得到 `undefined`，再被 `|| {}` 兜底 → **页面显示 0 而不是报错**。维修统计页四项指标恒为 0 就是这么漏了几个月
  3. 历史教训：3.4/3.6/3.7 三个模块当初都选择了改前端，于是偏离扩散成 20 个端点（`repair.py` 11 + `linkage_plans.py` 7 + `linkage_logs.py` 2）
- **影响范围**: `backend/app/api/v1/{repair,linkage_plans,linkage_logs}.py`（2026-09-13 已全部迁完，119 个端点口径归零）、`frontend/src/views/{repair,linkage}/`
- **配套**: 新增 `backend/tests/test_api_envelope_contract.py` 静态守卫（AST 扫全部路由，返回裸数据即失败）。这条约定此前**只靠人记**
- **来源会话**: 2026-09-13 21:15
- **回滚条件**: 无。若某端点确需返回非 JSON 载荷（文件下载、流式），用 `FileResponse`/`StreamingResponse`/`PlainTextResponse` 等，守卫天然豁免；204 亦然

## DEC-019：新增业务时区配置，**只作用于调度器**，不改容器 TZ

- **决策**: 新增 `APP_TIMEZONE`（默认 `Asia/Shanghai`）与 `app/core/timezone.py` 的 `now_in_app_tz()` / `today_in_app_tz()`；巡检调度器按业务时区算「现在几点 / 今天几号」，并把算好的 `target_date` **显式传给 service**。
- **原因**:
  1. 后端容器跑在 UTC（实测容器 `date` = `Sun Sep 13 12:12 UTC`，而业务口径已是 `20:12+08:00`）。按容器本地时间算 00:05，实际触发在北京 08:05
  2. 更隐蔽的是**日期**：`generate_tasks_for_plan` 内部的 `date.today()` 返回 UTC 的「昨天」，会生成错日期的任务
  3. **不改容器 TZ**：仓库内所有时间戳都是 naive 存储，整体改 TZ 会让存量数据语义偏移 8 小时
- **关键设计**: 时区只出现在调度器这一层。service 层不自己问「今天几号」，避免同一个问题在多处重复回答
- **影响范围**: `backend/app/core/timezone.py`（新建）、`backend/app/core/config.py`、`backend/app/services/inspection_scheduler.py`
- **来源会话**: 2026-09-13 21:15
- **回滚条件**: 无。后续 `app/core/security.py:97` 硬编码的 `timedelta(hours=8)` 可收敛到本模块，属独立工作，本次未做

## DEC-020：`InspectionTask` 补 `(plan_id, task_date)` 唯一约束

- **决策**: 给 `InspectionTask` 加 `UniqueConstraint("plan_id", "task_date", name="uq_inspection_tasks_plan_date")` + alembic 迁移；同时让 `generate_tasks_for_plan` 捕获 `IntegrityError` 并**仅识别唯一违例**（FK 违例仍上抛）。
- **原因**:
  1. 模型注释与 3.6 计划第 358 行都以「unique (plan_id, task_date)」作为多 worker 去重的兜底前提，但**该约束实际并不存在**（模型无 `__table_args__`，迁移里只有外键）
  2. 去重完全依赖 `generate_tasks_for_plan()` 的 check-then-act，`WORKERS>1` 下必然双写；而 `WORKERS` 在 docker-compose 里可配
- **为何仍要 service 侧捕获**: `main.py:_ensure_database_schema()` 在「存量脏库」分支会 `stamp head` 跳过迁移，且 `create_all` 不会给已有表补约束——**那条路径下约束不生效**，不能依赖它存在
- **影响范围**: `backend/app/models/inspection.py`、`backend/alembic/versions/2026_09_13_1800-add_inspection_task_unique.py`（新建）、`backend/app/services/inspection_service.py`
- **来源会话**: 2026-09-13 21:15
- **回滚条件**: 若需允许同计划同日多任务（如一天多轮巡检），删除该约束与 `_is_duplicate_task_error` 判断

## DEC-021：设备域的 `data_scope='self'` 降级为 `dept`

- **决策**: 新增 `device_service.apply_device_data_scope`，`self` 按 `dept` 处理（本部门及全部子部门）。设备的列表、详情、历史、轨迹、回收站恢复全部改走该函数，**不再复用 `user_service.apply_data_scope`**（后者如今在**生产代码中**已无调用方，`app/` 零调用；docstring 已改写为警示）。
- **原因**:
  1. 通用函数把 `self` 锚在 `devices.created_by` —— 设备的**录入人**。设备是**组织的资产**，不是录入人的私产；「谁录的档案」与「谁该看/该修/该管这台设备」无关。
  2. 实测后果（2026-09-14）：维保员 `data_scope='self'`、设备由管理员录入 → 设备档案页 **0 台**、详情/历史/轨迹一律 404（envelope `code=404`，HTTP 200）。而设备维保正是该角色的本职工作 —— 模块对其主要使用者不可用。
  3. 这与既有两条口径同源：**DEC-012**（alarms 的 `self` 降级为 `dept`，「自动上报的报警没有 created_by」）、`apply_task_data_scope`（任务锚 `responsible_user_id`）、`repair_service.repair_scope_condition`（工单锚报修/维修/验收/创建四字段）。**每个域自己决定 `self` 锚在哪，锚不住就降级 dept**；设备域是最后一个还在套通用函数的。
- **被否的备选**: 改维保员的 `data_scope` 为 `dept`（对上 `3.6-设备巡检 - 权限测试用例补充.md` TC-PERM-004 的「maintainer=dept」）。否决理由：`data_scope` 是**用户级**属性，改它会连带把该用户的**任务**可见性从「责任人是我的」变成「本部门任务」（与 `3.6-设备巡检-开发计划.md`「后端技术要点」第 5 条冲突），**维修工单**从「我报的/我修的/我验收的/我建的」变成「本部门设备的全部工单」（实测 6 条 → 8 条，多出两条与该用户无关）。范围口径应就地修在域内，而不是外溢到别的域。
- **影响范围**: `backend/app/services/device_service.py`、`device_history_service.py`、`organization_service.py`（`resolve_descendant_org_ids` 由 `monitor_service` 迁入）、`user_service.py`（docstring 警示）、`tests/test_device_permission.py`、`tests/test_device_scope.py`、`docs/plan/3.2-消防设备档案-开发计划.md`（技术要点第 1 条）
- **来源会话**: 2026-09-14
- **回滚条件**: 若将来给设备加上「归属人」字段（如 `responsible_user_id`），可把 `self` 锚到该字段，与任务域口径对齐；届时本降级即可撤销

## DEC-022：用户信息统一在会话初始化时恢复，且必须在生成路由**之前**

- **决策**: `authStore.userInfo` 的唯一有效填充点是路由守卫的 `initializeRoutes()`。其 `initPromise` 内改为**顺序**执行 `await useAuthStore().fetchUserInfo()` → `await permStore.generateRoutes()`；前面那步**不可后置、不可省略**。
- **原因**:
  1. `authStore.userInfo` 是**纯内存**状态，而 `accessToken` 会从 localStorage 恢复（`stores/auth.js:9`）。刷新后 token 恢复使路由守卫放行导航，但 `userInfo` 重新初始化为 `ref(null)`，而它的填充函数 `fetchUserInfo()`（`stores/auth.js:29`）**在全仓库应用代码里没有任何调用方**——此前只有它自己的单元测试在调（`stores/__tests__/auth.spec.js:61`）。后果是 `AppHeader.vue:9` 的三段兜底 `userInfo?.real_name || userInfo?.username || '用户'` 落到最后一档，顶部栏恒定显示字面量「用户」。
  2. 登录瞬间正常，是因为 `login()` 用登录响应的 `data.user` 填了一次（`stores/auth.js:22`）——**两条路径只有一条有填充**，这正是该缺陷能长期存在的原因。
  3. **顺序必须在 `generateRoutes()` 之前**：`isRoutesLoaded` 是在 `generateRoutes()` 末尾才置位的。若把用户信息放在其后且它失败，就会停在一个半初始化态——守卫见 `isRoutesLoaded === true` 直接跳过 `initializeRoutes()`，重试路径被跳过，`userInfo` 永远为 null，等于把缺陷埋得更深。
- **不吞异常**: 该步失败即抛，让初始化整体重试。吞掉它正是仓库教训 1 记录的形态（「对两种形状都放行 → 页面显示 0 而不报错」），会把故障从「报错」退化为「静默显示兜底文案」。
- **影响范围**: `frontend/src/router/index.js`、`frontend/src/stores/auth.js`（`fetchUserInfo` 自此是 `userInfo` 的唯一有效写入方）、`frontend/src/router/__tests__/index.spec.js`（+3 条用例）
- **来源会话**: 2026-09-14 23:11（commit `210b6b7b`）
- **回滚条件**: 若改为把 `userInfo` 持久化到 localStorage 以省下一次请求，需重新评估——但那会引入**陈旧数据**问题（改名/改角色后不刷新即不生效），且必须同时保证登出清除。当前选择的代价是每次冷启动多一次 `GET /users/me`。
- **连带约束**: 新增任何依赖 `userInfo` 字段的代码前，先确认该字段在 `GET /users/me` 的响应里存在——**不要**指望登录响应提供它（见 DEC-023）。

## DEC-023：登录响应不再返回 `roles`，用户身份字段统一从 `GET /users/me` 取

- **决策**: `POST /auth/login` 响应中的 `data.user` 只保留 `id` / `username` / `real_name`，**移除 `roles`**。用户角色一律从 `GET /users/me` 获取。
- **原因**:
  1. 同一份 `authStore.userInfo` 有**两个写入方、两种形状**：登录响应返回 `["chief"]`（`role_code` 字符串数组，`auth_service.py`），而 `/users/me` 返回 `[{id, role_code, role_name}]`（对象数组，`users.py:63-66`）。两者都写进同一个 ref。
  2. 该字段**两端都没有消费者**：前端 `userInfo` 的唯一读取点是 `AppHeader.vue:9`，只取 `real_name`/`username`；全前端唯一的 `roles` 消费点 `OrderList.vue:201` 遍历的是 `repairerOptions`（来自 `GET /users`），与 `userInfo` 无关；后端 `tests/test_auth.py` 只断言 `access_token`/`username`/`real_name`，`tests/e2e/common.py:65` 只取 `access_token`；`tokens["user"]` 全仓库只有 `auth.py:74` 一处透传。
  3. 保留 `id`/`username`/`real_name` 的理由：这三者**不是**死字段——`AppHeader.vue:9` 读 `real_name || username`，而 `stores/auth.js:22` 正是把登录响应的 `user` 写进 `userInfo`。删掉它们会让登录瞬间没有名字可显示。
  4. 真正的暴露面不在 `roles` 自身（它没人读），而在**未来**：往 `userInfo` 上读一个登录响应里不存在的新字段（`data_scope` / `org` / `phone` / `email`）时，会出现**取决于走哪条路径**的 `undefined`——那类比固定崩溃难查。见 DEC-022 的连带约束。
- **影响范围**: `backend/app/services/auth_service.py`、`frontend/src/stores/auth.js`（写入方形状随即归一）、`backend/tests/test_auth.py`（新增钉死用例）
- **来源会话**: 2026-09-14 23:11（commit `6d84d03b`）
- **回滚条件**: 若未来确需「登录即拿到角色」以避免额外请求，正确做法是让 `GET /users/me` 成为唯一来源并在登录后调它，**而不是恢复第二种形状**——`test_login_response_does_not_publish_roles` 会立即打红。（该用例刻意让用户**确实持有角色**并先断言 `len(user.roles) == 1`，否则「已删掉」与「环境本来就没角色」无法区分。）

---

## DEC-024：演练告警**不上**大屏统计卡片 —— 这是 FR-045 隔离，不是缺陷

- **决策**: 大屏「报警设备」卡片（`d.alarm`，来自 `devices.status`）**不**为演练告警做任何改动。用户最初提出的「模拟火警为什么不上这张卡片」诉求，经查证后**由用户明确放弃**（`[-]`）。
- **原因**:
  1. 该卡片读 `devices.status`（`monitor_service.py:104-114` 按 **devices 表**聚合），而该字段全仓库**唯一写入方是上报入库** `device_report_service.py:97`。模拟端点走 `raise_alarm`（`alarm_service.py:134-171`），**只 INSERT `alarms` 行、从不碰 `device.status`** → 两层数据源不同，卡片必然为 0。
  2. 另有**三处 `is_drill` 过滤**（`AlarmList.vue:75`、`stores/monitor.js:76`、`monitor_service.py:122`）全部源于 **FR-045（P0 演练数据隔离）**，且是**首版即写入**的（`docs/plan/3.3:36/171`「`alarms.is_drill` 首版即写入并默认过滤」）。**是设计，不是漏了。**
  3. 真实火警走**上报通道**时该卡片会正常联动——已实测：`POST /monitor/report` 造 `alarm_id=6` → 设备 `normal→alarm` → 卡片 **0→1**。**同一条告警，走哪条路决定了它上不上那张卡片。**
- **影响范围**: 无代码改动。结论已写入会话文件与 CLAUDE.md 摘要
- **来源会话**: 2026-09-19 12:59
- **重估条件**: 若产品口径变更为「大屏需展示演练数据」，正确做法是**加显式的「含演练」开关**（与报警中心 `Center.vue:63` 一致），而**不是**让模拟端点去翻转 `devices.status`——后者无法按演练过滤（`devices` 表**没有** `is_drill` 维度），会让演练永久污染真实设备状态

## DEC-025：模拟端点补广播，但大屏两处派生量一律排除演练

- **决策**: `POST /linkage-plans/{id}/simulate` 补 `publish(redis, "alarm_new", ...)`（仅在**新建**告警时）；同时 `pendingFireCount`（大屏 tab 徽标）与 `activeAlarmDeviceIds`（地图点位着色）**排除演练**。
- **原因**:
  1. `linkage_plans.py` 全文 `publish`/`redis` **零命中**，而另外两条产生告警的路径都广播（`device_report_service.py:144`、`linkage_engine_service.py:198/219`）——一条路径少做两件事，默认应理解为**漏了**。
  2. 频道**本就该传演练帧**：`alarm_payload` 带 `is_drill`（`alarm_service.py:99`），该字段存在的唯一理由就是让消费端能过滤；`Center.vue:363-372` 把 WS 帧与 REST 结果合并、再统一过 `matchesFilters` 的 `include_drill` 判断（:402）——「演练帧流进来、由开关决定显隐」是**已在使用**的路径。
  3. **必须先堵两个洞再补广播**：大屏报警列表无条件滤掉演练（`AlarmList.vue:75`），故徽标与地图着色若还算进去，会出现「**徽标 1、列表空**」「地图红、列表空」——比什么都不显示更难解释。
  4. 另修 `_active_alarm_map`（`monitor_service.py:310`）——它**也没有** `is_drill` 过滤，即地图其实**早已**把演练算红（只是走 REST 而非 WS）。不是新引入的，但必须与前端一次修齐，否则地图自身矛盾。
- **影响范围**: `backend/app/api/v1/linkage_plans.py`、`backend/app/services/monitor_service.py`、`frontend/src/stores/monitor.js`。`AlarmList.vue` 与 `Center.vue` **一行未动**（前者本就在过滤，后者本来就正确）
- **来源会话**: 2026-09-19 12:59（commit `cd8ea68a`）
- **回滚条件**: 若演练帧误鸣笛，说明 `is_drill` 判断被绕过——前端 `stores/monitor.js:207/211` 的 `!payload.is_drill` 是唯一的拦阻点

## DEC-026：应急事件页的「执行」入口用 `ElMessageBox`，不新写弹窗组件

- **决策**: `Event.vue` 的「处置完成」用 `ElMessageBox.prompt`、「关闭事件」用 `ElMessageBox.confirm`，**不新写 dialog 组件**。
- **原因**:
  1. 这是仓库既有模式（`Archive.vue:408` 的删除/恢复二次确认、`Plan.spec.js:261` 的测试桩法），照抄即可。
  2. **避开 2026-09-14 那个弹窗家族陷阱**：本仓曾同时三处（`RecordViewer` / `StatsDialog` / `PlanDetail`）出现「声明了 `modelValue` 却把浮层的 `v-model` 绑在各自局部 `ref(false)` 上」→ 弹窗永远打不开且不报错。`ElMessageBox` 由 Element Plus 自行管理可见性，**没有 `modelValue` 契约可写坏**。
  3. `visibleDialogStub()` 那套纪律（testing-guidelines 第 31 条）只为自研弹窗组件准备；走 `ElMessageBox` 时用 `vi.mock('element-plus')` 替换 `prompt`/`confirm` 即可（同 `Archive.spec.js:23-33`）。
- **影响范围**: `frontend/src/views/emergency/Event.vue`、`frontend/src/api/emergency.js`
- **来源会话**: 2026-09-19 12:59（commit `ec901531`）

## DEC-027：超时升级链路**决定暂不做**（`[-]`）

- **决策**: FR「待确认报警超 5 分钟升级通知主管」的链路修复**暂缓**，由用户于 2026-09-19 明确决定。**这是决定，不是遗漏。**
- **原因**:
  1. 链路当前**完全不通**，且两个成因**互相独立**：① `emergency_service.py:177` 访问 `alarm.emergency_event` 触发懒加载，async 下 `MissingGreenlet` 崩溃；② 扫描只取 `Alarm.status == "pending"` 的报警，而应急事件只在**确认时**（pending → confirmed）创建——**二者互斥，闸门恒空**。
  2. 成因② 由本会话**独立查出**，peer 会话亦独立得出同一结论（两条都落入 `tests/test_escalation_scan.py` 的 `xfail(strict=True)`）。
  3. 当前**无任何角色依赖它**：主管收不到升级通知也不会有人察觉，故暂缓的实际风险为零。
- **影响范围**: 无代码改动。待办池 **P1-015** 状态 `[-]`；`test_escalation_scan.py` 的 2 条 `xfail(strict=True)`
- **来源会话**: 2026-09-19 12:59
- **重估条件**: 出现真实依赖「超时升级」的场景时再评估。⚠️ **`strict=True` 是探针**——哪天这两条转绿，测试会**反过来报错**，提醒摘掉 xfail；届时也说明成因已被别人修掉，需重新核对本决策

## DEC-028：角色权限「父子完整性」守卫写成**严格规则、零豁免名单**

- **决策**: 新增 `tests/test_role_permission_hierarchy.py`，规则为「凡角色持有的权限码，其 `parent_code` 指向的码，该角色也必须持有」——**严格，不设豁免名单**。
- **原因**:
  1. 能写成严格规则是因为**实测它本来就成立**：修掉两处漏授（`emergency:event` / `linkage:plan`）后，三个角色 77 个权限码**零违规**。
  2. **没有豁免名单就不会烂成垃圾桶**——对照 `test_permission_coverage.py` 的 `UNENFORCED_ALLOWLIST`，那份豁免里 3 个孤儿码长期挂着（见 P2-014）。豁免一旦存在，新违规会被顺手加进去而不是被修。
  3. 该守卫覆盖 **P2-012** 的一半（主管全量授权无守卫）：第三条用例钉住「`ROLE_PERM_MAP["chief"]` 为空 **且** `bind_permissions(chief_role, list(perm_map.values()))` 语句在位」两件事——只钉前者可以在别处改硬编码，只钉后者可以同时在清单里堆一长串。
  4. **刻意没写**「菜单码必须至少被某角色持有」：chief 走全量绑定，每个已定义码必然被持有，那种断言**构造上恒真**。（第一版写了它，跑出来假报 7 个菜单码"无人持有"——因为 `ROLE_PERM_MAP["chief"]` 是空列表、全量授权发生在绑定阶段。已删。）
- **影响范围**: `backend/tests/test_role_permission_hierarchy.py`（新文件，3 条用例）
- **来源会话**: 2026-09-19 12:59（commit `765df519`）
- **回滚条件**: 若未来某角色**确实需要**「持有子权限但不持有父菜单」（例如后端接口权限与前端菜单解耦），届时须**显式讨论并记录理由**，而不是加一条豁免了事

## DEC-029：幽灵权限码**删除**而非补定义

- **决策**: `statistics:partial` 从 `ROLE_PERM_MAP["duty_officer"]` / `["maintainer"]` 中**删除**，**不**在 `BUTTON_PERMS` 里补上定义。
- **原因**:
  1. 它是**幽灵码**：只在两处角色清单里出现，`MENU_LEVEL1`/`MENU_LEVEL2`/`BUTTON_PERMS` **都没有定义**。而绑定语句是 `[perm_map[c] for c in ROLE_PERM_MAP[role] if c in perm_map]`——**静默跳过**未定义的码。
  2. **实测定性**：真实库 `SELECT count(*) FROM permissions WHERE perm_code='statistics:partial'` = **0**，即它**从来没被绑过**；全仓库（`app/`、`frontend/`、测试）**零引用**。删掉是**零行为变化**。
  3. 反之若补上定义，只会**新增一个没有任何端点校验的孤儿码**——正是 P2-014 在清理的那类东西。
  4. `docs/plan/3.1` 把它列为「部分报表」按钮（parent = `statistics:report`），但从未落到 `BUTTON_PERMS`。若该按钮仍需要，**正确顺序是先定义、再加回角色清单**。
- **影响范围**: `backend/scripts/init_data.py`
- **来源会话**: 2026-09-19 12:59（commit `765df519`）
- **回滚条件**: 若 3.1 的「部分报表」被重新启用，先在 `BUTTON_PERMS` 定义并**同时**接上端点校验（否则会造出新的孤儿码，`test_permission_coverage.py` 会拦）

## DEC-030：报告导出的 ORM/dict 契约修复**只动 `timelines`**，不顺手改另两个实参

- **决策**: `generate_event_report` 里只把 `timelines` 用 `timeline_payload()` 转换；`event`/`alarm` 的 `dict(obj.__dict__)` **保持原样**。
- **原因**:
  1. 崩溃根因**只有一个**：`generate_report_html(event: Dict[str, Any], alarm: Dict[str, Any], timelines: list, ...)` 的形参**声明是 dict**，而 `timelines` 以**纯 ORM 对象**传入 → `.get()` 抛 `AttributeError`。`event`/`alarm` 走了 `__dict__` 转换，是 dict，**没有缺陷**。
  2. 按「一次只修一个根因、不顺手重构」的纪律，不动能跑的代码。
  3. **影响面是全坏而非偶发**：崩溃在遍历节点的循环里，空时间轴不触发；而真实事件恒有 `alarm`+`confirm` 两条初始节点（`create_emergency_event` 建的）→ **每个真实事件的报告都导不出**。
- **影响范围**: `backend/app/services/emergency_report_service.py`、`backend/tests/test_emergency_report.py`
- **来源会话**: 2026-09-19 12:59（commit `89d63a04`）
- **⚠️ 连带约束**: `event`/`alarm` 那两句虽能用，但**脆弱**——`event.model_dump()` 分支对 ORM 永远走不到（ORM 无此方法），实际恒走 `__dict__`，会带上 `_sa_instance_state` 且**只含已加载列**。异步下访问未加载列是 `MissingGreenlet`。仓库已有 canonical 序列化器（`event_payload` / `timeline_payload` / `alarm_payload`），**新增报告类代码不要沿用这个写法**，已立 **P2-020**

---

## 未编号的计划调整（非 ADR，仅备查）

- **开发计划总工期**: 3.1 模块由 W1-W2 调整为 W1-W3（3 周）。来源会话 2026-09-07 22:50。
- **P1-001 登录安全增强的「延期」决议已失效**: 2026-09-09 审计发现该能力在 W1 的 B-3 任务中已随登录接口一并实现（锁定 + 日志落库），延期标记为陈旧记录。详见 `.claude/sessions/2026-09-09-0048.md`。
