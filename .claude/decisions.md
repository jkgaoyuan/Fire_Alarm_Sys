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

---

## 未编号的计划调整（非 ADR，仅备查）

- **开发计划总工期**: 3.1 模块由 W1-W2 调整为 W1-W3（3 周）。来源会话 2026-09-07 22:50。
- **P1-001 登录安全增强的「延期」决议已失效**: 2026-09-09 审计发现该能力在 W1 的 B-3 任务中已随登录接口一并实现（锁定 + 日志落库），延期标记为陈旧记录。详见 `.claude/sessions/2026-09-09-0048.md`。
