---
   
  # Claude 开发进度归档协议和构建规范

  > 本文件只保留**协议定义**、**最近 3 条进度摘要**和**滚动待办池**。
  > 完整历史会话记录见 `.claude/sessions/*.md`，技术决策见 `.claude/decisions.md`。

  ---

  ## 构建规范
  所有 Dockerfile 必须内置大陆镜像源替换（sed 修改 sources.list / 配置 registry），确保无外部依赖即可构建。默认使用阿里云/清华源，多阶段构建每个阶段都要处理。

  ---

  ## 引用规范（执行任务前必读）

  - **生成测试用例前**：先读取 `./testing-guidelines.md`，
    遵循其中的设计方法、优先级定义、ID 命名体系和前后端代码模式。
    该文件另含「记录归属」表、第六节断言陷阱清单（9 条）与「完成判据」；**可复用的测试侧假设一律追加进该文件，
    不要只写在某一次的测试报告里**（P2-001 已于 2026-09-09 补齐）。
  - **开始业务模块开发前**：先读取 `.claude/decisions.md`。其中 DEC-004（业务表统一加 `created_by`）
    与 DEC-005（新页面须登记 `viewComponents` 映射表）对 3.2 及后续所有模块均有强制约束，
    违反会分别导致数据权限失效、菜单点击白屏。
  - **归档进度前**：遵循本文件上方的「归档触发条件」与「执行步骤」。
 
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

- **2026-09-09 22:21 归档（P1 收尾：登录日志审计 + Alembic 基线 + 3.3 性能压测）**：完成剩余全部 P1 项与相关 P2 项，共 20 个文件变更未提交。**P1-003** 新增 `GET /api/v1/login-logs`（分页 + 用户名/状态/时间范围筛选，权限码 `system:log:view`）、前端 `views/system/LoginLog.vue` 审计页、6 条后端守护用例；**P1-006** 生成 Alembic baseline 迁移 `54d02fd0cebb`，覆盖 11 张表及 JSONB/索引，本地 PostgreSQL 已 `stamp head`；**P1-007** 在设备详情/更新/退役/删除/历史/轨迹/导出接口叠加数据权限范围，越权返回 404，新增 6 条守护用例并移除 e2e 的 `xfail`；**P1-008** 新增 `backend/scripts/benchmark_3_3.py`，地图视口 1000/5000 点位 P95=121ms/268ms，WS 100 条/s 推送 P95=981ms/P99=1026ms，均通过验收线。**验证结果**：`pytest -q` 171 passed / 48 skipped，`npm run build` 成功。P2-004（`.claude/decisions.md` 与 `sessions/index.md` 纳入版本控制）与 P2-009（3.3 结论回写 PRD/ADR）同步收口。本次同时清理了用户级记忆索引中一条已废弃条目。会话文件见 `.claude/sessions/2026-09-09-2221.md`。

- **2026-09-09 05:45 归档（3.3 实时监控与电子地图：计划 → 实现 → 验证）**：先按 PRD v2.0 §3.3 产出 `docs/plan/3.3-实时监控与电子地图-开发计划.md`（一致性复查：A 类 18 / B 类 7 / C 类 8 / OQ 7，OQ 全部按建议默认落地），再实现 B-12~B-19 与 F-12~F-18。**验证结果全为实测，原始日志存 `docs/test/raw/*-3.3.*`：`pytest` 159 passed + 48 skipped（3.3 新增 39 条，8 个文件）、`vitest` 19 files / 106 passed（新增 18 条）、`npm run build` 退出码 0、`E2E_BASE_URL=... pytest tests/e2e` 47 passed + 1 xfailed（新增 `test_monitor_e2e.py` 16 条，两轮 19.78s / 17.30s 结果一致）**。里程碑 M1 帧延迟实测 `n=10 p50=0.081s p95=0.111s max=0.111s`（预算 P95 ≤ 2s、红线 3s）；会话清理后 `dashboard` 全 0、未收敛报警 0、`storage/map-images/` 空。**两个真实缺陷**：① e2e teardown 顺序错误使上报型报警永不收敛（必须「上报 normal → 复位 → 删设备」）；② `frontend/nginx.conf` 缺 `/static/` 反代且 `/ws` 未设长连接超时 → 底图与实时推送在浏览器侧**静默失效**（返回 `200 text/html`）。计划 §八 的镜像依赖告警再次复现（新增 `pillow` 未 build → `ModuleNotFoundError` 崩溃循环）。**新增端点**：`/monitor/{report,ws-ticket,dashboard,alarms/recent,map,map/devices}`、`/alarms*`（列表/详情/confirm/silence/reset）、`/organizations/{id}/map-image`（+DELETE）、`/devices/{id}/trajectory[/export]`、`/ws/devices`；`alarms` 表 + 4 权限码由 `create_all` 与 `scripts/sql/3_3_alter.sql` 双路径落地（旧库必须手工执行该 SQL，P1-006 未收口）。交付后回填计划第十五节「实现偏离」27 项、新建 `docs/test/3.3-...测试执行结果.md`（逐条结果 + 缺陷根因与守护用例映射 + 验收边界）、`testing-guidelines.md` 断言陷阱 9 → 14 条并补 E2E/前端约定。**2026-09-09 后续提交**：本次交付内容已随 `41e0b1c 3.3功能` 进入版本库；`.claude/` 仍被 `.gitignore` 排除，会话归档与 ADR 未随该提交入库（后由 P2-004 处理）。

- **2026-09-09 02:47 归档（3.2 E2E 固化为可重跑用例）**：首轮容器联调的 23 项检查 + 权限矩阵 + 数据范围差异，已沉淀为 `backend/tests/e2e/test_device_api_e2e.py`（25 个用例函数，权限矩阵参数化后共 32 项，标记 `pytest.mark.e2e`，已在 `backend/pytest.ini` 注册）。**结果：`E2E_BASE_URL=... pytest -m e2e` 31 passed + 1 xfailed，02:44 与 02:47 两次全量重跑一致；默认 `pytest` 仍 119 passed + 32 skipped，不依赖容器**。设计要点：随机编码前缀 `E2E-xxxxxx` + autouse fixture 会话末按前缀逻辑删除，可反复执行不污染开发库；服务不可达或种子账号缺失时 `skip` 而非 fail。沉淀过程修正 4 处用例侧错误假设（详情类「不存在」走统一响应体 `code`、HTTP 仍 200；`设备编码*`/`设备名称*` 同为导入必需列；扩展属性单元格须 JSON 文本；回滚阈值是失败率严格 >50%），**未发现新的生产缺陷**。测试报告已同步更新（新增 3.5 节，原「未沉淀为自动化用例」表述作废）。**03:03 追加文档分工**：新建根目录 `testing-guidelines.md`（P2-001 收口，收纳可复用测试假设与 9 条断言陷阱），并在 `docs/plan/3.2-...开发计划.md` 追加「十、实现偏离」小节（5 条，含原因与影响），使偏离记录落在随仓库入库的文件里而非仅存于 gitignore 的 `.claude/`。会话文件见 `.claude/sessions/2026-09-09-0247.md`。

> 更早摘要（2026-09-09 02:18 及之前）已移至 `.claude/sessions/index.md`。

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
| P0-016 | 前后端联调：设备档案全流程验收（收尾） | P0 | [ ] | 2026-09-09 | **部分完成（2026-09-09 02:18）**：主管账号「新增→编辑→导入→退役→历史」全流程与三类角色 401/403 抽样已在真实 PostgreSQL 容器验证通过。主管/值班员/维保 × 10 端点权限矩阵与 `all`/`dept`/`self` 可见量差异已实测通过，并已固化为 `pytest -m e2e` 自动化用例（02:47），后续无需再手工复核。**剩余**：计划要求的「1000+ 设备分页流畅」性能验证未做（导入实现已从计划的「每 100 行提交」改为全量单事务，见 `.claude/sessions/2026-09-09-0218.md` 计划偏离 5） |
| P2-002 | 清理 pytest warning | P2 | [ ] | 2026-09-09 | 3.2 时 121 条，**3.3 全量运行为 136 条**。来源均已定位：`tests/test_data_scope.py:16` 的 `TestDevice` 类名被 pytest 误采集（改名或加 `__test__ = False`）、httpx per-request cookies 弃用（conftest 改用 `ASGITransport`）、**Pydantic `class Config` 全仓库写法**（3.3 新 `schemas/alarm.py` 沿用同款，改造需连 3.1/3.2 一起换成 `model_config`）。注：3.2 归档的 `raw/pytest-v.txt` 无 warning 汇总段，两份日志不可直接对比 |
| P2-003 | PRD 3.3+ 后续模块排期 | P2 | [ ] | 2026-09-09 | **部分完成**：3.3 已完成计划编写 → 实现 → 验证全链路（`docs/plan/3.3-...md` + `docs/test/3.3-...测试执行结果.md`）。**剩余**：inspection / drill / linkage / statistics 等 3.4+ 模块仍是 12 行占位页，无计划文档。3.3 已为其预留：`alarms.pending_since`（FR-025 超时升级）、`alarms` 主键与状态机（3.5 闭环）、`echarts` 依赖（3.9 报表复用） |
| P2-005 | 部署前替换 JWT `SECRET_KEY` | P2 | [ ] | 2026-09-09 | `backend/app/core/config.py` 与 `backend/.env.example` 中均为占位值 `your-super-secret-key-change-in-production`，仓库内无实际 `.env`。当前 Token 可被伪造，**任何对外演示/公网部署前必须替换**。3.3 的 WS Ticket 与设备上报 `DEVICE_REPORT_KEY` 同属该密钥体系，一并换。**追加**：部署检查还需确认是否给 backend 显式加 `storage` 卷（当前靠 `./backend:/app` bind mount 覆盖，见计划偏离 15.1-1） |
| P2-006 | 软删除设备占用编码的提示语误导 | P2 | [ ] | 2026-09-09 | `device_code` 唯一性校验包含 `is_deleted` 行（设计正确，防约束冲突），但列表任何视图都看不到已删设备，新建/导入时报「设备编码已存在」会让用户无从排查。建议文案改为「设备编码已被已删除档案占用: XXX」并给出恢复入口 |
| P2-007 | 镜像依赖与 `requirements.txt` 漂移无校验 | P2 | [ ] | 2026-09-09 | 3.2 新增 `openpyxl`、**3.3 新增 `pillow`** 都踩过同一坑：bind-mount 的新代码在旧镜像里 `ModuleNotFoundError` → `fire_alarm_backend` 崩溃循环，须手动 `docker compose build backend`（3.3 同时需 build frontend 才让 `nginx.conf`/新页面生效）。建议 `entrypoint.sh` 启动前做一次依赖导入预检并给出明确提示 |
| P2-008 | 多 worker 部署下的 WS 推送未实测 | P2 | [ ] | 2026-09-09 | 计划 §八 要求的 `WORKERS` 环境变量与 storage 卷**均未落地**，`entrypoint.sh` 仍是单进程 uvicorn。每 worker 独立 consumer（name 含 hostname+pid+uuid）与 `XACK` 已实现，但 `WORKERS≥2` 下的重复推送/漏推、以及「权限快照需重连才生效」的多连接表现未验证。同时 WS 单连接内存清理（`/health` 的 `ws_connections` 指标，计划 §十一 风险项）也未实现 |
| P2-010 | 组织树无法自建 floor 节点，地图用例只能挂在根区域 | P2 | [ ] | 2026-09-09 | `api/v1/organizations.py` 只有查询与平面图上传/删除，**无创建/维护组织节点的端点**，预置树仅 1 个根、无 `floor` 类型节点；后端也不校验 `org_type`。因此计划 A-18 的「zone 设备向上递归继承祖先楼层底图」只能在 SQLite 单测验证，真实多级区域未在 e2e 展开。补齐后需回头加一条多级继承的容器级用例 |

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
