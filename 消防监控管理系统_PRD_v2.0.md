# 消防监控管理系统 — 产品需求文档（PRD）

| 项目 | 内容 |
|------|------|
| **文档版本** | v2.0（审核优化版） |
| **编写日期** | 2026-09-07 |
| **编写人** | 系统架构师 / 敏捷项目经理 |
| **技术栈** | 前端 Vue 3 + 后端 Python 3.10 + PostgreSQL |
| **交互方式** | RESTful API + WebSocket 实时推送 |
| **目标用户** | 消防值班员、维保人员、消防主管 |

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
│  │  FastAPI    │  │  WebSocket  │  │  Celery Worker      │   │
│  │  (REST API) │  │  (实时推送)  │  │  (异步任务)          │   │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘   │
│         └─────────────────┴────────────────────┘            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │ SQLAlchemy  │  │  JWT Auth   │  │  Pydantic Schema    │   │
│  │  (ORM 2.0)  │  │  (OAuth2)   │  │  (数据校验)          │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌──────────┐ ┌──────────────┐
│  PostgreSQL  │ │  Redis   │ │   MinIO      │
│  (主数据库)   │ │(缓存/会话)│ │  (文件存储)   │
│  版本: 15+   │ │ 版本: 7+ │ │              │
└──────────────┘ └──────────┘ └──────────────┘
```

### 2.2 消息可靠性设计（新增）

为确保 WebSocket 断线重连后报警消息不丢失，引入 **Redis Stream** 作为消息缓冲队列：

1. 后端收到设备上报 → 写入 Redis Stream。
2. WebSocket 服务从 Stream 读取 → 推送前端。
3. **断线重连补偿**：前端重连时携带 `last_msg_id`，后端从 Stream 中读取 `last_msg_id` 之后的消息进行补发，确保报警不丢失。

### 2.3 后端技术选型

| 组件 | 选型 | 版本 | 说明 |
|------|------|------|------|
| Web 框架 | FastAPI | 0.110+ | 异步支持、自动 OpenAPI 文档、高性能 |
| ORM | SQLAlchemy | 2.0+ | 声明式模型、Alembic 迁移 |
| 认证 | OAuth2 + JWT | PyJWT 2.8+ | Bearer Token，Access Token + Refresh Token |
| 数据校验 | Pydantic | v2 | 请求/响应模型校验 |
| 异步任务 | Celery | 5.3+ | 报表导出、定时巡检任务生成 |
| 消息代理 | Redis | 7.0+ | Celery Broker + 缓存 + WebSocket 状态存储 |
| 数据库驱动 | asyncpg | 0.29+ | PostgreSQL 异步驱动 |
| 文件存储 | MinIO SDK | 最新 | 巡检照片、演练视频、报表文件 |

### 2.4 前端技术选型

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

| 编号 | 功能 | 需求描述 | 优先级 |
|------|------|----------|--------|
| FR-001 | 用户登录 | 支持用户名+密码登录，密码 bcrypt 加密存储。登录成功后返回 JWT Access Token（有效期 **1h**）和 Refresh Token（有效期 7d）。 | P0 |
| FR-002 | 角色管理 | 内置 3 个角色：消防值班员、维保人员、消防主管。支持后台自定义角色。 | P0 |
| FR-003 | 菜单权限 | 每个角色绑定可访问的菜单列表。前端根据 `/api/v1/users/me/menus` 动态渲染侧边栏。 | P0 |
| FR-004 | 数据权限 | 数据范围控制：全部数据 / 本部门及子部门 / 仅本人。设备、报警、巡检等数据按用户数据范围过滤。 | P0 |
| FR-005 | Token 刷新 | Access Token 过期前自动调用 `/api/v1/auth/refresh` 换取新 Token，无感刷新。 | P0 |
| FR-006 | 登录安全 | 连续 5 次登录失败锁定账户 30 分钟；记录登录 IP、时间、设备信息。 | P1 |

**角色权限矩阵：**

| 功能模块 | 消防值班员 | 维保人员 | 消防主管 |
|----------|:----------:|:--------:|:--------:|
| 实时监控 | ✅ 查看/确认 | ❌ | ✅ 查看 |
| 报警中心 | ✅ 确认/处置 | ❌ | ✅ 查看 |
| 设备档案 | ✅ 查看 | ✅ 查看/维修记录 | ✅ 增删改查 |
| 联动预案 | ❌ | ❌ | ✅ 配置/执行 |
| 巡检任务 | ❌ | ✅ 执行/记录 | ✅ 计划/统计 |
| 消防演练 | ❌ | ❌ | ✅ 全流程 |
| 统计报表 | 部分 | 部分 | ✅ 全部 |
| 系统管理 | ❌ | ❌ | ✅ 用户/角色 |

---

### 3.2 消防设备档案（FR-007 ~ FR-012）

| 编号 | 功能 | 需求描述 | 优先级 |
|------|------|----------|--------|
| FR-007 | 设备类型 | 预置 8 种类型：烟感探测器、温感探测器、手动报警按钮、消火栓、喷淋头、排烟风机、防火门、应急照明。每种类型定义专属属性模板。 | P0 |
| FR-008 | 设备档案 CRUD | 设备编码（唯一）、名称、类型、厂商、型号、安装位置（区域关联）、安装日期、质保期、维护周期、平面图坐标（x, y）、状态。 | P0 |
| FR-009 | 批量导入 | 提供 Excel 模板下载，支持批量导入设备。校验：编码唯一、区域存在、类型有效。导入结果返回成功/失败明细。 | P0 |
| FR-010 | 二维码标签 | 每个设备生成唯一二维码（内容：`https://系统域名/device/{device_code}`），支持打印导出。扫码可查看设备详情。 | P1 |
| FR-011 | 设备历史 | 记录设备的状态变更历史、报警历史、维修历史、巡检历史。 | P1 |
| FR-012 | 设备搜索 | 支持按编码、名称、类型、区域、状态组合筛选；支持分页（默认 20 条/页）。 | P0 |

**设备状态枚举：** `normal`（正常）、`alarm`（报警）、`fault`（故障）、`shield`（屏蔽）、`offline`（离线）、**`retired`（已退役）**（新增）

**设备退役流程（新增）：**
- 删除"物理删除"按钮，改为"退役"操作。
- 点击退役后，设备状态变更为 `retired`，前端列表默认过滤该状态设备（需勾选"显示已退役"才可见）。
- 该设备关联的历史报警、巡检记录**必须保留**，不可级联删除。

---

### 3.3 实时监控与电子地图（FR-013 ~ FR-018）

| 编号 | 功能 | 需求描述 | 优先级 |
|------|------|----------|--------|
| FR-013 | 实时状态推送 | 设备状态变化通过 WebSocket 推送至前端。连接地址：`/ws/devices`。心跳间隔 30 秒。 | P0 |
| FR-014 | 监控大屏 | 总览面板：设备总数、在线数、报警数、故障数。报警列表按时间倒序，**未确认火警强制置顶**，新报警**红色呼吸灯/左右滑入动画**效果，直至被确认。 | P0 |
| FR-015 | 电子地图 | 支持上传楼层平面图（PNG/JPG/PDF 转 PNG）。设备以图标形式叠加，按状态着色。支持缩放、拖拽、点击弹详情。 | P0 |
| FR-016 | 报警声光提示 | 新报警触发浏览器 Notification + 页面内音频告警（可手动静音/取消）。 | P0 |
| FR-017 | 报警分级 | 火警（红色）、预警（橙色）、故障（黄色）、屏蔽（灰色）。不同级别不同提示音。 | P1 |
| FR-018 | 历史轨迹 | 查询单个设备指定时间范围内的状态变化轨迹，支持导出。 | P1 |

**电子地图性能优化（新增）：**
- 前端上传平面图时，若图片宽度 > 2000px，自动调用后端接口进行压缩（质量 0.8）或切片处理。
- 地图初始化时，仅加载当前视口（Viewport）内的设备图标；缩放或拖拽时，动态请求可视区域内的设备数据（懒加载）。

**报警消音与复位（新增 FR-016.1 ~ FR-016.2）：**

| 编号 | 功能 | 需求描述 | 优先级 |
|------|------|----------|--------|
| FR-016.1 | 报警消音 | 点击"消音"后，前端停止播放报警音频，浏览器通知栏消除闪烁，但报警列表中的记录状态保持不变（仍为待确认/已确认）。 | P0 |
| FR-016.2 | 报警复位 | 仅当设备物理状态恢复正常后，值班员可点击"系统复位"，清除界面上的故障/火警标识，使设备状态回滚至"正常"。 | P0 |

---

### 3.4 报警联动（FR-019 ~ FR-024）

| 编号 | 功能 | 需求描述 | 优先级 |
|------|------|----------|--------|
| FR-019 | 联动预案配置 | 按"区域 + 火灾类型（A类/B类/C类/电气）"配置联动规则。规则包含：触发条件（设备类型+报警类型）→ 动作列表（启动排烟/关闭防火门/启动应急照明/疏散广播）。 | P0 |
| FR-020 | 自动联动 | 报警触发后，联动引擎 5 秒内自动下发所有关联动作指令。每条指令记录执行状态：pending → sent → acked → success / failed。 | P0 |
| FR-021 | 手动联动 | 值班员或主管可在监控页面手动选择预案并执行。需二次确认弹窗。 | P0 |
| FR-022 | 联动日志 | 记录每次联动的触发源、触发时间、执行动作、执行结果、耗时。支持按时间/区域/预案筛选。 | P0 |
| FR-023 | 预案启用/停用 | 预案可设置启用状态，停用后不参与自动联动。 | P1 |
| FR-024 | 联动模拟 | 支持模拟触发（不操作真实设备），用于测试预案逻辑。 | P2 |

**联动失败处理机制（新增 FR-020.1）：**

| 编号 | 功能 | 需求描述 | 优先级 |
|------|------|----------|--------|
| FR-020.1 | 联动失败处理 | 若指令执行状态变为 `failed`（如设备离线、响应超时），系统需立即在"报警中心"生成一条**次级告警**（级别：严重），并弹窗提示值班员"联动设备执行失败，请人工介入"。 | P0 |

---

### 3.5 火警确认与应急处置（FR-025 ~ FR-031）

| 编号 | 功能 | 需求描述 | 优先级 |
|------|------|----------|--------|
| FR-025 | 火警确认流程 | 报警产生后状态为"待确认"。值班员需在 5 分钟内现场确认或视频复核。**超时（5分钟）未确认自动升级通知主管**，通知方式：① 系统内通知（前端右上角红点）。 | P0 |
| FR-026 | 误报处理 | 确认为误报时，必须选择/填写误报原因（设备故障/环境因素/人为误触/其他），记录确认人、确认时间。 | P0 |
| FR-027 | 真实火警处置 | 确认真实火警后，自动启动应急处置流程：生成应急事件 → 记录处置时间轴 → 参与人员签到。 | P0 |
| FR-028 | 处置时间轴 | 以时间轴形式记录处置关键节点：报警时间 / 确认时间 / 联动启动时间 / 人员疏散时间 / 火情控制时间 / 处置完成时间。 | P0 |
| FR-029 | 人员签到 | 应急处置过程中，相关人员可通过系统签到（记录时间、GPS 位置可选）。 | P1 |
| FR-030 | 事件归档 | 事件结束后生成完整事件报告，包含：报警信息、联动记录、确认记录、处置时间轴、参与人员、现场照片。支持 PDF 导出。 | P0 |
| FR-031 | 事件状态机 | `pending` → `confirmed` / `false_alarm` → `processing` → `resolved` / `closed` | P0 |

---

### 3.6 设备巡检（FR-032 ~ FR-037）

| 编号 | 功能 | 需求描述 | 优先级 |
|------|------|----------|--------|
| FR-032 | 巡检计划 | 按设备类型/区域/责任人制定周期计划：每日/每周/每月/每季度/每年。支持设置执行时间段。 | P0 |
| FR-033 | 任务生成 | 每日凌晨 Celery 定时任务自动生成当日巡检任务。任务状态：待执行 / 执行中 / 已完成 / 漏检。 | P0 |
| FR-034 | ~~移动端巡检~~ → **PC 端手动巡检** | ~~维保人员通过手机扫码设备二维码进入巡检页面。~~ 维保人员在 PC 端「巡检任务」列表中选择当日任务，点击设备名称进入巡检填报页面。填写巡检项结果（正常/异常），异常可拍照上传、填写备注。 | P0 |
| FR-035 | 漏检统计 | 自动统计漏检任务，生成漏检报告。漏检超过 3 次触发预警通知主管。 | P1 |
| FR-036 | 巡检记录 | 所有巡检记录归档，支持按设备/人员/时间筛选查询。 | P0 |
| ~~FR-037~~ | ~~离线巡检~~ | ~~移动端支持离线缓存巡检数据，网络恢复后自动同步。冲突时以服务端接收时间为准，但需校验设备状态版本号，防止覆盖最新维修记录。~~ | ~~P2~~ | **已取消**：移动端巡检改为 PC 端手动记录，无需离线能力。 |

---

### 3.7 故障维修（FR-038 ~ FR-042）

| 编号 | 功能 | 需求描述 | 优先级 |
|------|------|----------|--------|
| FR-038 | 故障报修 | 巡检发现故障或监控发现故障时，自动生成报修工单。工单关联设备与故障描述。 | P0 |
| FR-039 | 工单流转 | 状态流：`待处理` → `已派单` → `维修中` → `待验收` → `已完成`。支持退回。 | P0 |
| FR-040 | 维修记录 | 记录维修过程、更换配件、维修人员、维修时间、维修结果。维修完成后设备状态自动恢复"正常"。 | P0 |
| FR-041 | 维修验收 | 工单完成后需验收人确认。验收不通过退回重新维修。 | P1 |
| FR-042 | 维修统计 | 统计平均维修时长、故障类型分布、维修人员工作量。 | P1 |

---

### 3.8 消防演练（FR-043 ~ FR-047）

| 编号 | 功能 | 需求描述 | 优先级 |
|------|------|----------|--------|
| FR-043 | 演练计划 | 制定年度/季度演练计划：演练时间、地点、类型（疏散/灭火/综合）、参与部门/人员。 | P1 |
| FR-044 | 演练执行 | 演练当天记录实际执行过程：时间节点、现场照片/视频、模拟报警触发记录。 | P1 |
| FR-045 | 演练数据隔离 | 演练期间产生的报警、联动标记为 `drill=true`，不参与真实业务统计，演练结束后可归档或清理。 | P0 |
| FR-046 | 演练评估 | 按预设评估项打分（响应时间/疏散效率/设备联动/人员配合），记录问题与改进措施。 | P1 |
| FR-047 | 演练报告 | 生成演练评估报告，支持 PDF/Word 导出。 | P1 |

---

### 3.9 统计报表（FR-048 ~ FR-053）

| 编号 | 功能 | 需求描述 | 优先级 |
|------|------|----------|--------|
| FR-048 | 设备完好率看板 | 饼图展示正常/报警/故障/屏蔽设备占比。支持按区域下钻。 | P0 |
| FR-049 | 报警趋势图 | 折线图展示近 7 天/30 天/90 天报警数量趋势，按报警类型分组。 | P0 |
| FR-050 | 故障 TOP10 | 柱状图展示故障次数最多的前 10 个设备，支持点击跳转详情。 | P1 |
| FR-051 | 巡检完成率 | 统计各责任人/区域的巡检完成率、漏检率。 | P1 |
| FR-052 | 报表导出 | 所有统计看板支持导出 Excel/CSV。大数据量（>1万行）走异步任务，完成后消息通知下载。 | P0 |
| FR-053 | 操作审计 | 记录所有写操作日志：操作人、IP、时间、模块、操作类型、变更内容（JSON diff）。保留 180 天。 | P0 |

---

### 3.10 系统配置与运维（新增章节，FR-054 ~ FR-056）

| 编号 | 功能 | 需求描述 | 优先级 |
|------|------|----------|--------|
| FR-054 | 数据字典管理 | 支持管理员动态配置设备类型、报警级别、故障原因等枚举值。前端下拉框根据字典接口动态渲染，无需发版即可新增类型。 | P1 |
| FR-055 | 日志自动清理 | 配置定时任务（Celery Beat），每日凌晨清理超过 180 天的操作审计日志和 WebSocket 历史消息，释放数据库空间。 | P1 |
| FR-056 | 通知渠道配置 | 集成邮件服务配置。在"超时未确认"或"联动失败"场景下，支持配置是否发送邮件给主管。 | P2 |

---

## 4. 数据模型设计

### 4.1 核心 ER 关系

```
User (用户) ───< UserRole >─── Role (角色) ───< RolePermission >─── Permission (权限)
 │
 └── Organization (组织架构) ───< Floor >─── Zone (区域) ───< Device (设备)
                                              │
                                              ├── DeviceStatusLog (状态日志)
                                              ├── Alarm (报警) ───< AlarmLinkageLog (联动日志)
                                              │                    │
                                              │                    └── LinkagePlan (联动预案)
                                              ├── InspectionTask (巡检任务) ─── InspectionRecord (巡检记录)
                                              ├── RepairOrder (维修工单)
                                              └── DrillEvent (演练事件) ─── DrillEvaluation (演练评估)
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

-- 4. 报警与联动
CREATE TABLE alarms (
    id BIGSERIAL PRIMARY KEY,
    device_id BIGINT REFERENCES devices(id),
    alarm_type VARCHAR(20) NOT NULL,  -- fire / pre_fire / fault / shield
    alarm_level VARCHAR(20),  -- critical / major / minor
    status VARCHAR(20) DEFAULT 'pending',  -- pending / confirmed / false_alarm / processing / resolved
    confirmed_by BIGINT REFERENCES users(id),
    confirmed_at TIMESTAMPTZ,
    confirm_result VARCHAR(20),  -- real / false_alarm
    false_reason TEXT,
    location_description VARCHAR(255),
    is_drill BOOLEAN DEFAULT FALSE,
    created_by BIGINT REFERENCES users(id),  -- 新增：数据权限 'self' 范围依赖
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

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

### 5.3 实时监控

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/monitor/dashboard` | 监控大屏统计数据 |
| GET | `/api/v1/monitor/alarms/recent` | 最近报警列表 |
| WebSocket | `/ws/devices` | 设备状态实时推送（含断线重连补偿） |
| GET | `/api/v1/alarms` | 报警列表 |
| POST | `/api/v1/alarms/{id}/confirm` | 火警确认 |
| POST | `/api/v1/alarms/{id}/silence` | **新增**：报警消音 |
| POST | `/api/v1/alarms/{id}/linkage/execute` | 手动执行联动 |

### 5.4 联动预案

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/linkage-plans` | 预案列表 |
| POST | `/api/v1/linkage-plans` | 创建预案 |
| PUT | `/api/v1/linkage-plans/{id}` | 更新预案 |
| DELETE | `/api/v1/linkage-plans/{id}` | 删除预案 |
| POST | `/api/v1/linkage-plans/{id}/toggle` | 启用/停用预案 |
| GET | `/api/v1/linkage-plans/{id}/logs` | 预案执行日志 |

### 5.5 应急处置

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/emergency-events` | 事件列表 |
| GET | `/api/v1/emergency-events/{id}` | 事件详情 |
| POST | `/api/v1/emergency-events/{id}/resolve` | 事件处置完成 |
| POST | `/api/v1/emergency-events/{id}/timeline` | 添加时间轴节点 |
| GET | `/api/v1/emergency-events/{id}/report` | 导出事件报告 |

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

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/config/dictionary` | 数据字典列表 |
| PUT | `/api/v1/config/dictionary` | 更新数据字典 |
| GET | `/api/v1/config/notifications` | 通知渠道配置 |
| PUT | `/api/v1/config/notifications` | 更新通知渠道配置 |

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
- **XSS 防护**：前端 Vue 模板自动转义，富文本使用 DOMPurify 过滤。
- **敏感数据**：手机号、身份证号等敏感字段在数据库层使用 **AES-256-GCM 加密**存储（字段级加密）。
- **文件上传**：限制类型（jpg/png/pdf），大小 ≤ 10MB，MinIO 私有桶 + 预签名 URL。

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

| 阶段 | 周期 | 目标 | 核心功能 | 验收标准 |
|------|------|------|----------|----------|
| **第一阶段** | W1-W4 | 基础可用 | 用户权限 RBAC、组织架构、设备档案 CRUD、批量导入 | 三类角色登录见不同菜单；1000+ 设备导入成功 |
| **第二阶段** | W5-W8 | 监控可用 | 设备模拟器、WebSocket 实时推送、电子地图、报警中心、历史查询 | 报警 3 秒内推送；地图正确展示点位 |
| **第三阶段** | W9-W13 | 业务闭环 | 联动预案配置、自动/手动联动、火警确认流程、应急处置时间轴、事件归档 | 联动 5 秒内下发；误报/真实火警完整闭环 |
| **第四阶段** | W14-W17 | 运维可用 | 巡检计划、PC 端手动巡检记录、故障报修、维修工单、漏检统计 | PC 端手动巡检填报跑通；工单流转完整 |
| **第五阶段** | W18-W21 | 管理完善 | 消防演练（含数据隔离）、统计看板、报表导出（异步）、操作审计 | 看板 3 秒加载；10 万行数据 60 秒内导出 |

---

## 9. 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 真实消防设备协议复杂 | 第二阶段延期 | 先以 Python 模拟器（`asyncio` 定时任务模拟设备上报）完成核心功能，协议对接并行 |
| WebSocket 高并发连接 | 推送延迟 | 使用 Redis Pub/Sub 做多实例广播，连接数过多时启用负载均衡 |
| 电子地图大量点位渲染 | 前端卡顿 | >500 点位启用聚合（MarkerCluster），按需加载可视区域设备 |
| 报表导出大数据量 OOM | 服务崩溃 | Celery 异步任务 + 流式写入 Excel，分批次查询数据库 |
| 演练数据污染真实统计 | 数据错误 | 全局 `is_drill` 字段隔离，统计 API 统一过滤 `is_drill = false` |

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

1. **硬件协议**：消防主机协议确定为 MQTT，其他协议暂时不做兼容。

---

*文档结束*
