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
8. **`self` 数据范围**：`created_by` 是 `self` 范围的唯一锚点（DEC-004），业务表漏建该字段会导致该类用户可见量恒为 0。
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
