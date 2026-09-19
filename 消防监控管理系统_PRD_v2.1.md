# 消防监控管理系统 — 产品需求文档（PRD）

| 项目 | 内容 |
|------|------|
| **文档版本** | v2.1（实现对齐版） |
| **编写日期** | 2026-09-07（v2.0） / **2026-09-19（v2.1 修订）** |
| **编写人** | 系统架构师 / 敏捷项目经理 |
| **技术栈** | 前端 Vue 3 + 后端 Python 3.10 + PostgreSQL |
| **交互方式** | RESTful API + WebSocket 实时推送 |
| **目标用户** | 消防值班员、维保人员、消防主管 |

---

## 0. v2.1 修订说明

**本次修订的唯一目的：让 PRD 与代码实际状态一致。** v2.0 是一份**需求基线**，成文于 2026-09-07，
此后再未随实现同步；截至 2026-09-19，其中相当一部分描述已与代码不符——有的是**没做**，
有的是**做了但和写的不一样**，还有的是**写错了**（如架构图里的 MinIO、API 章里的一批路径）。

**修订原则**：

1. **以代码为准**，不采信计划/完成报告的自我描述——本仓已多次出现完成报告标 100% 而实际未接线的情形。
2. **需求本身不因未实现而删除**，只标注状态（未实现的需求仍是需求）。
3. **凡「做了但不一样」的，走「实现偏离」记录**，不悄悄改写成现状——否则会丢掉"当初要的是什么"。

**实现状态汇总（58 条需求，含 FR-016.1 / FR-016.2 / FR-020.1；FR-037 已取消不计）**：

| 状态 | 条数 | 占比 | 含义 |
|------|:---:|:---:|------|
| ✅ 已交付 | **28** | 48% | 代码中可用，有端点/页面 |
| ⚠️ 部分交付 | **24** | 41% | 有实现但存在明确缺口，逐条见 §3.11 |
| ❌ 未实现 | **6** | 10% | FR-010 二维码、FR-021 手动联动（前端）、FR-053 操作审计、FR-054/055/056（§3.10 全章） |

**本次修订涉及的位置**：

| 位置 | 修订内容 |
|------|---------|
| 文档头 | 版本 v2.0 → v2.1，标注修订日期 |
| §0（本节） | 新增 |
| §2.1 / §2.2 / §2.4 | 架构图中的 **MinIO 实为本地磁盘**；Celery 段落的实际执行情况 |
| §3 全部 FRD 表 | 每条需求新增「**实现状态**」列 |
| §3.1 角色权限矩阵 | 与实际授予的菜单码对齐（联动预案/消防演练/应急处置/维修工单四行） |
| **§3.11（新增）** | **实现偏离明细**——本次修订的核心产出 |
| §4.1 | ER 图更正：删去不存在的 `Floor`/`Zone`，补入应急/通知/导出三域 |
| §5.4 / §5.5 / §5.8 | API 路径更正（7 条写错的路径）；§5.8 整节标为未实现 |
| §6.2 | 删去不存在的 MinIO / 字段级 AES 加密 / DOMPurify |
| §8 | 五阶段开发计划标注实际到达位置 |
| §9 | 风险表中的 Celery 描述与实际选型对齐 |
| §11 | 待确认事项重写（原仅一条，且已过时） |

> **一句话结论**：系统的**骨架是完整的**（10 个模块全部有落地代码，28 条需求完整交付），
> 但**"闭环的最后一段"普遍缺失**——多处呈现同一形态：**后端齐备、前端零入口**（FR-021、
> FR-029、FR-047 均是），或**链路接通了但最后一跳没接**（FR-020.1 的次级告警不推帧、
> FR-025 的超时升级完全不通）。详见 §3.11。

---

## 1. 项目概述

### 1.1 项目背景
为满足建筑消防设施的数字化管理需求，构建一套覆盖"设备档案 → 实时监控 → 报警联动 → 应急处置 → 巡检维保 → 演练评估 → 统计决策"全生命周期的消防监控管理系统。

### 1.2 核心目标
1. **数字化档案**：建立 8 类消防设备（烟感/温感/手报/消火栓/喷淋/排烟/防火门/应急照明）的完整电子档案。
2. **实时感知**：通过电子地图可视化展示设备状态，报警秒级推送。
3. **智能联动**：火灾报警自动触发预设联动预案（排烟/防火门/应急照明/广播）。
4. **闭环处置**：火警确认 → 应急处置 → 过程记录 → 事件归档的完整业务闭环。
5. **运维保障**：周期性巡检、故障维修、消防演练的全流程管理。
6. **权限隔离**：基于角色的访问控制（RBAC），不同角色拥有独立菜单与数据范围。

---

## 2. 技术架构

### 2.1 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      前端层 (Vue 3)                          │
│  Vue Router 4 │ Pinia │ Axios │ Element Plus │ ECharts       │
│  电子地图: Leaflet / 自定义 Canvas                            │
└──────────────────────┬──────────────────────────────────────┘
                       │ RESTful API / WebSocket
┌──────────────────────▼──────────────────────────────────────┐
│                      网关层                                    │
│  Nginx (反向代理 / 静态资源 / 负载均衡)                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                   后端服务 (Python 3.10)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │  FastAPI    │  │  WebSocket  │  │  Background Tasks   │   │
│  │  (REST API) │  │  (实时推送)  │  │  (asyncio 定时任务)  │   │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘   │
│         └─────────────────┴────────────────────┘            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │ SQLAlchemy  │  │  JWT Auth   │  │  Pydantic Schema    │   │
│  │  (ORM 2.0)  │  │  (OAuth2)   │  │  (数据校验)          │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌──────────────┐            ┌──────────────────────┐
│  PostgreSQL  │            │  Redis               │
│  (主数据库)   │            │  (WebSocket 事件流 /  │
│  版本: 15+   │            │   Token 白名单 / 缓存)│
└──────────────┘            └──────────────────────┘

  文件存储（导出报表、巡检照片）：**容器本地磁盘** `backend/storage/`
  —— 由 `backend_storage` 卷持久化，**未使用对象存储**
```

> **v2.1 更正**：原图绘有 **MinIO** 对象存储服务，实际**不存在**——
> `backend/requirements.txt` 无 MinIO 依赖、`docker-compose.yml` 无该服务。
> 真实实现是本地磁盘（`app/services/report_export_service.py:170` →
> `backend/storage/export/`）。详见 §0 修订说明与「实现偏离」小节。

### 2.2 Celery 引入时机说明

**3.1~3.6 阶段（当前）**：暂不引入 Celery，使用 FastAPI `lifespan` + `asyncio.create_task()` 处理定时任务。
- **适用场景**：巡检任务生成（3.6）、漏检扫描（3.6）、离线设备检测（3.3）
- **原因**：系统规模较小（≤10,000 设备），单进程 asyncio 定时任务已满足需求
- **优点**：减少外部依赖，降低部署复杂度

**3.9 统计报表阶段（未来评估）**：
- **触发条件**：若需跨多个服务协调任务，或报表导出数据量 >10 万行
- **替代方案**：引入 Celery + Redis 作为消息队列
- **回滚条件**：若 asyncio 出现任务重复执行/丢失等问题

**其他组件保持不变**：
- Redis 用于缓存 + WebSocket 状态存储（事件流即 Redis Stream，见 §2.3）
- **文件存储：容器本地磁盘** —— 原 v2.0 写「MinIO 用于文件存储」，
  实际**未使用任何对象存储**（`requirements.txt` 无 MinIO 依赖、compose 无该服务）。
  落盘位置 `backend/storage/`，由 `backend_storage` 卷持久化。
  ⚠️ 这意味着**多实例部署时导出文件不共享**，与 §7「水平扩展·无状态服务设计」存在张力，
  详见 §3.11 偏离项。

### 2.3 消息可靠性设计（新增）

为确保 WebSocket 断线重连后报警消息不丢失，引入 **Redis Stream** 作为消息缓冲队列：

1. 后端收到设备上报 → 写入 Redis Stream。
2. WebSocket 服务从 Stream 读取 → 推送前端。
3. **断线重连补偿**：前端重连时携带 `last_msg_id`，后端从 Stream 中读取 `last_msg_id` 之后的消息进行补发，确保报警不丢失。

### 2.4 后端技术选型

| 组件 | 选型 | 版本 | 说明 |
|------|------|------|------|
| Web 框架 | FastAPI | 0.110+ | 异步支持、自动 OpenAPI 文档、高性能 |
| ORM | SQLAlchemy | 2.0+ | 声明式模型、Alembic 迁移 |
| 认证 | OAuth2 + JWT | PyJWT 2.8+ | Bearer Token，Access Token + Refresh Token |
| 数据校验 | Pydantic | v2 | 请求/响应模型校验 |
| 异步任务 | asyncio | — | FastAPI `lifespan` + `asyncio.create_task()`（3.6 前暂不引入 Celery） |
| 消息代理 | Redis | 7.0+ | 缓存 + WebSocket 状态存储（Celery 暂缓）|
| 数据库驱动 | asyncpg | 0.29+ | PostgreSQL 异步驱动 |
| 文件存储 | **容器本地磁盘** | — | 导出报表落 `backend/storage/export/`（`report_export_service.py:170`），由 `backend_storage` 卷持久化 |
| ~~对象存储~~ | ~~MinIO SDK~~ | ~~最新~~ | **v2.1 删除**：从未引入，见 §2.2 |

### 2.5 前端技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| 框架 | Vue 3.4+ | Composition API |
| 状态管理 | Pinia | 替代 Vuex |
| UI 组件库 | Element Plus | 企业级后台组件 |
| 路由 | Vue Router 4 | 动态路由（按角色加载） |
| HTTP 客户端 | Axios | 拦截器统一处理 Token 与错误 |
| 图表 | ECharts 5 | 统计看板 |
| 地图 | Leaflet 1.9+ | 电子地图可视化 |
| 构建工具 | Vite | 快速构建与热更新 |

---

## 3. 功能需求（FRD）

### 3.1 用户登录与权限管理（FR-001 ~ FR-006）

| 编号 | 功能 | 需求描述 | 优先级 | 实现状态 |
|------|------|----------|----------|:---:|
| FR-001 | 用户登录 | 支持用户名+密码登录，密码 bcrypt 加密存储。登录成功后返回 JWT Access Token（有效期 **1h**）和 Refresh Token（有效期 7d）。 | P0 | 已交付 |
| FR-002 | 角色管理 | 内置 3 个角色：消防值班员、维保人员、消防主管。支持后台自定义角色。 | P0 | 已交付 |
| FR-003 | 菜单权限 | 每个角色绑定可访问的菜单列表。前端根据 `/api/v1/users/me/menus` 动态渲染侧边栏。 | P0 | 已交付 |
| FR-004 | 数据权限 | 数据范围控制：全部数据 / 本部门及子部门 / 仅本人。设备、报警、巡检等数据按用户数据范围过滤。 | P0 | 已交付 |
| FR-005 | Token 刷新 | Access Token 过期前自动调用 `/api/v1/auth/refresh` 换取新 Token，无感刷新。 | P0 | 已交付 |
| FR-006 | 登录安全 | 连续 5 次登录失败锁定账户 30 分钟；记录登录 IP、时间、设备信息。 | P1 | 已交付 |

**角色权限矩阵（v2.1 依据真实菜单码更正）：**

| 功能模块 | 消防值班员 | 维保人员 | 消防主管 |
|----------|:----------:|:--------:|:--------:|
| 实时监控 | ✅ 查看/确认 | ❌ | ✅ 查看 |
| 报警中心 | ✅ 确认/处置 | ❌ | ✅ 查看 |
| 设备档案 | ✅ 查看 | ✅ 查看/维修记录 | ✅ 增删改查 |
| 联动预案 | ✅ 查看/执行 | ❌ | ✅ 配置/执行 |
| **应急处置** | ✅ 进入/时间轴 | ❌ | ✅ 处置完成/关闭/导出 |
| 巡检任务 | ❌ | ✅ 执行/记录 | ✅ 计划/统计 |
| **维修工单** | ✅ 报修/查看 | ✅ 接单/维修 | ✅ 派单/验收 |
| 消防演练 | ✅ 查看/执行 | ✅ 查看/执行 | ✅ 全流程 |
| 统计报表 | 部分 | 部分 | ✅ 全部 |
| 系统管理 | ❌ | ❌ | ✅ 用户/角色 |

> **v2.1 更正说明**（依据真实库 `role_permissions` 的 `perm_type='menu'` 记录）：
> v2.0 矩阵有四处与实际不符，另有**两行缺失**：
> - **联动预案**：原写值班员 ❌，实际**可以进入**——但直到 2026-09-19 才补上菜单码
>   `linkage:plan`（此前只给了 `linkage:view`/`linkage:execute` 两个按钮码，而菜单树
>   不做「父菜单随子权限自动补齐」，导致有按钮权限却进不去页面）。
> - **消防演练**：原写值班员与维保均 ❌，实际**两者都可进入**（`drill:event`，OQ-5 方案一）。
> - **应急处置 / 维修工单**：v2.0 矩阵**没有这两行**，实际两域均已开放（`emergency:event` /
>   `repair:order`）。
>
> ⚠️ 另需注意：本节 FR-004 写「仅本人」，但**设备域与报警域已刻意降级为 `dept`**
> （自动上报的报警没有 `created_by` 可锚），巡检域锚 `responsible_user_id`、
> 维修域锚四字段 OR。详见 §3.11 偏离项。

---

### 3.2 消防设备档案（FR-007 ~ FR-012）

| 编号 | 功能 | 需求描述 | 优先级 | 实现状态 |
|------|------|----------|----------|:---:|
| FR-007 | 设备类型 | 预置 8 种类型：烟感探测器、温感探测器、手动报警按钮、消火栓、喷淋头、排烟风机、防火门、应急照明。每种类型定义专属属性模板。 | P0 | 已交付 |
| FR-008 | 设备档案 CRUD | 设备编码（唯一）、名称、类型、厂商、型号、安装位置（区域关联）、安装日期、质保期、维护周期、平面图坐标（x, y）、状态。 | P0 | 已交付 |
| FR-009 | 批量导入 | 提供 Excel 模板下载，支持批量导入设备。校验：编码唯一、区域存在、类型有效。导入结果返回成功/失败明细。 | P0 | 已交付 |
| FR-010 | 二维码标签 | 每个设备生成唯一二维码（内容：`https://系统域名/device/{device_code}`），支持打印导出。扫码可查看设备详情。 | P1 | 未实现 |
| FR-011 | 设备历史 | 记录设备的状态变更历史、报警历史、维修历史、巡检历史。 | P1 | 已交付 |
| FR-012 | 设备搜索 | 支持按编码、名称、类型、区域、状态组合筛选；支持分页（默认 20 条/页）。 | P0 | 已交付 |

**设备状态枚举：** `normal`（正常）、`alarm`（报警）、`fault`（故障）、`shield`（屏蔽）、`offline`（离线）、**`retired`（已退役）**（新增）

**设备退役流程（新增）：**
- 删除"物理删除"按钮，改为"退役"操作。
- 点击退役后，设备状态变更为 `retired`，前端列表默认过滤该状态设备（需勾选"显示已退役"才可见）。
- 该设备关联的历史报警、巡检记录**必须保留**，不可级联删除。

---

### 3.3 实时监控与电子地图（FR-013 ~ FR-018）

| 编号 | 功能 | 需求描述 | 优先级 | 实现状态 |
|------|------|----------|----------|:---:|
| FR-013 | 实时状态推送 | 设备状态变化通过 WebSocket 推送至前端。连接地址：`/ws/devices`。心跳间隔 30 秒。 | P0 | 已交付 |
| FR-014 | 监控大屏 | 总览面板：设备总数、在线数、报警数、故障数。报警列表按时间倒序，**未确认火警强制置顶**，新报警**红色呼吸灯/左右滑入动画**效果，直至被确认。 | P0 | 已交付 |
| FR-015 | 电子地图 | 支持上传楼层平面图（PNG/JPG/PDF 转 PNG）。设备以图标形式叠加，按状态着色。支持缩放、拖拽、点击弹详情。 | P0 | 已交付 |
| FR-016 | 报警声光提示 | 新报警触发浏览器 Notification + 页面内音频告警（可手动静音/取消）。 | P0 | 已交付 |
| FR-017 | 报警分级 | 火警（红色）、预警（橙色）、故障（黄色）、屏蔽（灰色）。不同级别不同提示音。 | P1 | 已交付 |
| FR-018 | 历史轨迹 | 查询单个设备指定时间范围内的状态变化轨迹，支持导出。 | P1 | 已交付 |

**电子地图性能优化（新增）：**
- 前端上传平面图时，若图片宽度 > 2000px，自动调用后端接口进行压缩（质量 0.8）或切片处理。
- 地图初始化时，仅加载当前视口（Viewport）内的设备图标；缩放或拖拽时，动态请求可视区域内的设备数据（懒加载）。

**报警消音与复位（新增 FR-016.1 ~ FR-016.2）：**

| 编号 | 功能 | 需求描述 | 优先级 | 实现状态 |
|------|------|----------|----------|:---:|
| FR-016.1 | 报警消音 | 点击"消音"后，前端停止播放报警音频，浏览器通知栏消除闪烁，但报警列表中的记录状态保持不变（仍为待确认/已确认）。 | P0 | 已交付 |
| FR-016.2 | 报警复位 | 仅当设备物理状态恢复正常后，值班员可点击"系统复位"，清除界面上的故障/火警标识，使设备状态回滚至"正常"。 | P0 | 已交付 |

---

### 3.4 报警联动（FR-019 ~ FR-024）

| 编号 | 功能 | 需求描述 | 优先级 | 实现状态 |
|------|------|----------|----------|:---:|
| FR-019 | 联动预案配置 | 按"区域 + 火灾类型（A类/B类/C类/电气）"配置联动规则。规则包含：触发条件（设备类型+报警类型）→ 动作列表（启动排烟/关闭防火门/启动应急照明/疏散广播）。 | P0 | 部分交付 |
| FR-020 | 自动联动 | 报警触发后，联动引擎 5 秒内自动下发所有关联动作指令。每条指令记录执行状态：pending → sent → acked → success / failed。 | P0 | 部分交付 |
| FR-021 | 手动联动 | 值班员或主管可在监控页面手动选择预案并执行。需二次确认弹窗。 | P0 | 未实现 |
| FR-022 | 联动日志 | 记录每次联动的触发源、触发时间、执行动作、执行结果、耗时。支持按时间/区域/预案筛选。 | P0 | 部分交付 |
| FR-023 | 预案启用/停用 | 预案可设置启用状态，停用后不参与自动联动。 | P1 | 已交付 |
| FR-024 | 联动模拟 | 支持模拟触发（不操作真实设备），用于测试预案逻辑。 | P2 | 已交付 |

**联动失败处理机制（新增 FR-020.1）：**

| 编号 | 功能 | 需求描述 | 优先级 | 实现状态 |
|------|------|----------|----------|:---:|
| FR-020.1 | 联动失败处理 | 若指令执行状态变为 `failed`（如设备离线、响应超时），系统需立即在"报警中心"生成一条**次级告警**（级别：严重），并弹窗提示值班员"联动设备执行失败，请人工介入"。 | P0 | 部分交付 |

---

### 3.5 火警确认与应急处置（FR-025 ~ FR-031）

| 编号 | 功能 | 需求描述 | 优先级 | 实现状态 |
|------|------|----------|----------|:---:|
| FR-025 | 火警确认流程 | 报警产生后状态为"待确认"。值班员需在 5 分钟内现场确认或视频复核。**超时（5分钟）未确认自动升级通知主管**，通知方式：① 系统内通知（前端右上角红点）。 | P0 | 部分交付 |
| FR-026 | 误报处理 | 确认为误报时，必须选择/填写误报原因（设备故障/环境因素/人为误触/其他），记录确认人、确认时间。 | P0 | 已交付 |
| FR-027 | 真实火警处置 | 确认真实火警后，自动启动应急处置流程：生成应急事件 → 记录处置时间轴 → 参与人员签到。 | P0 | 已交付 |
| FR-028 | 处置时间轴 | 以时间轴形式记录处置关键节点：报警时间 / 确认时间 / 联动启动时间 / 人员疏散时间 / 火情控制时间 / 处置完成时间。 | P0 | 部分交付 |
| FR-029 | 人员签到 | 应急处置过程中，相关人员可通过系统签到（记录时间、GPS 位置可选）。 | P1 | 部分交付 |
| FR-030 | 事件归档 | 事件结束后生成完整事件报告，包含：报警信息、联动记录、确认记录、处置时间轴、参与人员、现场照片。支持 PDF 导出。 | P0 | 部分交付 |
| FR-031 | 事件状态机 | `pending` → `confirmed` / `false_alarm` → `processing` → `resolved` / `closed` | P0 | 部分交付 |

---

### 3.6 设备巡检（FR-032 ~ FR-037）

| 编号 | 功能 | 需求描述 | 优先级 | 实现状态 |
|------|------|----------|----------|:---:|
| FR-032 | 巡检计划 | 按设备类型/区域/责任人制定周期计划：每日/每周/每月/每季度/每年。支持设置执行时间段。 | P0 | 部分交付 |
| FR-033 | 任务生成 | 每日凌晨 Celery 定时任务自动生成当日巡检任务。任务状态：待执行 / 执行中 / 已完成 / 漏检。 | P0 | 部分交付 |
| FR-034 | ~~移动端巡检~~ → **PC 端手动巡检** | ~~维保人员通过手机扫码设备二维码进入巡检页面。~~ 维保人员在 PC 端「巡检任务」列表中选择当日任务，点击设备名称进入巡检填报页面。填写巡检项结果（正常/异常），异常可拍照上传、填写备注。 | P0 | 部分交付 |
| FR-035 | 漏检统计 | 自动统计漏检任务，生成漏检报告。漏检超过 3 次触发预警通知主管。 | P1 | 部分交付 |
| FR-036 | 巡检记录 | 所有巡检记录归档，支持按设备/人员/时间筛选查询。 | P0 | 部分交付 |
| ~~FR-037~~ | ~~离线巡检~~ | ~~移动端支持离线缓存巡检数据，网络恢复后自动同步。冲突时以服务端接收时间为准，但需校验设备状态版本号，防止覆盖最新维修记录。~~ | ~~P2~~ | **已取消**：移动端巡检改为 PC 端手动记录，无需离线能力。 已取消 |

---

### 3.7 故障维修（FR-038 ~ FR-042）

| 编号 | 功能 | 需求描述 | 优先级 | 实现状态 |
|------|------|----------|----------|:---:|
| FR-038 | 故障报修 | 巡检发现故障或监控发现故障时，自动生成报修工单。工单关联设备与故障描述。 | P0 | 部分交付 |
| FR-039 | 工单流转 | 状态流：`待处理` → `已派单` → `维修中` → `待验收` → `已完成`。支持退回。 | P0 | 已交付 |
| FR-040 | 维修记录 | 记录维修过程、更换配件、维修人员、维修时间、维修结果。维修完成后设备状态自动恢复"正常"。 | P0 | 部分交付 |
| FR-041 | 维修验收 | 工单完成后需验收人确认。验收不通过退回重新维修。 | P1 | 已交付 |
| FR-042 | 维修统计 | 统计平均维修时长、故障类型分布、维修人员工作量。 | P1 | 已交付 |

---

### 3.8 消防演练（FR-043 ~ FR-047）

| 编号 | 功能 | 需求描述 | 优先级 | 实现状态 |
|------|------|----------|----------|:---:|
| FR-043 | 演练计划 | 制定年度/季度演练计划：演练时间、地点、类型（疏散/灭火/综合）、参与部门/人员。 | P1 | 部分交付 |
| FR-044 | 演练执行 | 演练当天记录实际执行过程：时间节点、现场照片/视频、模拟报警触发记录。 | P1 | 部分交付 |
| FR-045 | 演练数据隔离 | 演练期间产生的报警、联动标记为 `drill=true`，不参与真实业务统计，演练结束后可归档或清理。 | P0 | 部分交付 |
| FR-046 | 演练评估 | 按预设评估项打分（响应时间/疏散效率/设备联动/人员配合），记录问题与改进措施。 | P1 | 部分交付 |
| FR-047 | 演练报告 | 生成演练评估报告，支持 PDF/Word 导出。 | P1 | 部分交付 |

---

### 3.9 统计报表（FR-048 ~ FR-053）

| 编号 | 功能 | 需求描述 | 优先级 | 实现状态 |
|------|------|----------|----------|:---:|
| FR-048 | 设备完好率看板 | 饼图展示正常/报警/故障/屏蔽设备占比。支持按区域下钻。 | P0 | 部分交付 |
| FR-049 | 报警趋势图 | 折线图展示近 7 天/30 天/90 天报警数量趋势，按报警类型分组。 | P0 | 已交付 |
| FR-050 | 故障 TOP10 | 柱状图展示故障次数最多的前 10 个设备，支持点击跳转详情。 | P1 | 已交付 |
| FR-051 | 巡检完成率 | 统计各责任人/区域的巡检完成率、漏检率。 | P1 | 部分交付 |
| FR-052 | 报表导出 | 所有统计看板支持导出 Excel/CSV。大数据量（>1万行）走异步任务，完成后消息通知下载。 | P0 | 部分交付 |
| FR-053 | 操作审计 | 记录所有写操作日志：操作人、IP、时间、模块、操作类型、变更内容（JSON diff）。保留 180 天。 | P0 | 未实现 |

---

### 3.10 系统配置与运维（新增章节，FR-054 ~ FR-056）

| 编号 | 功能 | 需求描述 | 优先级 | 实现状态 |
|------|------|----------|----------|:---:|
| FR-054 | 数据字典管理 | 支持管理员动态配置设备类型、报警级别、故障原因等枚举值。前端下拉框根据字典接口动态渲染，无需发版即可新增类型。 | P1 | 未实现 |
| FR-055 | 日志自动清理 | 配置定时任务（Celery Beat），每日凌晨清理超过 180 天的操作审计日志和 WebSocket 历史消息，释放数据库空间。 | P1 | 未实现 |
| FR-056 | 通知渠道配置 | 集成邮件服务配置。在"超时未确认"或"联动失败"场景下，支持配置是否发送邮件给主管。 | P2 | 未实现 |

---

### 3.11 实现偏离明细（v2.1 新增）

> 本节是本版修订的**核心产出**。收录原则：**只收「需求与代码不一致」且已定位到具体代码位置的事实**，
> 不收推测、不收「大概没做」。每条都给出可核查的 `file:line`。

#### 3.11.1 先看形态：同一类缺口反复出现

逐条读容易只见树木。58 条需求的缺口其实高度同构，归为四类：

**① 后端齐备、前端零入口**（3 条）

后端端点写好、`api/*.js` 封装写好，但**没有任何视图调用它**。用户点不到，功能等于不存在。

| 需求 | 后端 | 前端 |
|------|------|------|
| **FR-021 手动联动** | `POST /linkage-plans/execute`（`linkage_plans.py:496-546`） | ❌ 无按钮、无二次确认弹窗 |
| **FR-029 人员签到** | `add_timeline_node` 支持 `check_in`（`emergency_service.py:263-301`） | ❌ `Event.vue` 无签到入口，`TimelineEditor.vue:97-105` 选项表里没有「签到」 |
| **FR-047 演练报告 Word** | `_generate_word` 可经 `POST /reports/export`（`task_type=drill_report`）触达 | ❌ `drill/Event.vue:317-333` 只调 HTML；`ExportCenter.vue` 的 `taskTypeMap` 有 `drill_report` 却无发起入口 |

> 本类缺陷**不会报错**：后端测试直连端点、前端测试 mock 掉 API 模块，两侧各自全绿，
> 断的是中间那一段。2026-09-19 已按同一形态修过一处（应急事件的 `resolve`/`close`）。

**② 链路接通了，但最后一跳没接**（4 条）

| 需求 | 断在哪 |
|------|--------|
| **FR-025 超时升级** | 见 3.11.2，**完全不通**（两个独立成因） |
| **FR-020.1 次级告警弹窗** | 告警**能落库**，但 `raise_alarm` 不推送；前端 `stores/monitor.js:176-212` 的 `handleFrame` **无 `linkage_failed` 分支** → 报警中心不实时出现、无弹窗 |
| **FR-033 任务「已完成」** | 定时生成已生效，但 `crud/inspection.py:154-175` 的 `update_status_to_completed` **零调用** → 该状态**不可达** |
| **FR-035 漏检预警** | 扫描能标 `missed`，但只 `return alert_plans` 不写 `Notification`；API `inspection.py:723` 的 `notification_sent` **硬编码 False** |

**③ 「字段在、语义不在」**——模型留了位置，但填的内容与需求不符（FR-040 的配件、FR-046 的评估项、
FR-044 的 `drill_id` 缺失、FR-022 的耗时）。

**④ 文档自身写错**——不是实现的问题，是 PRD 写错了，见 3.11.4。

#### 3.11.2 逐条偏离

| FR | 偏离内容 | 依据 |
|----|---------|------|
| FR-001 | Refresh Token **不是随响应 body 返回**，而是经 `Set-Cookie`（httpOnly, max_age=604800）下发；前端仅 localStorage 存 Access Token。功能等价，**交付形态与 PRD 描述不一致** | `api/v1/auth.py:57-65`、`utils/auth.js:1-2` |
| FR-004 | **「仅本人」在设备域与报警域被刻意降级为「本部门」**；巡检域 `self` 锚 `responsible_user_id`、维修域锚四字段 OR。均非字面的「本人 `created_by`」 | `device_service.py:213-228`、`monitor_service.py:7`、DEC-012/DEC-021 |
| FR-019 | ① 火灾类型只实现 `fire`/`pre_fire`，PRD 要的 **A/B/C/电气分级未落地**（schema 注释写了 `A/B/C/electrical` 但引擎按 `fire_type == alarm.alarm_type` 匹配）② `trigger_device_type_id` 虽入表单，引擎匹配时是 **`# 暂不校验`** | `PlanForm.vue:42-48`、`schemas/linkage.py:18`、`linkage_engine_service.py:110-114` |
| FR-020 | ① 状态机**缺 `acked` 态**（实现为 pending→sent→success/failed；`docs/plan/3.4` 已文档化该简化）② **「5 秒内」无超时控制**，仅注释写着，无超时降级 | `linkage_executor.py:20-68`、`linkage_engine_service.py:78-80` |
| FR-020.1 | ① 次级告警级别为 `fault`/`minor`，PRD 要求**「严重」** ② **不推 `alarm_new`**、前端无 `linkage_failed` 分支 → **「报警中心生成 + 弹窗提示值班员」不成立**，只在刷新后可见 | `models/alarm.py:48-53`、`linkage_engine_service.py:291-298`、`stores/monitor.js:176-212` |
| FR-022 | 日志模型**无「耗时」字段**（有 `executed_at`/`completed_at` 但未计算）；列表**无「按区域」筛选** | `models/linkage.py:60-61`、`linkage_logs.py:66-92` |
| FR-025 | **超时升级链路完全不通**，两个**互相独立**的成因：① `emergency_service.py:177` 访问 `alarm.emergency_event` 触发异步懒加载 → `MissingGreenlet`，被 `scan_loop` 的 `except` 吞掉只打印 `Scan error`；② 扫描只取 `status=="pending"`，而事件**只在确认真实火警时**创建 → `escalated_event_ids` 恒空 → `:187-188` 直接 `return 0`。另：「视频复核」**全仓无实现** | `emergency_service.py:153-218, 247-248`、`alarm_service.py:213` |
| FR-028 | 时间轴骨架在，但 **「联动启动时间」不自动记录**——联动写的是 `alarm_linkage_logs`，引擎不写 emergency timeline，其余节点靠人工补 | `emergency_service.py:130-147` |
| FR-030 | ① **非 PDF**，为 HTML 直出（`HTMLResponse`）② 报告**缺「联动记录 / 参与人员 / 现场照片」**，只有基本信息+报警信息+时间轴 | `emergency_events.py:236-255`、`emergency_report_service.py:62-120` |
| FR-031 | 报警侧状态机有效；但**事件 `resolve`/`close` 无状态机校验**（直接赋值 `status`）——`closed` 可被覆盖回 `resolved`、`resolved` 可重复处置且 `complete` 节点**无去重**；事件创建即 `processing`，**无 pending/confirmed 事件态** | `emergency_service.py:328, 371`、`CLAUDE.md` 待办 P1-014 |
| FR-032 | **「支持设置执行时间段」未实现**——schema 无时段字段，前端表单无时段输入 | `schemas/inspection.py:41-51`、`PlanForm.vue` |
| FR-034 | ① **拍照上传是假的**：`ExecutionDialog.vue:217` 的 `photos: []` 硬编码、`action="#"`、`on-remove`/preview 空实现 ② 交互是「执行巡检」按钮弹窗选设备，**非 PRD 写的「点设备名进入填报页」** | `ExecutionDialog.vue:217`、`Task.vue:108-116` |
| FR-036 | **缺「按人员筛选」**（记录端点无 `inspected_by` 参数；仅任务端点有 `responsible_user_id`） | `inspection.py:621-697` |
| FR-038 | **「监控发现故障时自动生成工单」未实现**——`device_report_service` 与离线扫描只 `raise_alarm(...)` 产 fault 报警，**无建单调用**；只有「巡检发现异常」一条真自动路径。模型预留了 `alarm_id` 关联列但无链路 | `inspection_service.py:498-514`、`models/repair.py:75-77` |
| FR-040 | ① **「维修过程 / 更换配件」无结构化字段**，只能塞进自由文本 `repair_result` ② **设备状态在「验收通过」时恢复**，而 PRD 写「维修完成即恢复」——`complete()` 只置 `pending_accept`、不动设备状态 | `models/repair.py:113`、`crud/repair.py:226-227, 267-276` |
| FR-043 | **无「年度/季度」维度**，只有单一 `planned_at`；前端为扁平计划列表 | `models/drill.py:35-67` |
| FR-044 | **「模拟报警触发记录」不落演练**——`Alarm` 只有布尔 `is_drill`，**没有 `drill_id` 外键**；`is_drill=True` 的告警来自联动模拟测试或上报载荷，**与具体某场演练无关** | `models/alarm.py`（全表无 `drill_id`） |
| FR-045 | **「归档」未实现**：`DrillStatus` 只有 planned/ongoing/completed/cancelled，无 `archived` 态也无归档端点；**「清理」只有物理删除** | `schemas/drill.py:23-28`、`api/drills.py:432-446` |
| FR-046 | **「预设评估项」未落地**：`EvaluationDialog.vue:160-166` 打开时只 `addItem()` ×4 生成四个**空白项**（label 为空、默认 10 分），评估项完全由用户手填 | `EvaluationDialog.vue:160-166` |
| FR-048 | 后端支持 `org_id` 递归下钻，但**前端无区域选择器入口**，下钻只能靠 URL `?org_id=` 或空面包屑 | `statistics.py:22-31`、`DeviceStatus.vue:130-135` |
| FR-051 | ① **漏检率未作为比率计算**（只返回 `missed` 计数）② **区域仅作后端过滤**、非分组维度，且前端不传 `org_id` | `statistics_service.py:213-311` |
| FR-052 | ① **异步是 FastAPI `BackgroundTasks` 而非 Celery**（符合项目规范，与 PRD 措辞不符）② **无「完成后消息通知」**，前端靠 **5 秒轮询** ③ **CSV 未实现**（仅 xlsx/docx，而 `reports.py:40` 注释写 Excel/CSV 与实现不符）④ 导出数据由前端传当前页数组，**>1 万行的异步分支在看板上几乎不可达** | `reports.py:33-63`、`report_export_service.py:149-192`、`ExportCenter.vue:216-221` |

**另有两条前后端契约不一致（不属于某条 FR，但会造成数据静默丢失）：**

- **时间轴节点词表不一致**：前端 `TimelineEditor.vue:97-105` 用
  `alarm_occurred` / `manual_confirm` / `field_confirmed` / …，后端
  `models/emergency.py:47` 与报告映射 `emergency_report_service.py:98-108` 用
  `alarm` / `confirm` / `linkage` / `evacuate` / `control` / `complete`。
  前端新增节点的 `type` **与后端和报告对不上**。
- **备注字段名不一致**：`TimelineEditor` 提交 `remark`，而后端 schema 只认
  `description`（`schemas/emergency.py:63-69`）→ **用户填的备注不落库**。

#### 3.11.3 技术选型类偏离

| 项 | PRD 原写 | 实际 | 说明 |
|----|---------|------|------|
| 定时任务 | Celery / Celery Beat（FR-033、FR-055、§9） | **FastAPI `lifespan` + `asyncio.create_task()`** | §2.2 已声明的决策，但 FR-055 与 §9 未同步——**PRD 内部自相矛盾**。CLAUDE.md 引用规范写明「3.1~3.6 暂不引入 Celery」 |
| 文件存储 | MinIO 对象存储 | **容器本地磁盘** `backend/storage/` | 从未引入。⚠️ 与 §7「无状态服务设计，支持多实例部署」存在张力：**多实例下导出文件不共享** |
| 设备接入协议 | §11 称「硬件协议确定为 MQTT」 | **HTTP `POST /monitor/report` + `X-Device-Key` 预共享密钥** | 代码里 MQTT **只以「后续适配层」出现在三处注释中**，无任何实现 |
| 联动指令状态机 | `pending → sent → acked → success/failed` | `pending → sent → success/failed` | `acked` 合并入 `success`（`docs/plan/3.4` A-1/C-3 已记录） |
| 事件报告格式 | PDF（FR-030） | **HTML 直出**，PDF 靠浏览器打印 | `HTMLResponse`；前端落 `.html` |
| 敏感字段加密 | AES-256-GCM 字段级加密（§6.2） | **无任何 AES 实现** | 全仓 grep 零命中 |
| 富文本过滤 | DOMPurify（§6.2） | **无该依赖**，且系统无富文本输入 | — |

#### 3.11.4 PRD 自身的错误（本次更正，非实现问题）

| 位置 | v2.0 写的 | 实际 |
|------|----------|------|
| §2.1 架构图 | 绘有 MinIO 服务 | 无此服务 |
| §2.4 选型表 | 文件存储 = MinIO SDK | 本地磁盘 |
| §3.1 角色权限矩阵 | 联动预案值班员 ❌、消防演练值班员/维保 ❌；**缺应急处置、维修工单两行** | 四行均需更正，见 §3.1 |
| §4.1 ER 图 | `Organization ─< Floor ─ Zone ─< Device` | **`Floor`/`Zone` 两张表不存在**，设备直接挂 `org_id`；且漏画应急/通知/导出三域 |
| §5.4 | `GET /linkage-plans/{id}/logs` | 实为独立域 `GET /alarm-linkage-logs` |
| §5.5 | `/api/v1/emergency-events*`（4 条） | 实为 **`/api/v1/emergency/events*`**；`timeline` 实为复数 `timelines`；漏 `close` |
| §5.8 | 4 个 `/config/*` 端点 | **全部不存在**（§3.10 未实现） |
| §6.2 | MinIO / AES / DOMPurify 三条 | 均不成立 |

> **§4.1 与 §5 的更正已就地进行**；§5 的 `/config/*` 四条保留但划除，标明「未实现」，
> 以保留原始设计意图。

---

## 4. 数据模型设计

### 4.1 核心 ER 关系

```
User (用户) ───< user_roles >─── Role (角色) ───< role_permissions >─── Permission (权限)
 │
 └── Organization (组织架构) ───< Device (设备, 直接挂 org_id)
                                  │
                                  ├── DeviceStatusLog (状态日志)
                                  ├── Alarm (报警) ───< AlarmLinkageLog (联动日志)
                                  │      │                  │
                                  │      │                  └── LinkagePlan (联动预案)
                                  │      └──< EmergencyEvent (应急事件) ───< EmergencyTimeline (处置时间轴)
                                  ├── InspectionTask (巡检任务) ─── InspectionRecord (巡检记录)
                                  ├── RepairOrder (维修工单)
                                  └── DrillEvent (演练事件) ─── DrillEvaluation (演练评估)

User ───< Notification (通知中心)          ReportExportTask (导出中心，task_no)
User ───< LoginLog (登录日志)
```

### 4.2 核心表结构（PostgreSQL）

```sql
-- 1. 用户与权限
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,  -- bcrypt
    real_name VARCHAR(50),
    phone VARCHAR(20),
    email VARCHAR(100),
    org_id BIGINT REFERENCES organizations(id),
    data_scope VARCHAR(20) DEFAULT 'self', -- all / dept / self
    status VARCHAR(20) DEFAULT 'active',   -- active / locked / disabled
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE roles (
    id BIGSERIAL PRIMARY KEY,
    role_code VARCHAR(50) UNIQUE NOT NULL, -- duty_officer / maintainer / chief
    role_name VARCHAR(50) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE user_roles (
    user_id BIGINT REFERENCES users(id) ON DELETE RESTRICT,  -- 优化：禁止级联删除
    role_id BIGINT REFERENCES roles(id) ON DELETE RESTRICT,   -- 优化：禁止级联删除
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE permissions (
    id BIGSERIAL PRIMARY KEY,
    perm_code VARCHAR(100) UNIQUE NOT NULL,  -- device:view, alarm:confirm
    perm_name VARCHAR(100),
    perm_type VARCHAR(20),  -- menu / button / api
    parent_id BIGINT REFERENCES permissions(id),
    route_path VARCHAR(200),
    sort_order INT DEFAULT 0
);

CREATE TABLE role_permissions (
    role_id BIGINT REFERENCES roles(id) ON DELETE RESTRICT,   -- 优化：禁止级联删除
    perm_id BIGINT REFERENCES permissions(id) ON DELETE RESTRICT,  -- 优化：禁止级联删除
    PRIMARY KEY (role_id, perm_id)
);

-- 2. 组织架构
CREATE TABLE organizations (
    id BIGSERIAL PRIMARY KEY,
    parent_id BIGINT REFERENCES organizations(id),
    org_name VARCHAR(100) NOT NULL,
    org_type VARCHAR(20),  -- building / floor / zone
    map_image_url VARCHAR(500),  -- 平面图
    map_image_width INT,  -- 3.3 新增：原始图宽（前端坐标换算）
    map_image_height INT,  -- 3.3 新增：原始图高
    sort_order INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. 设备档案
CREATE TABLE device_types (
    id BIGSERIAL PRIMARY KEY,
    type_code VARCHAR(50) UNIQUE NOT NULL,  -- smoke_detector / heat_detector / ...
    type_name VARCHAR(50) NOT NULL,
    category VARCHAR(20),  -- detector / alarm / extinguishing / exhaust / door / lighting
    attribute_schema JSONB,  -- 属性模板
    icon_url VARCHAR(500)
);

CREATE TABLE devices (
    id BIGSERIAL PRIMARY KEY,
    device_code VARCHAR(100) UNIQUE NOT NULL,
    device_name VARCHAR(100) NOT NULL,
    type_id BIGINT REFERENCES device_types(id),
    org_id BIGINT REFERENCES organizations(id),
    manufacturer VARCHAR(100),
    model VARCHAR(100),
    brand VARCHAR(50),          -- 新增：独立字段，用于统计筛选，建索引
    spec VARCHAR(100),          -- 新增：独立字段，用于筛选
    install_date DATE,
    warranty_expire_date DATE,
    maintain_cycle INT,  -- 维护周期（天）
    status VARCHAR(20) DEFAULT 'normal',  -- normal / alarm / fault / shield / offline / retired
    map_x DECIMAL(10, 2),  -- 平面图 X 坐标
    map_y DECIMAL(10, 2),  -- 平面图 Y 坐标
    last_report_at TIMESTAMPTZ,  -- 3.3 新增：最近一次设备上报时间，用于在线/离线判定
    -- qr_code_url VARCHAR(500),  -- 【已取消】二维码标签功能取消，此字段不再使用
    attributes JSONB,  -- 扩展属性（仅存非筛选属性）
    is_deleted BOOLEAN DEFAULT FALSE,  -- 新增：逻辑删除标记
    created_by BIGINT REFERENCES users(id),  -- 新增：数据权限 'self' 范围依赖
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 新增索引（优化高频筛选查询性能）
CREATE INDEX idx_devices_brand ON devices(brand);
CREATE INDEX idx_devices_spec ON devices(spec);
CREATE INDEX idx_devices_created_by ON devices(created_by);  -- 新增：数据权限查询优化
CREATE INDEX idx_devices_last_report_at ON devices(last_report_at);  -- 3.3 新增：离线扫描

-- 4. 报警与联动
CREATE TABLE alarms (
    id BIGSERIAL PRIMARY KEY,
    device_id BIGINT REFERENCES devices(id),
    device_code VARCHAR(100),  -- 3.3 新增：报警时从 devices.device_code 快照，列表展示免 JOIN
    org_id BIGINT REFERENCES organizations(id),  -- 3.3 新增：设备归属区域快照，实时推送/数据权限过滤
    alarm_type VARCHAR(20) NOT NULL,  -- fire / pre_fire / fault / shield
    alarm_level VARCHAR(20),  -- critical / major / minor
    status VARCHAR(20) DEFAULT 'pending',  -- pending / confirmed / false_alarm / processing / resolved
    confirmed_by BIGINT REFERENCES users(id),
    confirmed_at TIMESTAMPTZ,
    confirm_result VARCHAR(20),  -- real / false_alarm
    false_reason TEXT,
    location_description VARCHAR(255),
    is_drill BOOLEAN DEFAULT FALSE,
    pending_since TIMESTAMPTZ,  -- 3.3 新增：首次进入 pending 的时间，供后续超时升级（FR-025）使用
    silenced_at TIMESTAMPTZ,  -- 3.3 新增：消音时间
    silenced_by BIGINT REFERENCES users(id),  -- 3.3 新增：消音操作人
    reset_at TIMESTAMPTZ,  -- 3.3 新增：复位时间
    reset_by BIGINT REFERENCES users(id),  -- 3.3 新增：复位操作人
    reset_physical_restored BOOLEAN DEFAULT FALSE,  -- 3.3 新增：复位时是否已物理恢复
    created_by BIGINT REFERENCES users(id),  -- 新增：数据权限 'self' 范围依赖
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),  -- 3.3 新增：状态/消音/复位变更时间
    resolved_at TIMESTAMPTZ
);

-- 3.3 新增索引
CREATE INDEX idx_alarms_org_id ON alarms(org_id);
CREATE INDEX idx_alarms_device_id_status ON alarms(device_id, status);

CREATE TABLE linkage_plans (
    id BIGSERIAL PRIMARY KEY,
    plan_name VARCHAR(100) NOT NULL,
    org_id BIGINT REFERENCES organizations(id),
    fire_type VARCHAR(20),  -- A / B / C / electrical
    trigger_device_type_id BIGINT REFERENCES device_types(id),
    trigger_alarm_type VARCHAR(20),
    actions JSONB NOT NULL,  -- [{action_type, target_device_type, delay_seconds, params}]
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE alarm_linkage_logs (
    id BIGSERIAL PRIMARY KEY,
    alarm_id BIGINT REFERENCES alarms(id),
    plan_id BIGINT REFERENCES linkage_plans(id),
    action_type VARCHAR(50) NOT NULL,  -- start_exhaust / close_door / start_lighting / broadcast
    target_device_id BIGINT REFERENCES devices(id),
    status VARCHAR(20) DEFAULT 'pending',  -- pending / sent / success / failed
    executed_at TIMESTAMPTZ,
    result_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. 应急处置
CREATE TABLE emergency_events (
    id BIGSERIAL PRIMARY KEY,
    alarm_id BIGINT REFERENCES alarms(id),
    event_no VARCHAR(50) UNIQUE NOT NULL,  -- EV-20260907-001
    status VARCHAR(20) DEFAULT 'processing',  -- processing / resolved / closed
    started_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    summary TEXT,
    created_by BIGINT REFERENCES users(id)
);

CREATE TABLE emergency_timelines (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT REFERENCES emergency_events(id),
    node_type VARCHAR(50) NOT NULL,  -- alarm / confirm / linkage / evacuate / control / complete
    node_title VARCHAR(100),
    description TEXT,
    operator_id BIGINT REFERENCES users(id),
    operated_at TIMESTAMPTZ DEFAULT NOW(),
    attachments JSONB  -- [{file_name, file_url}]
);

-- 6. 巡检
CREATE TABLE inspection_plans (
    id BIGSERIAL PRIMARY KEY,
    plan_name VARCHAR(100),
    org_id BIGINT REFERENCES organizations(id),
    device_type_id BIGINT REFERENCES device_types(id),
    cycle_type VARCHAR(20),  -- daily / weekly / monthly / quarterly / yearly
    cycle_days INT,
    responsible_user_id BIGINT REFERENCES users(id),
    start_date DATE,
    end_date DATE,
    is_enabled BOOLEAN DEFAULT TRUE
);

CREATE TABLE inspection_tasks (
    id BIGSERIAL PRIMARY KEY,
    plan_id BIGINT REFERENCES inspection_plans(id),
    task_date DATE NOT NULL,
    responsible_user_id BIGINT REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'pending',  -- pending / doing / completed / missed
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE inspection_records (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT REFERENCES inspection_tasks(id),
    device_id BIGINT REFERENCES devices(id),
    result VARCHAR(20),  -- normal / abnormal
    abnormal_desc TEXT,
    photos JSONB,
    inspected_by BIGINT REFERENCES users(id),
    created_by BIGINT REFERENCES users(id),  -- 新增：数据权限 'self' 范围依赖
    inspected_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. 维修工单
CREATE TABLE repair_orders (
    id BIGSERIAL PRIMARY KEY,
    order_no VARCHAR(50) UNIQUE NOT NULL,  -- RO-20260907-001
    device_id BIGINT REFERENCES devices(id),
    alarm_id BIGINT REFERENCES alarms(id),
    fault_desc TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',  -- pending / assigned / repairing / pending_accept / completed / returned
    reporter_id BIGINT REFERENCES users(id),
    repairer_id BIGINT REFERENCES users(id),
    assigned_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    repair_result TEXT,
    created_by BIGINT REFERENCES users(id),  -- 新增：数据权限 'self' 范围依赖
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. 演练
CREATE TABLE drill_events (
    id BIGSERIAL PRIMARY KEY,
    drill_name VARCHAR(100),
    drill_type VARCHAR(20),  -- evacuation / firefighting / comprehensive
    planned_at TIMESTAMPTZ,
    actual_start_at TIMESTAMPTZ,
    actual_end_at TIMESTAMPTZ,
    location VARCHAR(255),
    participants JSONB,  -- [{user_id, role, sign_in_at}]
    status VARCHAR(20) DEFAULT 'planned',  -- planned / ongoing / completed / cancelled
    is_drill_data BOOLEAN DEFAULT TRUE,
    created_by BIGINT REFERENCES users(id)
);

-- 9. 操作审计
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    username VARCHAR(50),
    operation VARCHAR(100),  -- CREATE / UPDATE / DELETE / LOGIN / LOGOUT
    module VARCHAR(50),
    method VARCHAR(10),  -- GET / POST / PUT / DELETE
    request_url VARCHAR(500),
    request_params JSONB,
    old_value JSONB,
    new_value JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引优化
CREATE INDEX idx_devices_org ON devices(org_id);
CREATE INDEX idx_devices_status ON devices(status);
CREATE INDEX idx_devices_created_by ON devices(created_by);  -- 新增：数据权限查询优化
CREATE INDEX idx_alarms_status ON alarms(status);
CREATE INDEX idx_alarms_created ON alarms(created_at);
CREATE INDEX idx_alarms_created_by ON alarms(created_by);  -- 新增：数据权限查询优化
CREATE INDEX idx_alarm_linkage_alarm ON alarm_linkage_logs(alarm_id);
CREATE INDEX idx_inspection_tasks_date ON inspection_tasks(task_date);
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id, created_at);
```

### 4.2.1 3.3 模块建表/升级说明

- 上表已按 3.3 实现结论补列（`devices.last_report_at`、`organizations.map_image_width/height`、`alarms` 的 `org_id/device_code/pending_since/silenced_*/reset_*/updated_at`）。
- 3.3 沿用 DEC-006：开发期通过 `Base.metadata.create_all()` 建表；`alembic/versions/` 仍为空，正式发布前需统一补 Alembic 基线（待办 P1-006）。
- **既有数据库升级**：`create_all` 不会给已存在的表补列，必须从 `backend/scripts/sql/3_3_alter.sql` 执行手工 ALTER；该脚本已随仓库维护，缺失时 3.3 服务启动即 500。

---

## 5. API 接口规范

### 5.1 认证相关

| 方法 | 路径 | 描述 | 请求体 |
|------|------|------|--------|
| POST | `/api/v1/auth/login` | 用户登录 | `{username, password}` |
| POST | `/api/v1/auth/refresh` | 刷新 Token | 无（`refresh_token` 通过 httpOnly Cookie 自动携带） |
| POST | `/api/v1/auth/logout` | 登出 | - |
| GET | `/api/v1/users/me` | 获取当前用户信息 | - |
| GET | `/api/v1/users/me/menus` | 获取当前用户菜单 | - |
| GET | `/api/v1/users/me/permissions` | 获取当前用户权限码 | - |

### 5.2 设备档案

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/devices` | 设备列表（分页+筛选） |
| POST | `/api/v1/devices` | 创建设备 |
| GET | `/api/v1/devices/{id}` | 设备详情 |
| PUT | `/api/v1/devices/{id}` | 更新设备 |
| DELETE | `/api/v1/devices/{id}` | 删除设备（逻辑删除） |
| POST | `/api/v1/devices/{id}/retire` | **新增**：设备退役操作 |
| POST | `/api/v1/devices/import` | 批量导入（multipart/form-data） |
| ~~GET~~ | ~~`/api/v1/devices/{id}/qrcode`~~ | ~~获取设备二维码~~ |
| GET | `/api/v1/devices/{id}/history` | 设备历史记录 |
| GET | `/api/v1/devices/{id}/trajectory` | **3.3 新增**：设备状态变化轨迹（单类别时序） |
| GET | `/api/v1/devices/{id}/trajectory/export` | **3.3 新增**：轨迹导出（xlsx/csv，≤1 万行） |

### 5.3 实时监控

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/monitor/dashboard` | 监控大屏统计数据 |
| GET | `/api/v1/monitor/alarms/recent` | 最近报警列表 |
| POST | `/api/v1/monitor/ws-ticket` | **3.3 新增**：申请 WebSocket 一次性 Ticket |
| POST | `/api/v1/monitor/report` | **3.3 新增**：设备状态/报警上报通道（模拟器/未来 MQTT 适配） |
| GET | `/api/v1/monitor/map` | **3.3 新增**：获取当前用户可见地图与设备点位 |
| GET | `/api/v1/monitor/map/devices` | **3.3 新增**：视口内设备点位懒加载 |
| WebSocket | `/ws/devices` | 设备状态实时推送（含断线重连补偿） |
| GET | `/api/v1/alarms` | 报警列表 |
| GET | `/api/v1/alarms/{id}` | **3.3 新增**：报警详情 |
| POST | `/api/v1/alarms/{id}/confirm` | 火警确认 |
| POST | `/api/v1/alarms/{id}/silence` | **新增**：报警消音 |
| POST | `/api/v1/alarms/{id}/reset` | **3.3 新增**：报警/设备复位 |
| POST | `/api/v1/organizations/{id}/map-image` | **3.3 新增**：上传/更新区域平面图 |
| DELETE | `/api/v1/organizations/{id}/map-image` | **3.3 新增**：删除区域平面图 |
| POST | `/api/v1/alarms/{id}/linkage/execute` | 手动执行联动 |

### 5.3.1 3.3 实现补充说明

**WebSocket 帧协议与认证**
- 浏览器 WebSocket 无法携带标准 `Authorization` 头，采用 **Ticket 方案**：客户端先调用 `POST /monitor/ws-ticket` 获取一次性 Ticket，连接时通过 query `?ticket=...` 交换；Ticket 在 Redis 中 TTL 60 秒，避免长期 Token 进入 access_log（DEC-010）。
- 帧格式统一为 `{id, type, ts, data}`，核心事件：`device_status`、`alarm_new`、`alarm_silenced`、`resync_required`、`pong`。`pong.id` 为空串，仅作心跳，不参与去重。
- 服务端使用 **Redis Stream + 每进程消费者组** 扇出：设备上报 → `XADD` → 各 uvicorn worker 的独立 consumer 读取并按用户 `org_id` 范围过滤后推送；断线重连时通过 `XRANGE` 补发最近 500 条，超出则回退 `resync_required`（DEC-009）。

**平面图继承规则（A-18）**
- `organizations.map_image_url` 挂在 `floor` 类型节点；`devices.org_id` 通常指向更细粒度的 `zone` 叶子节点。
- 前端取图时，从设备所在 `zone` 向上递归到根，取**最近持有 `map_image_url` 的祖先 floor 节点**的底图；后端 `/monitor/map` 接口已实现该继承逻辑。

**已确认的产品问题（OQ 默认结论）**
- OQ-1：`data_scope='self'` 在报警/实时监控场景降级为按设备归属区域过滤（等价 `dept`），否则自动上报报警无创建人导致 self 用户永远收不到推送。
- OQ-2：无 MQTT 回读时，复位必须显式勾选「已物理恢复」并写入审计字段 `reset_physical_restored`（DEC-011）。
- OQ-3：消防主管保留 `alarm:view` 与系统管理/档案权限；`alarm:silence/reset` 等处置权限默认赋予值班员/系统管理员，主管不自动继承写权限（与 3.1 矩阵一致）。
- OQ-4：消音分两层——REST `POST /alarms/{id}/silence` 留痕并广播 `alarm_silenced` 停止该条报警音频；全局静音为客户端 localStorage/内存态，不同浏览器标签不强制同步。
- OQ-5：3.3 定时任务（离线检测、Stream 裁剪）使用 FastAPI lifespan `asyncio` 后台任务；Celery 引入时点延至 3.6/3.9 前决策。
- OQ-6：WebSocket 认证采用 Ticket 方案（见上文）。
- OQ-7：3.4 起计划任务编号统一为 `模块-序号` 前缀；3.1/3.2/3.3 历史编号不回改。

### 5.4 联动预案

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/linkage-plans` | 预案列表 |
| POST | `/api/v1/linkage-plans` | 创建预案 |
| PUT | `/api/v1/linkage-plans/{id}` | 更新预案 |
| DELETE | `/api/v1/linkage-plans/{id}` | 删除预案 |
| POST | `/api/v1/linkage-plans/{id}/toggle` | 启用/停用预案 |
| POST | `/api/v1/linkage-plans/{id}/simulate` | **3.4 新增**：模拟触发（走完整联动链路，生成演练告警） |
| POST | `/api/v1/linkage-plans/execute` | **3.4 新增**：手动执行预案 |
| GET | `/api/v1/alarm-linkage-logs` | 联动日志列表（**独立域，非 `/linkage-plans/{id}/logs`**） |
| GET | `/api/v1/alarm-linkage-logs/{log_id}` | 联动日志详情 |
| GET | `/api/v1/alarm-linkage-logs/export` | 联动日志导出 |

### 5.5 应急处置

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/emergency/events` | 事件列表 |
| GET | `/api/v1/emergency/events/{event_id}` | 事件详情 |
| POST | `/api/v1/emergency/events/{event_id}/resolve` | 事件处置完成 |
| POST | `/api/v1/emergency/events/{event_id}/close` | **3.5 新增**：关闭事件（主管权限） |
| GET | `/api/v1/emergency/events/{event_id}/timelines` | 时间轴列表 |
| POST | `/api/v1/emergency/events/{event_id}/timelines` | 添加时间轴节点 |
| DELETE | `/api/v1/emergency/events/timelines/{node_id}` | 删除时间轴节点 |
| GET | `/api/v1/emergency/events/{event_id}/report` | 导出事件报告（**HTML 直出，非 PDF**） |

> **v2.1 更正**：v2.0 的路径全写成了 `/api/v1/emergency-events*`，实际前缀是
> **`/api/v1/emergency/events`**（`api/v1/__init__.py` 的 `prefix="/emergency/events"`）；
> `{id}/timeline` 实际为**复数** `timelines`；`close` 端点 v2.0 漏写。
> 通知中心另有独立域 `/api/v1/notifications`（列表 / `/{id}/read` / `read-all` / `unread-count`），
> v2.0 未收录。

### 5.6 巡检维保

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/inspection-plans` | 巡检计划 |
| POST | `/api/v1/inspection-plans` | 创建计划 |
| GET | `/api/v1/inspection-tasks` | 巡检任务（我的任务） |
| POST | `/api/v1/inspection-tasks/{id}/records` | 提交巡检记录 |
| GET | `/api/v1/repair-orders` | 维修工单列表 |
| POST | `/api/v1/repair-orders` | 创建工单 |
| PUT | `/api/v1/repair-orders/{id}/assign` | 派单 |
| PUT | `/api/v1/repair-orders/{id}/complete` | 完成维修 |

### 5.7 统计报表

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/statistics/device-status` | 设备状态分布 |
| GET | `/api/v1/statistics/alarm-trend` | 报警趋势 |
| GET | `/api/v1/statistics/fault-top10` | 故障 TOP10 |
| GET | `/api/v1/statistics/inspection-completion` | 巡检完成率 |
| POST | `/api/v1/reports/export` | 报表导出（异步） |
| GET | `/api/v1/reports/export/{task_id}/status` | 查询导出任务状态 |
| GET | `/api/v1/reports/export/{task_id}/download` | 下载导出文件 |

### 5.8 系统配置（新增）

**⚠️ v2.1：本节整节对应的实现不存在。** 以下四个端点**在代码中均未实现**，
`api/v1/__init__.py` 未注册任何 `config` 路由、`app/api/v1/` 下无对应模块文件。
保留于此仅为标明原始设计意图；状态见 §3.10（FR-054/055/056 全部「未实现」）。

| 方法 | 路径（**未实现**） | 描述 |
|------|------|------|
| ~~GET~~ | ~~`/api/v1/config/dictionary`~~ | ~~数据字典列表~~ |
| ~~PUT~~ | ~~`/api/v1/config/dictionary`~~ | ~~更新数据字典~~ |
| ~~GET~~ | ~~`/api/v1/config/notifications`~~ | ~~通知渠道配置~~ |
| ~~PUT~~ | ~~`/api/v1/config/notifications`~~ | ~~更新通知渠道配置~~ |

### 5.9 通用响应格式

```json
{
  "code": 200,
  "message": "success",
  "data": { },
  "timestamp": "2026-09-07T20:30:00+08:00"
}
```

**分页格式：**
```json
{
  "code": 200,
  "data": {
    "items": [],
    "total": 100,
    "page": 1,
    "page_size": 20,
    "total_pages": 5
  }
}
```

---

## 6. 安全设计

### 6.1 认证鉴权
- **JWT 双 Token**：Access Token（**1h**，原 2h 已缩短）+ Refresh Token（7 天），存储于 Redis 白名单。
- **密码安全**：bcrypt 算法，cost factor = 12。
- **接口鉴权**：FastAPI Dependency `get_current_user` 统一校验 Token 与权限。

### 6.2 数据安全
- **SQL 注入**：SQLAlchemy ORM + 参数化查询，禁止原生 SQL 拼接。
- **XSS 防护**：前端 Vue 模板自动转义。~~富文本使用 DOMPurify 过滤~~ ——
  **v2.1 删除**：`dompurify` 不是前端依赖，全仓无该调用；且系统**不存在富文本输入**，
  该条无落点。
- **敏感数据**：~~手机号、身份证号等敏感字段使用 AES-256-GCM 字段级加密~~
  —— **v2.1 删除**：全仓 grep 无任何 AES 加密实现。当前敏感字段仅靠数据库访问控制
  与接口层数据范围过滤保护。
- **文件上传**：限制类型（jpg/png/pdf）、大小 ≤ 10MB（`config.py:70` `MAX_UPLOAD_SIZE_MB`）。
  ~~MinIO 私有桶 + 预签名 URL~~ —— **v2.1 删除**：无 MinIO，文件落本地磁盘
  `backend/storage/`（见 §2.2）。⚠️ 本地磁盘**没有预签名 URL 的时效控制**，
  访问控制依赖应用层。

### 6.3 传输安全
- 全站 HTTPS（TLS 1.3）。
- API 响应头配置 CORS、X-Content-Type-Options、X-Frame-Options。

---

## 7. 非功能需求

| 类别 | 需求 | 指标 |
|------|------|------|
| **性能** | 页面首屏加载 | ≤ 2 秒 |
| | API 响应时间（P95） | ≤ 500ms |
| | 实时推送延迟 | ≤ 2 秒 |
| | 并发用户支持 | ≥ 200 同时在线 |
| **可用性** | 系统可用性 | ≥ 99.5% |
| | 数据库备份 | 每日全量 + 实时 WAL 归档 |
| **扩展性** | 设备容量 | 支持 10,000+ 设备 |
| | 水平扩展 | 无状态服务设计，支持多实例部署 |
| **兼容性** | 浏览器 | Chrome 100+ / Edge 100+ / Firefox 100+ |
| | 移动端 | iOS Safari 14+ / Android Chrome 90+ |

---

## 8. 开发计划（五阶段）

> **v2.1 补注**：下表新增「**实际状态**」列（截至 2026-09-19）。阶段划分与周期维持 v2.0 原样
> ——它是计划基线，不因实际进度而改写。判定依据是各阶段涵盖的 FR 的实现状态（§3 各表）。

| 阶段 | 周期 | 目标 | 核心功能 | 验收标准 | **实际状态（v2.1）** |
|------|------|------|----------|----------|---------------------|
| **第一阶段** | W1-W4 | 基础可用 | 用户权限 RBAC、组织架构、设备档案 CRUD、批量导入 | 三类角色登录见不同菜单；1000+ 设备导入成功 | ✅ **已达成**。FR-001~009、011、012 全部已交付；仅 FR-010 二维码未实现 |
| **第二阶段** | W5-W8 | 监控可用 | 设备模拟器、WebSocket 实时推送、电子地图、报警中心、历史查询 | 报警 3 秒内推送；地图正确展示点位 | ✅ **已达成**。FR-013~018、FR-016.1/016.2 全部已交付；WS 路径 `/ws/devices` 与心跳 30s 与 PRD 一致 |
| **第三阶段** | W9-W13 | 业务闭环 | 联动预案配置、自动/手动联动、火警确认流程、应急处置时间轴、事件归档 | 联动 5 秒内下发；误报/真实火警完整闭环 | ⚠️ **基本达成，闭环有缺口**。已交付 8 条 / 部分 9 条 / 未实现 1 条（FR-021 手动联动**前端零入口**）。**「联动 5 秒内下发」无超时控制**；**应急处置链路多处缺最后一跳**（FR-020.1 不推帧、FR-028 联动时间不自动记录、FR-029 无签到入口、FR-030 非 PDF 且缺三项内容） |
| **第四阶段** | W14-W17 | 运维可用 | 巡检计划、PC 端手动巡检记录、故障报修、维修工单、漏检统计 | PC 端手动巡检填报跑通；工单流转完整 | ⚠️ **基本达成**。已交付 3 条 / 部分 7 条。工单流转完整（含此前卡死缺陷已修）；但**「漏检超 3 次预警主管」未发送**、**任务「已完成」状态不可达**、**巡检拍照上传是假的**（`photos: []` 硬编码） |
| **第五阶段** | W18-W21 | 管理完善 | 消防演练（含数据隔离）、统计看板、报表导出（异步）、操作审计 | 看板 3 秒加载；10 万行数据 60 秒内导出 | ❌ **未完成**。已交付 2 条 / 部分 8 条 / **未实现 4 条**：**FR-053 操作审计整条未实现**（无写操作日志、无 JSON diff、无 180 天保留），**§3.10 整章（FR-054/055/056）未实现**。演练域七条全部部分交付（归档未实现、评估项未预设、无年度季度维度等） |

**进度判读**：前三阶段的主体功能都已落地，**第四、五阶段的"最后一公里"普遍未走完**。
典型形态见 §3.11.1——**后端齐备、前端零入口**与**链路接通但最后一跳没接**。

---

## 9. 风险与应对

| 风险 | 影响 | 应对措施 | **实际落实情况（v2.1）** |
|------|------|----------|-------------------------|
| 真实消防设备协议复杂 | 第二阶段延期 | 先以 Python 模拟器（`asyncio` 定时任务模拟设备上报）完成核心功能，协议对接并行 | ⚠️ 模拟器已交付（`scripts/device_simulator.py`），但**协议对接未开始**——当前接入是 HTTP `POST /monitor/report` + `X-Device-Key` 预共享密钥，**MQTT 无任何实现**（见 §3.11.3） |
| WebSocket 高并发连接 | 推送延迟 | ~~使用 Redis Pub/Sub 做多实例广播~~，连接数过多时启用负载均衡 | ⚠️ **实际用的是 Redis Stream 而非 Pub/Sub**（`ws:devices:stream` + consumer group，见 §2.3）。选型正确（Stream 才能做断线补发），但 PRD 措辞与实现不符 |
| 电子地图大量点位渲染 | 前端卡顿 | >500 点位启用聚合（MarkerCluster），按需加载可视区域设备 | ✅ 已落实：`leaflet.markercluster` 1.5.3 + 后端视口网格聚合（`monitor_service.py:356-404`），且上传图片 >2000px 自动压缩 |
| 报表导出大数据量 OOM | 服务崩溃 | ~~Celery 异步任务~~ + 流式写入 Excel，分批次查询数据库 | ⚠️ **实际用 FastAPI `BackgroundTasks`**（`reports.py:58-61`），非 Celery（与 §2.2 的技术选型一致）。且**导出数据由前端传当前页数组**，>1 万行分支在看板上几乎不可达；`_generate_excel` 非流式 |
| 演练数据污染真实统计 | 数据错误 | 全局 `is_drill` 字段隔离，统计 API 统一过滤 `is_drill = false` | ✅ 已落实，且落点比 PRD 设想的更多：统计（`statistics_service.py:114`）、大屏计数与最近报警（`monitor_service.py:122,175`）、应急升级扫描（`emergency_service.py:163`）、报警列表（`include_drill` 默认 False）、前端报警中心「含演练」开关。**这是本项目中执行得最彻底的一条隔离** |

---

## 10. 输入输出映射表

| 输入数据 | 系统处理 | 输出结果 | 对应功能点 |
| :--- | :--- | :--- | :--- |
| **设备档案** | 入库、地图坐标解析、状态计算 | **设备地图** | FR-015, FR-011 |
| **报警数据** | 规则匹配、WebSocket 推送、状态流转 | **报警记录** | FR-014, FR-016.1 |
| **联动预案** | 触发条件判断、指令下发、结果回调 | **联动执行** | FR-020, FR-020.1 |
| **巡检记录** | PC 端填报、照片上传、归档 | **巡检台账** | FR-034, FR-036 |
| **处置过程** | 时间轴聚合、附件关联、PDF 生成 | **处置报告** | FR-030 |

---

## 11. 待确认事项（Open Issues）

> **v2.1 重写**：v2.0 本节只有一条，且该条与实际不符（见下）。以下按「**需求是否仍成立**」
> 与「**已实现但口径待定**」两类整理，每条标明现状依据。

### 11.1 需求本身待澄清（是否还要做）

| # | 事项 | 现状 | 待定问题 |
|:-:|------|------|---------|
| 1 | ~~**硬件协议 MQTT**~~（v2.0 原条目称「已确定」） | **代码中无任何 MQTT 实现**，仅三处注释提到"后续 MQTT 适配层"。当前接入为 HTTP `POST /monitor/report` + `X-Device-Key` | 是否仍要接 MQTT？若接，是替换 HTTP 还是并存？v2.0 的"已确定"是**误述** |
| 2 | **§3.10 系统配置与运维**（FR-054 数据字典 / FR-055 日志清理 / FR-056 通知渠道） | **整章未实现**：无端点、无模型、无表。`docs/plan/3.10` 计划的"实现偏离"节为空，自述「待 3.10 开发完成后填写」 | 全章是否仍要做？其中 **FR-055 的措辞还绑定了 Celery**，与项目选型冲突，需一并改口径 |
| 3 | **FR-053 操作审计**（P0） | **未实现**：无审计模型、无端点，只有 `login_logs`（登录日志）。`3.9` 完成报告的 PRD 一致性表**刻意未含 FR-053** | P0 却未做——是降级、还是遗漏？另注：`3.10` 计划把 `audit_logs` 当作"3.9 计划新增"的前置依赖，但该表从未创建，**两份计划相互矛盾** |
| 4 | **FR-019 火灾类型分级**（A 类/B 类/C 类/电气） | 只实现 `fire`/`pre_fire` 两个取值；`schemas/linkage.py:18` 注释写了 `A/B/C/electrical` 但引擎按 `fire_type == alarm.alarm_type` 匹配 | A/B/C/电气是否仍要做？若不做，应把注释与 PRD 一并改掉，避免下一个读到"注释说支持"的人再踩 |
| 5 | **FR-020「联动 5 秒内下发」** | 无超时控制，仅注释写着 | 是否需要真正的超时降级（超时标记 failed 并触发 FR-020.1 次级告警）？ |
| 6 | **FR-030 事件报告 PDF** | 实际 HTML 直出，PDF 靠浏览器打印 | 是否必须真 PDF（服务端生成）？ |
| 7 | **FR-034 巡检拍照上传** | **是假的**：`photos: []` 硬编码、`action="#"`、去掉/预览为空实现 | 拍照是真需求还是占位？若为真，需接文件上传与存储 |
| 8 | **FR-044 演练与报警的关联** | `Alarm` **无 `drill_id` 外键**，`is_drill=True` 的告警与具体某场演练无关联 | 「演练期间产生的报警」需要能回溯到**哪一场**演练吗？若需要，要加外键 + 迁移 |

### 11.2 已实现但口径待定

| # | 事项 | 现状依据 |
|:-:|------|---------|
| 9 | **`linkage:log`（联动日志菜单）是否对值班员开放** | 2026-09-19 补值班员菜单码时**刻意只补了 `linkage:plan`**，未补 `linkage:log`——是否开放是产品口径。⚠️ 定口径时须连带看：**该页目前无任何数据范围过滤**（待办 P2-018），对更低权限角色开放会同时暴露"能看到全部组织的联动日志" |
| 10 | **文件存储是否改回对象存储** | 当前为容器本地磁盘，与 §7「无状态服务设计，支持多实例部署」冲突（多实例下导出文件不共享） |
| 11 | **应急处置 `resolve`/`close` 的状态机** | 当前**无状态机校验**：`closed` 可被覆盖回 `resolved`、`resolved` 可重复处置且 `complete` 节点无去重。前端按钮已做显示条件，但直接打 API 仍可绕过（待办 P1-014） |

### 11.3 明确决定「暂不做」的

| # | 事项 | 决定 |
|:-:|------|------|
| 12 | **FR-025 超时升级链路** | **2026-09-19 决定暂缓**（非遗漏）。链路当前完全不通（两个独立成因，见 §3.11.2）。当前无任何角色依赖它，故暂缓风险为零。两条成因已由 `tests/test_escalation_scan.py` 以 `xfail(strict=True)` 入册——**转绿会反过来报错**，届时重新评估 |
| 13 | **FR-037 离线巡检** | 已取消（v2.0 已标）——移动端巡检改为 PC 端手动记录，无需离线能力 |

---

*文档结束*
