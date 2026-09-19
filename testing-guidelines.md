# 测试规范（testing-guidelines）

> `CLAUDE.md`「引用规范」要求生成测试用例前先读本文件。此前该文件缺失（待办 P2-001），
> 本版本由 3.2 消防设备档案交付过程沉淀而来：条目均为**仓库里已核实的事实**，不是设想中的理想规范。
> 后续模块（3.3 起）在此基础上追加，不要另起一份。

---

## 一、记录归属（这类信息写在哪）

| 内容 | 载体 | 说明 |
|------|------|------|
| 逐条执行结果、缺陷根因 + 对应守护用例、未覆盖项 / 验收边界 | `docs/test/3.x-<模块>-测试执行结果.md` | 证据层，绑定某一次交付的时间点，不抽走、不为去重而删薄 |
| 可复用的测试侧假设与陷阱 | 本文件 | 「下次写测试别再踩」的内容属于规范，不属于报告 |
| 实现与计划不一致 | 对应 `docs/plan/3.x-...md` 末尾「实现偏离」小节 | 读计划的人第一眼就该看到；`.claude/` 被 gitignore，不能作为唯一载体 |
| 尚未收口的动作项 | `CLAUDE.md` 滚动待办池 | 文档中凡已有 P-x 编号的条目**引用编号即可**，不整段抄写 |
| 跨会话架构决策（DEC-xxx） | `.claude/decisions.md` | 迁往 `docs/adr/` 属待办 P2-004 的决策，勿提前拆分 |

## 二、ID 与命名体系

- **任务号**：`B-<n>` 后端 / `F-<n>` 前端，跨模块连续编号（3.3 起为 B-12 / F-12）。测试文件与计划文档的任务编号须对得上。
- **待办号**：`P0-` / `P1-` / `P2-` + 三位序号，只在 `CLAUDE.md` 池内分配与流转。
- **后端用例**：文件 `backend/tests/test_<模块>_<主题>.py`（如 `test_device_import.py`），函数 `test_<行为>[_<条件>]`，
  函数体第一行是**中文 docstring，说明这条用例断言什么**（测试报告的用例说明直接由它生成）。
- **前端用例**：`src/<层>/__tests__/<名称>.spec.js`，`describe('<组件名> <职责>')` + `it('<用户可见结果>')`。
- **端到端用例**：`backend/tests/e2e/test_<域>_e2e.py`，标记 `pytest.mark.e2e`。

## 三、后端单元测试约定

- 运行环境：宿主机 Python 3.10.10 + pytest 8.1.1 + pytest-asyncio 0.23.8（`asyncio_mode = auto`）。
  **不进入容器执行**（`docker exec` 受权限策略限制）。
- 数据库：SQLite `aiosqlite` 内存库 + `Base.metadata.create_all`（DEC-006，开发期不引入 Alembic）。
  跨库 JSON 一律用 `app/models/types.py` 的 `JSONB().with_variant(JSON(), "sqlite")`，不要直接写 `JSONB`。
- 复用 `tests/conftest.py` 的夹具：`db_engine` / `db_session` / `fake_redis` / `client` / `test_user` / `test_client_with_user`；
  `client` 走 ASGI 进程内调用，不开真实端口。
- 域内构造器放 `tests/<域>_helpers.py`（例：`device_helpers.py` 的 `create_org` / `create_device_type` / `create_device_user` / `auth_headers` / `device_payload`）。
  **不要在用例里手写 `User(...)`、`Device(...)` 字面量**，字段一多必然与模型漂移。
- 断言统一走响应信封 `code` / `message` / `data`，而不是只看 HTTP 状态（见第六节第 1 条）。
- 全量运行不得新增 warning；现存 121 条 warning 的清理是待办 P2-002，不要顺手扩大范围。

## 四、端到端（E2E）回归约定

```bash
docker compose up -d
cd backend && E2E_BASE_URL=http://localhost:8000/api/v1 python -m pytest -m e2e -v
```

- 标记 `e2e`（已在 `backend/pytest.ini` 注册）。**未设置 `E2E_BASE_URL` 时整个模块 `skip`**，保证默认 `python -m pytest` 不依赖容器。
- 降级优先于失败：服务不可达、种子账号缺失一律 `pytest.skip` 并提示执行 `backend/scripts/init_data.py`，
  不得让无环境的环境变红。
- 数据自清理：本轮数据编码带随机前缀（如 `E2E-<uuid6>`），由**会话级 autouse fixture** 在结束时按前缀清理；
  每条用例再带子标签（`-FLT` / `-HIS` / `-RB`）避免关键词互相串扰。
- 状态变更类用例（退役 / 删除 / 越权写）用**函数级**夹具，不复用会话级对象。
- 已知缺口用 `@pytest.mark.xfail(strict=False)` 挂**期望行为**作为探针，并在待办池登记编号；
  **禁止写「断言当前错误行为」的用例**把缺口固化成绿色基线。
- 依赖 `init_data.py` 的幂等预置数据（DEC-007）。E2E 不得自行改种子数据。
- **共享骨架放在 `tests/e2e/conftest.py` + `tests/e2e/common.py`**（`Api` 封装、`login(client, role)`、`device_payload`、
  `make_device`、`make_alarm`、会话级清理）。跨模块复制一份夹具必然漂移——3.3 已把 3.2 的重复代码合并进去，合并后结果不变。
- **涉及设备上报通道时，`.env.docker` 必须显式给出前置**并在模块 docstring 写明：`ALLOW_DEVICE_REPORT=true`、
  `DEVICE_REPORT_KEY=...`、`OFFLINE_SCAN_ENABLED=false`。心跳扫描会在用例之间把设备刷成 `offline`，统计卡片断言因此不稳定。
- **清理顺序对上报型报警是硬约束：「上报回 normal → 复位 → 删设备」**。复位要求设备物理状态已恢复，
  而设备一旦软删，用于正常化的上报就会 404，报警永远无法收敛（3.3 首轮实测 20 条复位失败）。
- 需要验证真实反代行为时用 `E2E_PUBLIC_URL`（默认 `http://localhost`），不可达时 skip；WS 客户端库缺失用
  `pytest.importorskip("websockets")` 兜底，不要让没装依赖的环境变红。
- 每轮结果需**连续跑两次**确认可重复，并把 `-v` 原始日志存档到 `docs/test/raw/`。

## 五、前端单元测试约定

- vitest 1.6.1 + jsdom + Vue Test Utils，`npm run build` 必须与测试同时通过。
- **`vite.config.js` 必须 `test.server.deps.inline: ['element-plus']`**（DEC-008）。否则 Node 直接加载 element-plus 的 ESM 产物时
  async-validator 的 CJS 互操作失效，**所有 `el-form` 校验在测试中静默恒为通过**，必填拦截用例全部假绿。
- 弹层 / 下拉断言用内联 `overlayStub`，不要用 `stubs: { teleport: true }`（会把内容整体搬离断言范围）。
- 异步校验器（如设备编码唯一性）要覆盖**服务异常路径**：不能因接口不可用而永久阻塞提交，最终裁决交给后端。
- 权限相关 UI 断言 `v-permission` 的默认 CSS 隐藏行为（DEC-003），不要断言 DOM 是否移除。
- 视图用例统一复用 `src/views/device/__tests__/mount.js` 的 `mountOptions()`（内部同时装 pinia 与 `createTestRouter()`）、
  `overlayStub()`、`findButton()`、`visibleButtonTexts()`。含 `el-tabs` / 路由跳转的页面**没有 router 会挂载即抛错**；
  纯 store 用例则需 `setActivePinia(createPinia())`（见 `stores/__tests__/monitor.spec.js`）。
- 大屏 / 地图 / 报警中心共用一条 WS，连接生命周期由 `stores/monitor.js` 的 `acquire()/release()` 引用计数决定；
  组件测试不要各自建连，改为断言 store 的调用。

## 六、断言陷阱清单（均已在本仓库实测）

1. **业务「不存在」走统一响应体 `code=404`，HTTP 仍是 200**。3.2 时这只是 `api/v1/devices.py` 返回 dict 的局部行为，
   3.3 已在 `app/main.py` 注册全局 `NotFoundError` 处理器（`app/core/exceptions.py`），因此**全仓库口径统一**；
   断言 `status_code == 404` 会永远失败。例外是 `StaticFiles` 自己返回的**真实 HTTP 404**（如删除平面图后再取 `/static/maps/*`）。
   参数校验类错误则由异常处理器返回真实 HTTP 400。
2. **权限拦截**：无 Token → 401；有 Token 缺权限点 → 403 且 `message` 含「缺少权限: <code>」。
3. **导入的必需列只有 `设备编码*` 与 `设备名称*`**，其余 14 列缺失不报错、按空值处理。
   用这两列构造「缺列」用例实际得到的是合法文件。缺列报 400 `Excel 缺少必需列: ...`。
4. **openpyxl 单元格不能写 dict**：Excel 导入用例的「扩展属性(JSON)」列必须先 `json.dumps(..., ensure_ascii=False)`。
5. **导入回滚阈值是失败率严格 `> 50%`**（`device_import_service.ROLLBACK_FAILURE_RATE`）：
   恰好 50% 不回滚；3 行 2 失败（66%）会连带合法行一起回滚。验证「部分失败仍入库」需把失败率控制在 ≤50%。
6. **软删除设备仍占用 `device_code`**（唯一性校验含 `is_deleted` 行），且列表任何视图都看不到它
   → 用例前缀不要跨轮次复用，否则撞码（提示语问题见待办 P2-006）。
7. **Numeric 精度**：坐标断言用 `340.25` 这类多位小数，`340.2` 检不出精度丢失。
8. **`self` 数据范围：锚点由各域自定，`created_by` 不是唯一锚点。**
    本条原为「`created_by` 是 `self` 范围的**唯一锚点**（DEC-004）」——**该说法已于 2026-09-14 更正，是错的**。
    DEC-004 只规定业务表**要有** `created_by` 字段，并没有规定它是唯一锚点。
    按 `created_by` 过滤只对「记录归属于录入人」的表成立；对**组织资产**不成立，
    而误用的后果是**静默的 0**（接口返回 `code 200 / message success`，页面一张空表）：

    | 域 | `self` 锚在哪 | 位置 |
    |----|---------------|------|
    | 设备 | **降级为 `dept`**（设备无个人归属字段可锚） | `device_service.apply_device_data_scope`（DEC-021） |
    | 巡检任务 | `responsible_user_id`（责任人，不是录入人） | `inspection_service.apply_task_data_scope` |
    | 维修工单 | 报修/维修/验收/创建 四字段 OR | `repair_service.repair_scope_condition` |
    | 报警/监控 | **降级为 `dept`**（自动上报的报警没有 `created_by`） | `monitor_service.resolve_visible_org_ids`（DEC-012） |

    另：`user_service.apply_data_scope`（通用版，`self` 锚 `created_by`）截至 2026-09-14
    **生产代码中已无调用方**（`app/` 零调用，只剩 10 处直接单测它自身的用例）。它还有个 `hasattr` 守卫——模型缺 `created_by` / `org_id` 时
    **静默返回原查询（不过滤）**，多一层间接调用就几乎看不出来。新域不要拿它当默认选项。
    **写用例时**：不要去断言「`self` 用户只看到自己创建的 X」，除非该域确实锚 `created_by`；
    先看该域的 `apply_*_data_scope` 把 `self` 锚在哪，再照那个锚点构造前提。
9. 数据范围目前**只作用于列表接口**，按 ID 的详情 / 历史 / 写接口未叠加，越权读取缺口见待办 P1-007（勿在测试中固化）。
10. **WS 握手鉴权失败分两层可观测**：ASGI 层（`TestClient`）能看到 accept 前的 `close(4401)`；
    真实 uvicorn 把它转成**握手 HTTP 403**（`websockets.InvalidStatus`），浏览器侧只有 `onclose(1006)`。
    端到端断言写 `"403" in str(exc)`，不要指望拿到 4401。
11. **新建的 WS 连接会先收到上一用例在途的帧**（扇出是异步广播）。用「按 `type` 循环等待目标帧」的辅助函数，
    不要 `recv()` 一次就断言类型。
12. **单次设备上报产生两帧，顺序固定为 `device_status → alarm_new`**；只关心报警的用例必须能跳过前一条。
    消音重复调用**不广播**（幂等），断言「没有第二条 `alarm_silenced`」是正确期望。
13. **`pong` 帧的 `id` 是空串**（服务端主动心跳与客户端 ping 应答都不来自 Stream）。
    前端 `last_msg_id` 只能由带真实 Stream entry id 的业务帧推进，用 `pong.id` 会把断点写坏。
14. **HTTP 422 的响应体是 FastAPI 默认 `{"detail":[...]}`，不是统一信封**（仓库无 `RequestValidationError` 处理器），
    实测：`format=pdf` → `{"detail":[{"type":"string_pattern_mismatch",...}]}`。
    前端拦截器与测试都不能按 `body.code` 读它。四类口径要分清：权限 403 / 业务前置与状态机 400 / 字段校验 422 / 资源不存在 200+`code=404`。
15. **HTTP 状态码与信封 `code` 是两件事，信封成功值恒为 200**。
    `docs/plan/API_RESPONSE_FORMAT_SPECIFICATION.md` 原则 1 与前端检查项（「是否检查了 `res.code === 200`」）
    都把 200 定成唯一的成功码，前端 `PlanForm.vue` / `ExecutionDialog.vue` 也据此判定。
    HTTP 状态码可以按 REST 走（新建 201），但**信封里仍要写 `code=200`**。
    **本条曾是错的**：`inspection.py` 的 create/update/toggle 三个写接口一度都返回
    `Response(code=201, message="Created")`，本文件把它当成「模块契约」记录下来，
    `assert_ok` 也随之放宽成 `body["code"] in (200, 201)`——契约缺陷于是被洗成绿色基线，
    直到线上 `PUT /inspection-plans/{id}` 弹出文案为 "Created" 的错误提示才暴露（守护用例 TC-INS-015）。
    教训：**辅助断言函数不得为了「兼容」而放宽成功码的取值集合**；拿不准时去读规范文档，
    而不是把观测到的现状写成契约。
16. **异步夹具里对已 flush 的对象取未加载集合会抛 `MissingGreenlet`**。
    `db_session.add(role); await db_session.flush(); role.permissions.extend(...)` 必炸。
    关联要在 flush **之前**完成，或先 `await db_session.refresh(obj, ["permissions"])`；
    收尾的 `refresh(user)` 要写成 `refresh(user, ["roles"])`，否则下游 `user.roles` 同样炸。
    `tests/conftest.py` 的 `test_user` / `auth_headers` / `viewer_user` 三处均已按此修正。
17. **Element Plus 2.x 校验失败项挂在 `.el-form-item.is-error`**，不是 `el-form-item--error`；
    且 async-validator 是异步的，点击提交后要 `await flushPromises()` 两轮再断言，否则恒为 0（假绿/假红都出现过）。
18. **布尔型筛选值 `false` 会被 `||` 吞掉**：`is_enabled: form.is_enabled || undefined` 在选「已停用」时
    把条件整个丢掉、退化成「全部」。布尔与 `0` 值筛选一律用 `??`。
19. **不要为不存在的全局 stub 掉接口层，断言要落在 API 模块函数上**。
    `inspection/Plan.vue` 的操作列曾直接调 `window.$axios(...)`——这个全局全仓库从未注册过，
    三个按钮必然抛 `TypeError`。而测试里一句 `window.$axios = vi.fn()` 就把这层掩盖成了假绿。
    正确做法：mock `@/api/<模块>` 导出的函数，并**点击按钮后断言该函数以正确参数被调用**
    （见 `views/inspection/__tests__/Plan.spec.js` T11–T14）。只断言「按钮存在」是无效覆盖。
    同一模块内出现裸 axios / `window.$` 调用时，先确认该全局是否真的被注册过。
20. **不要在 `el-table` 的 scoped slot 里用 `v-if`/`v-else` 包一层 `<template>`**。
    `fixed="right"` 的列会被 el-table 复制一份渲染，嵌套 `<template>` 会让复制出的
    那一份**丢掉 `row` 绑定**（实测 slot 里的 `row` 变成 `null`，`row.id` 取到 `undefined`）。
    症状很隐蔽：按文案取按钮的测试会点到那份坏行，接口收到 `id=undefined` 却不报错。
    改用平铺的 `v-if="条件"` / `v-if="!条件"` 展开每个按钮，并把外层冗余 `<template>` 去掉。
    排查这种问题别靠读模板，直接 dump 渲染结果比对（`findAll('button')` + 点击后打印入参）。
21. **`src/api/__tests__/<模块>.spec.js` 是唯一能拦住「参数放错位置」的层**。
    组件测试 mock 掉了 API 模块，后端测试直连接口，两端都绿而中间断掉：
    `generateInspectionTasks` 曾把 `days` 发成 **query**，后端却从 **JSON body** 读 → 线上 422 `Field required`。
    凡是 POST/PUT，都必须有一条用例断言 `data`（body）与 `params`（query）各自落在哪一侧；
    只断言 URL 和 method 不够。反向的同类坑：后端 `data: dict` 是**必填** body，调用方不带 body 也 422——
    字段全可选的 body 应声明成 `dict | None = Body(default=None)`，并由「不带 body」用例守护。

22. **前端组件测试的 mock 是「我以为的契约」，不是后端真实的契约**——`PlanForm.spec.js` 的 T4
    一直用 `updateInspectionPlan.mockResolvedValue({ code: 200 })`，组件测试全绿，
    真实后端却回 201（见第 15 条）。**mock 掉 API 模块的测试永远拦不住后端契约漂移**，
    因为两侧各自断言自己那一半。能拦住它的只有「不 mock、真打接口」的层：
    后端 pytest（用 `assert_ok` 钉死信封 code）+ `src/api/__tests__/<模块>.spec.js`（钉死参数落位）。
    mock 里请填**后端真实返回的信封**（含 `message`），不要用 `{ code: 200 }` 这种空壳——
    空壳会让「成功分支的文案/字段依赖」这类断言全部失效。

23. **「能不能查到」和「有没有提交」是两件事——测试里默认查不出后者**。
    `client` 与 `db_session` **共用同一个会话**，未 commit 的行对同一会话可见。
    所以 `generate` 只 `db.add()` + `flush()` 就返回时，接口回 7 条、测试里查也是 7 条，
    而线上 `get_db` 在 finally 里只 close 不 commit → 事务回滚 → 库里 0 行、任务页空白。
    这类用例必须**主动丢弃未提交变更再断言**：
    ```python
    await client.post(...)          # 打接口
    await db_session.rollback()     # 提交过的行不受影响，只 flush 的会消失
    assert (await db_session.execute(select(func.count())...)).scalar_one() == 3
    ```
    见 `tests/test_inspection_api.py::test_generate_tasks_are_committed`。
    背景：`CRUDBase.create` 自带 `commit()`，而服务层手写 `db.add()` 的路径没有这层保护，
    `get_db` 也不兜底——**新写 `db.add()` 时先问一句「谁负责 commit」**。

24. **`apply_data_scope` 对没有 `created_by` / `org_id` 的模型会静默变成 no-op**。
    该函数用 `hasattr(model, ...)` 守卫，属性缺失时**原样返回查询**——调用看起来生效了，
    实际谁都能看全部，比不调更危险。`InspectionTask` 两个字段都没有（只有
    `plan_id` / `responsible_user_id`），所以数据范围要写域内专用函数
    （`inspection_service.apply_task_data_scope`）：`self` 锚 `responsible_user_id`
    ——**不是 `created_by`**，任务是管理员/定时生成的，按 `created_by` 过滤会让
    被指派的人一条都看不到；`dept` 经 `plan.org_id` 折算，口径是「本部门及**子**部门」，
    挂在父节点的数据不可见（与 P1-007 对 devices 的口径一致）。
    另：过滤必须同时作用于 items 与 `total` 用的那条 stmt，否则会出现「总数 2、只回 1 条」。

25. **SQLite 下 `begin_nested()` 的 savepoint 是「假」的，用它写「提交没提交」的断言会得到假绿**。
    实测（SQLAlchemy 2.0 + aiosqlite，本仓库）：套在 `begin_nested()` 里 `flush` 的行
    **扛得住后续 `db_session.rollback()`**；不套 savepoint 的才会被丢弃。
    也就是说 `await db.rollback(); assert 行还在` 这个手法在 SQLite 上**恒为真**，
    无论生产代码有没有 `commit` —— 它测不出任何东西。
    正确信号是 **`db_session.in_transaction()`**：返回时若为 `True` 说明事务没结束
    （＝没提交），`False` 才是提交过。实测提交后 `False`、仅 flush `True`。
    见 `tests/test_inspection_scheduler.py::test_tasks_are_committed`。
    ⚠️ 连带影响：**PostgreSQL 与 SQLite 的 savepoint 语义不同**，所以
    「靠 savepoint 做错误隔离」这类逻辑在本仓库的单测里是**零覆盖**的——
    别看到 SQLite 全绿就以为生产路径验证过了。

26. **判别 `IntegrityError` 的类别不能只看异常类型，必须看 sqlstate / 文案**。
    FK 违例与唯一违例**都是** `IntegrityError`。把二者都当成「已存在」吞掉，
    任务会**静默不生成**——比直接报错难发现得多。
    Postgres 用 `orig.sqlstate == "23505"`（唯一）/ `"23503"`（外键）；
    SQLite 没有 sqlstate，回退到文案里的 `unique`。
    ⚠️ 而 SQLite **默认不启用外键**（`PRAGMA foreign_keys=OFF`），所以 FK 分支在单测里
    根本触发不到，只能用假异常对象直接覆盖——见
    `tests/test_inspection_scheduler.py::test_duplicate_error_classifier_covers_postgres_branch`。

27. **后台任务的日志要能实时看到，`print()` 是不够的**。
    容器 stdout 接到管道时 Python 是**块缓冲**，后台任务打的几行日志会一直攒在缓冲区里，
    `docker compose logs` 什么都看不到——而「凌晨到底跑没跑」正是这类任务唯一的外部可观测信号。
    实测：补跑 12 秒后日志已生效但一条都看不到，直到在 `scripts/entrypoint.sh` 里
    `export PYTHONUNBUFFERED=1` 才出现。写后台任务时顺手确认这一项。

28. **`selectinload` / 懒加载这类问题，测试里会因为 identity map 而变成假绿**。
    测试夹具与请求**共用同一个会话**，夹具里建出来的设备/用户对象已经在
    identity map 中；组件（或响应构造）访问 `order.device` 时**直接从内存拿到**，
    压根不发 SQL——于是「关系没预加载」这个线上必炸的问题（异步会话下
    `MissingGreenlet` → HTTP 500）在单测里完全看不出来。
    实测：给 `get_repair_order` 加数据范围时把 `crud.get()`（带 4 个
    `selectinload`）换成了裸 `select(RepairOrder)`，**11 条用例全绿**，
    而容器里 admin 打详情直接 500。
    写「接口能否正常返回」这类用例时，先 `db_session.expire_all()` 把 identity map
    清掉，强制关系从库里真加载：
    ```python
    mine_id = e["mine"].id          # ⚠️ 先取出来：expire_all() 会把夹具对象也过期
    db_session.expire_all()         # 同步方法，勿 await
    resp = await client.get(f"/api/v1/repair-orders/{mine_id}", headers=headers)
    ```
    顺序不能反——先 `expire_all()` 再读 `e["mine"].id`，会在**测试自己**身上触发
    同步刷新并抛 MissingGreenlet，把「接口有没有 500」这个待测问题淹掉。
    见 `tests/test_repair_authz.py::test_in_scope_detail_survives_fresh_session`。
    **2026-09-14 又踩一次**：写 `tests/test_inspection_records.py` 时明知本条，
    两个用例仍忘了 `expire_all()`，去掉 `selectinload` 后 5 条**全绿**。
    是靠「拆掉修复看用例是否变红」的变异验证才发现的——**别信自己记得住，
    用变异验证兜底**。

29. **迁移一个端点时，必须扫一遍「谁在断言它的响应形状」**。
    统一信封那轮，`linkage_plans.py` 的 toggle 改完是绿的，
    而 `test_api_contract_regressions.py::test_linkage_toggle_accepts_explicit_state`
    （早先自己写的）断言的还是裸 `resp.json()["is_enabled"]`，直接被打红。
    这类耦合不会自己浮现，得主动 grep：`grep -rn "json()\[" tests/ | grep -v '"code"\|"data"'`。

30. **`model_validate(ORM 对象)` 只对「schema 字段 ⊆ 模型属性」成立**。
    schema 里声明了模型上**没有**的字段时，必填的抛 `ValidationError`（→ 500），
    可空的**静默给 `None`**（页面空白、无任何提示，更难发现）。
    「设备编码/名称」这类要跨关系取的字段最容易中招，本仓库已两次：
    `RepairOrderResponse.device_name`（`order.device.device_name`）与
    `InspectionRecordResponse.device_code/device_name`（`record.device.*`）。
    后者 2026-09-14 由 admin 提交巡检记录暴露，**两个端点同时坏**
    （`POST /inspection-tasks/{id}/records` 与 `GET /inspection-records`），
    且因 `device_code` 是 `str` 必填而报 500；同一 schema 的
    `inspected_by_name` 因为可空，坏得更早却一直没人发现。
    **正确做法**：显式构造响应（如 `_record_out()`），跨关系的字段从关系上取，
    并把关系 `selectinload` 上——`model_validate` 省下的那点代码不值得。
    排查口径：拿 schema 的必填字段减去模型的列，差集里凡是「看起来像别的表上的字段」
    就是这类缺陷。**写完还要问一句：这条路径有没有测试？**
    本缺陷自 `c4a857c2`（3.7 开发）起存在，只因 `/records` 两个端点
    **零用例覆盖**而横跨两次交付未被发现。

31. **浮层复用 `overlayStub` 会把「弹窗压根没打开」断言成真**。
    `views/device/__tests__/mount.js` 的 `overlayStub()` 是**无条件渲染**内容的——
    它把浮层里的一切都塞进 DOM，不管 `modelValue` 是真是假。于是
    `expect(wrapper.text()).toContain('...')` 这类断言**永远为真**，
    正好把这个缺陷家族（见第 32 条）盖得严严实实。
    **必须用 `visibleDialogStub()`**：它按 `modelValue` 决定内容是否渲染
    （`v-if` 语义，命中时挂 `.el-dialog-open`），并提供一个 `.el-dialog-close`
    按钮用于验证关闭回路。断言写成
    `expect(wrapper.find('.el-dialog-open').exists()).toBe(true)`。
    另注：`Plan.spec.js` 用 `PlanDetail: true` 把整个子组件 stub 掉，
    等于连挂载都没发生——**stub 掉一个组件就等于放弃了对它的所有验证**，
    被 stub 的组件必须另有自己的 spec。

32. **组件「声明了 `modelValue` 却从不读它」→ 弹窗永远打不开，且不报错**。
    写法：`defineProps({ modelValue: Boolean })` 声明了对外契约，却把浮层的
    `v-model` 绑在**各自的局部 `ref(false)`** 上。局部 ref 初值 false，
    而唯一的赋值语句通常是 `handleClose` 里的 `false`——
    **没有任何路径能把它置为 true**。父组件 `visible.value = true` 只改了 prop，
    弹窗读的是另一个变量。症状：点按钮毫无反应，控制台干净。
    2026-09-14 本仓库**同时三处**（`RecordViewer` / `StatsDialog` / `PlanDetail`），
    是同一段代码抄了三遍；而同目录的 `ExecutionDialog`（`computed({get,set})`）
    与 `PlanForm`（`watch` + `emit`）写法正确，所以只有前三个坏。
    **正确写法**（照抄 `ExecutionDialog.vue`）：

    ```js
    const visible = computed({
      get: () => props.modelValue,
      set: (val) => emit('update:modelValue', val),
    })
    ```

    配套两点：① 打开时的加载逻辑要 `watch(() => props.modelValue, fn, { immediate: true })`
    ——只监听「变化」的话，「挂载时已是打开状态」不会触发，弹窗开着但内容是空的；
    ② 别再多写一个 `watch(visible, ...)`，它会和 setter 互相触发并重复 emit。
    已加静态守卫 `views/inspection/__tests__/dialogContract.spec.js`（3 违规/0 误报）。
    **守卫的规则边界是试出来的**：不加「须声明过 modelValue」这个前提会误报 11 个
    （页面自有弹窗绑自己的 ref 是合法的）；不放行模板直绑 `:model-value="modelValue"`
    会误报 5 个；退化成「文件里出现 `modelValue` 字样即算消费」则会**漏掉它本该抓的那 3 个**
    （坏文件里都有 `defineEmits(['update:modelValue'])`）。
    还必须 `stripComments()` —— 否则它"读"的是修复时顺手写的那句说明注释。
    ⚠️ 它**不做数据流分析**：组件若在别处读了 `props.modelValue`（如上述 `watch`），
    守卫会放行，而此时浮层仍可能绑在局部 ref 上。**组件级用例是主力，守卫只是兜底。**

33. **别断言 `wrapper.text()` 含某个词——很容易被旁边的文字命中而假绿**。
    实测：`StatsDialog` 的用例断言 `text()` 含「每日」（周期类型），
    而样本的计划名恰好叫「每日巡检-总部大楼」。把字段读错（`plan_cycle_type`
    写成不存在的 `cycle_type`）之后**断言依然通过**，命中的是计划名里的「每日」。
    这个假绿是做变异测试时暴露的。
    **做法**：① 样本数据里，被断言的值不要与其他字段互为子串；
    ② 一律用 `descValue(wrapper, label)` 这种**按 label 精确定位**的方式取值再比相等，
    不要用包含匹配；③ 同理，断言「渲染出来的格子」而不是「mock 数据透传」——
    `expect(wrapper.vm.taskList[0].records_count).toBe(2)` 只证明了 mock 自己，
    模板改坏了它照样绿，要连 `.el-table__body` 里的 `td` 一起断言。

34. **断言「某事没有发生」时，要确认拦住它的是被测的那段代码，而不是它后面某个意外异常**。
    实测（2026-09-14，`ExecutionDialog`）：用例断言「未选设备时不得提交」——
    `expect(submitInspectionRecord).not.toHaveBeenCalled()`。把守卫
    `if (!currentSelectedDevice.value) { ElMessage.warning(...); return }` 整段删掉后，
    **这条断言依然通过**：代码继续走到 `currentSelectedDevice.value.id`，
    在 `null` 上读属性抛 `TypeError`，被外层 `catch` 吞掉，于是「没提交」照样为真。
    用例钉住的根本不是守卫，而是守卫后面那句会崩的代码。
    **做法**：不要只断言"没发生副作用"，要钉住被测代码**独有的可观测副作用**
    （这里是一条 `ElMessage.warning('请先选择设备')`）。
    同理适用于「没弹窗」「没跳转」「没改 state」这类否定式断言——
    它们天然容易在错误的位置上成立。
    **通用办法还是变异测试**：把守卫拆掉，确认它真的红。
    本会话三次假绿（第 31 条的 `overlayStub`、第 33 条的 `text()` 子串命中、
    本条）**全都是靠变异测试才暴露的**，没有一次是靠读代码看出来的。

35. **按字面量计数断言 HTML 标签闭合，恒假。**
    实测（2026-09-19，`test_emergency_report.py`）：
    `assert html_content.count("<div>") == html_content.count("</div>")`
    → `0 == 12`。因为报告里所有 div 都带属性（`<div class='...'>`），
    字面量 `<div>` 一个都匹配不到，**左边恒为 0**。
    正确写法是按**标签名前缀**计数：`count("<div")`。`table` / `tr` / `td` 三条同改。
    该用例此前一直红着，但红在 **P1-013**（建数据那步就崩），**根本执行不到断言**——
    P1-013 一修好才暴露出来。见第 37 条。

36. **`await` 一个 ORM 构造函数**（`event = await EmergencyEvent(...)`）。
    实测 `TypeError: object EmergencyEvent can't be used in 'await' expression`。
    ORM 对象**不是 awaitable**，构造是同步的；`await` 应当交给显式的 `db_session.flush()`。
    同一处还留了个元组尾巴 `, None  # 简化创建`——**这类"写坏了但看起来像有意图"的残留
    最容易骗过 review**，读到不认识的 `await` 先问「这个对象凭什么可等待」。

37. **既有红会让真实缺陷"不被执行"，而不只是"不被注意"。**
    这是 P1-012「既存红淹没告警」最有力的实证（2026-09-19）：
    `test_emergency_report.py` 的 **5 条用例一直是红的**，但红在 **P1-013**
    （`BigInteger` 主键在 SQLite 不自增，**建数据那一步**就崩）——它们
    **从来没能执行到被测代码**。P1-013 由 peer 修好的当天，
    「事件报告导出必然 500」当场暴露（`generate_report_html` 的 `timelines`
    实参以 ORM 对象传入只认 dict 的渲染器）。
    **推论**：看到"某文件长期红着"，不要假设"它测的东西大概没问题"——
    它可能**一次都没测过**。修既有红时优先修**能跑起来**的那类
    （环境/夹具层面的），它解锁的可见性远超它自己的条数。



## 七、缺陷与守护用例的绑定规则

- 每修复一个生产缺陷，**同一提交内必须带守护用例**，并在测试报告第四节记全三列：现象 / 修复 / 守护手段。
- 若发现的不是缺陷而是**测试假阳性**（如 DEC-008、第六节第 1 条），要同时做两件事：
  写进本文件第六节，并把受影响的历史用例翻出来复验（假阳性可能已掩盖既有缺陷）。

## 八、完成判据

| 项 | 要求 |
|----|------|
| 数量下限 | 每模块后端 pytest ≥ 30 条、前端 Vitest ≥ 10 条（3.2 实际：后端新增 40 / 前端新增 29 / E2E 32 项；3.3 实际：后端新增 39 / 前端新增 18 / E2E 新增 16 项） |
| 全量绿灯 | `python -m pytest`、`npx vitest run`、`npm run build` 三项同时通过，且无新增 warning（3.3 全量：159 passed + 48 skipped / 106 passed / build 退出码 0） |
| 可重复性 | E2E 连续两次全量重跑结果一致（3.3：19.78s 与 17.30s 两轮均 47 passed + 1 xfailed）；测试数据自清理，不污染开发库——清理后需实测 `pending_alarm=0` 且无残留业务数据 |
| 实时链路 | 帧延迟需给出实测分布而不是「感觉很快」：3.3 M1 红线实测 `n=10 p50=0.081s p95=0.111s max=0.111s`（预算 P95 ≤ 2s、单帧 ≤ 3s） |
| 证据留存 | 报告含真实汇总行（通过数、耗时），原始日志存 `docs/test/raw/`，用例说明可由脚本从 docstring 再生成 |
| 边界声明 | 未执行项、计划偏离、已知遗留必须写进报告第五节并给出对应待办编号，不允许以「全部通过」概览 |
