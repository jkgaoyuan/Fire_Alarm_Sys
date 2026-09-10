import { Grid, H1, H2, Stack, Stat, Table, Text, Divider } from 'qoder/canvas';

export default function TestReport36() {
  return (
    <Stack gap={24}>
      <Stack gap={8}>
        <H1>📊 3.6 设备巡检 - 测试执行报告</H1>
        <Text tone="secondary">Fire Alarm System • Inspection Module • Test Report</Text>
      </Stack>

      <Divider />

      {/* Executive Summary */}
      <Stack gap={16}>
        <H2>📈 测试摘要</H2>
        <Grid columns={4} gap={16}>
          <Stat value="7" label="总用例数" tone="info" />
          <Stat value="1" label="✅ 通过" tone="success" />
          <Stat value="6" label="❌ 错误" tone="danger" />
          <Stat value="14%" label="通过率" tone="warning" />
        </Grid>
      </Stack>

      <Divider />

      {/* 测试分类统计 */}
      <Stack gap={16}>
        <H2>🧩 测试覆盖矩阵</H2>
        <Table
          headers={['测试类型', '用例数量', '状态', '覆盖范围']}
          rows={[
            ['后端单元测试', '7 条', '进行中', 'FR-032 CRUD + 权限'],
            ['E2E 集成测试', '8 条', '已编写', '完整端到端流程'],
            ['前端组件测试', '0 条', 'N/A', 'Vue 单元测试待添加'],
            ['手动验证', 'N/A', '待执行', 'UI/UX 交互验证'],
          ]}
        />
        
        <Stack gap={8}>
          <H3>PRD 需求测试映射</H3>
          <Table
            headers={['功能点', '描述', '优先级', '测试覆盖率']}
            rows={[
              ['FR-032', '巡检计划管理', 'P0', '14% (1/7)'],
              ['FR-033', '任务生成与状态', 'P0', '待 E2E 补充'],
              ['FR-034', '手动巡检记录', 'P0', '待 E2E 补充'],
              ['FR-035', '漏检统计预警', 'P1', '待 E2E 补充'],
              ['FR-036', '记录归档查询', 'P0', '待 E2E 补充'],
            ]}
            rowTone={[undefined, undefined, undefined, undefined]}
          />
        </Stack>
      </Stack>

      <Divider />

      {/* 详细测试结果 */}
      <Stack gap={16}>
        <H2>🔍 详细执行结果</H2>
        
        <Stack gap={12}>
          <H3>✅ 通过的用例</H3>
          <Table
            headers={['测试 ID', '名称', '描述', '耗时']}
            rows={[
              ['TC-PERM-032-002', 'test_unauthorized_access', '未授权访问返回 401', '~50ms'],
            ]}
            rowTone={[undefined, 'default', 'success', undefined]}
          />
        </Stack>

        <Stack gap={12}>
          <H3>❌ 失败/错误用例</H3>
          <Table
            headers={['测试 ID', '名称', '错误类型', '根本原因']}
            rows={[
              ['TC-BACKEND-001', 'test_create_inspection_plan', 'SQLAlchemy Error', 'Organization 缺少 inspection_plans 关系'],
              ['TC-BACKEND-002', 'test_list_inspection_plans', 'SQLAlchemy Error', '同左'],
              ['TC-PERM-032-001', 'test_no_permission_access', 'SQLAlchemy Error', '同左'],
              ['TC-ERROR-032-001', 'test_invalid_cycle_type', 'SQLAlchemy Error', '同左'],
              ['TC-ERROR-032-002', 'test_empty_plan_name', 'SQLAlchemy Error', '同左'],
              ['TC-STAT-032-001', 'test_inspection_stats_endpoint', 'SQLAlchemy Error', '同左'],
            ]}
            rowTone={[undefined, 'default', 'error', 'error']}
          />
          
          <Text size="small" tone="secondary">
            ** 错误堆栈分析 **：<br/>
            `sqlalchemy.exc.InvalidRequestError: Mapper 'Mapper[Organization(organizations)]' has no property 'inspection_plans'.`<br/>
            这是由于 InspectionPlan 模型中定义了 `organization` relationship 并指定了 `back_populates="inspection_plans"`，但 Organization 模型中缺少对应的 `inspection_plans` 关系定义。<br/><br/>
            ** 修复操作 **：<br/>
            ✅ 已在 app/models/organization.py 中添加 inspection_plans 关系<br/>
            ✅ 已在 app/models/device_type.py 中添加 inspection_plans 关系
          </Text>
        </Stack>
      </Stack>

      <Divider />

      {/* 问题诊断与修复 */}
      <Stack gap={16}>
        <H2>🔧 问题诊断与修复</H2>
        
        <Stack gap={12}>
          <H3>问题 #1: SQLAlchemy ORM 关系初始化失败</H3>
          <Table
            headers={['阶段', '发现问题', '影响范围', '解决方案']}
            rows={[
              ['代码编写', 'InspectionPlan 定义 back_populates', '全表关联'],
              ['编译运行', 'Organization 缺少对应关系', '测试用例 6 条全部失败'],
              ['诊断排查', '查看报错堆栈', '找到缺失的属性'],
              ['实施修复', '添加 missing relationship', '预期可解决'],
            ]}
          />
          
          <Text size="small" tone="secondary">
            ** 根因分析 **:<br/>
            SQLAlchemy 的双向关系要求双方都明确定义关系属性。当 A → B 指定了 back_populates 时，B 必须有一个对应的属性指向 A，否则会在 mapper.configure() 阶段抛出异常。<br/><br/>
            ** 技术决策 **:<br/>
            遵循项目 ORM 最佳实践，在基类模型中添加新关系的反向引用（参考 User、Device 等现有模型的实现方式）。
          </Text>
        </Stack>
      </Stack>

      <Divider />

      {/* 下一步建议 */}
      <Stack gap={16}>
        <H2>📋 后续行动建议</H2>
        <Stack gap={12}>
          <ul style={{margin: 0, paddingLeft: 20}}>
            <li><strong>[立即] 重新运行测试:</strong> `cd backend && pytest tests/test_inspection.py -v --tb=short`</li>
            <li><strong>[建议] 完善 E2E 测试:</strong> 运行现有的 test_inspection_e2e.py 需要配置真实数据库</li>
            <li><strong>[建议] 添加更多边界用例:</strong> 包括周期生成逻辑、权限过滤、数据范围等</li>
            <li><strong>[建议] 前端单元测试:</strong> Vue 组件使用 @vue/test-utils 编写测试</li>
            <li><strong>[建议] 集成测试覆盖:</strong> Service 层直接调用测试（非 HTTP 接口）</li>
          </ul>
        </Stack>
        
        <Text size="small" tone="secondary">
          ** 当前进度 **：<br/>
          ✅ 后端 API 开发完成（11 endpoints）<br/>
          ✅ 后端业务逻辑完成（Service + Scheduler）<br/>
          ✅ E2E 测试用例已编写（8 条，依赖远程服务）<br/>
          ✅ 单元测试框架已建立（7 条）<br/>
          ⏸️ 单元测试部分失败（ORM 关系问题已修复）<br/>
          ❌ 前端测试尚未开始<br/>
        </Text>
      </Stack>

      <Divider />

      {/* 结论 */}
      <Stack gap={8}>
        <H2>💡 总结</H2>
        <Text>
          <strong>测试结果表明：</strong>
        </Text>
        <ul style={{margin: 0, paddingLeft: 20}}>
          <li>后端 API 功能已实现并通过 1 条基础权限测试</li>
          <li>ORM 关系模型存在缺陷导致多数测试失败</li>
          <li>关键问题已识别并已提供修复方案</li>
          <li>E2E 测试用例编写完成但需部署环境</li>
        </ul>
        
        <Text tone="secondary">
          ** 建议优先操作 **：重新运行单元测试以验证 ORM 关系修复是否成功，然后继续完善 E2E 和前端测试用例以达到 80%+ 覆盖率目标。
        </Text>
      </Stack>
    </Stack>
  );
}
