import { Badge, Card, CardMeta, Grid, H1, H2, Icon, IconButton, Stack, Stat, Table, Text, Tooltip, useHostTheme } from 'qoder/canvas';

export default function FireAlarmDrillModuleCompletion() {
  const theme = useHostTheme();

  const statusToneMap: Record<string, 'success' | 'warning' | 'danger' | undefined> = {
    '✅': 'success',
    '❌': 'danger',
    '⚠️': 'warning',
    '🎁': undefined,
  };

  return (
    <Stack gap={24}>
      <Stack gap={8}>
        <H1>🔥 3.8 消防演练模块 - 开发完成报告</H1>
        <Text tone="secondary">生成时间：2026-09-11 | 版本：v1.0（代码）/ v1.1（计划引用）</Text>
      </Stack>

      {/* Key Metrics */}
      <Grid columns={3} gap={16}>
        <Stat 
          value={<Stack gap={4}><Icon type="check" size={24} tone="success"/>后端 pytest</Stack>} 
          subtext="33/33 通过"
          tone="success"
        />
        <Stat 
          value={<Stack gap={4}><Icon type="check" size={24} tone="success"/>前端 Vitest</Stack>} 
          subtext="31/31 通过 + Build 绿灯"
          tone="success"
        />
        <Stat 
          value={<Stack gap={4}><Icon type="warning" size={24} tone="warning"/>E2E 自动化</Stack>} 
          subtext="Windows 终端编码受阻"
          tone="warning"
        />
      </Grid>

      {/* Deliverables Table */}
      <Card>
        <CardMeta title="核心交付物清单" />
        <Table
          headers={['类型', '任务', '状态', '备注']}
          rows={[
            ['后端模型', 'DrillEvent/DrillEvaluation Schema', '✅', 'models/drill.py'],
            ['后端 CRUD', '增删改查逻辑', '✅', 'crud/drill.py'],
            ['后端服务层', 'execute/complete/cancel 状态机', '✅', 'services/drill_service.py'],
            ['后端 API', '14 个端点注册', '✅', 'api/v1/drills.py'],
            ['权限码 seed', '8 个细粒度权限码 + 角色绑定', '✅', 'scripts/init_data.py'],
            ['API 封装', 'drill.js (14 函数)', '✅', 'frontend/src/api/drill.js'],
            ['列表页', 'Event.vue（弹窗模式）', '✅', 'frontend/src/views/drill/Event.vue'],
            ['计划表单', 'PlanFormDialog.vue', '✅', '参与人员管理 + 编辑回填'],
            ['执行详情', 'DetailDialog.vue', '✅', '控制按钮 + 评估展示'],
            ['评估打分', 'EvaluationDialog.vue', '✅', '动态评估项 + 总分计算'],
            ['单元测试', 'backend/tests/test_drill_crud.py', '✅', '33/33 green'],
            ['组件测试', '3 个 spec.js 文件', '✅', '31/31 green'],
            ['生产构建', 'npm run build', '✅', '退出码 0'],
            ['测试报告', 'docs/test/3.8-测试执行结果.md', '✅', '已输出'],
          ]}
          rowTone={Array(14).fill(undefined)}
        />
      </Card>

      {/* Plan Deviation Summary */}
      <Card>
        <CardMeta title="计划 §十五「实现偏离」摘要">
          <Tooltip content="本章节记录实际实现与本计划的不一致之处及原因说明" position="bottom">
            <IconButton icon="info" />
          </Tooltip>
        </CardMeta>
        <Stack gap={12}>
          {[
            { id: '#1', issue: 'trigger-alarm 端点缺失', impact: '低', reason: '前端 UI 移除模拟报警按钮' },
            { id: '#2', issue: '数据权限过滤缺失', impact: '高', reason: '待 v3.9 增加 visible_org_ids' },
            { id: '#3', issue: '评估 upsert 语义不一致', impact: '中', reason: '唯一约束拒绝重复→返回 400' },
            { id: '#4', issue: 'get_active_drill 未实现', impact: '中', reason: '可延后到详情页面合并校验' },
            { id: '#5', issue: 'PDF → HTML+Print 替代方案', impact: '无', reason: 'reportlab 学习成本高，复用 3.5 经验' },
            { id: '#6', issue: 'is_drill_data 冗余字段删除', impact: '无', reason: 'DEC-006 禁止冗余字段原则' },
          ].map((item) => (
            <Stack key={item.id} gap={4}>
              <Text>
                <Text tone="strong">{item.issue}</Text>{' '}
                <Badge tone={item.impact === '高' ? 'danger' : item.impact === '中' ? 'warning' : 'success'}>{item.impact}</Badge>
              </Text>
              <Text tone="secondary">{item.reason}</Text>
            </Stack>
          ))}
        </Stack>
      </Card>

      {/* Known Issues */}
      <Card>
        <CardMeta title="已知遗留问题 & 后续建议" />
        <Table
          headers={['ID', '问题描述', '严重性', '建议修复优先级', '负责人']}
          rows={[
            ['P01', '数据权限过滤缺失', '高', 'P1（v3.9 迭代）', '[技术负责人]'],
            ['P02', '评估 upsert 语义', '中', 'P2（v3.9 优化）', '[后端开发]'],
            ['P03', 'trigger-alarm 端点', '低', 'backlog', '[产品确认]'],
            ['P04', 'get_active_drill 上下文', '中', 'P2（可选）', '[后端开发]'],
            ['P05', 'E2E Windows 编码问题', '高', 'CI Linux 迁移', '[DevOps]'],
          ]}
          rowTone={['danger', 'warning', 'success', 'warning', 'danger']}
        />
      </Card>

      {/* Testing Evidence */}
      <Card>
        <CardMeta title="测试质量证据">
          <Tooltip content="连续两次全量重跑确保稳定性" position="top">
            <IconButton icon="chart-bar" />
          </Tooltip>
        </CardMeta>
        <Stack gap={16}>
          <Stack direction="row" justify="space-between">
            <Stack gap={4}>
              <Text tone="strong">后端 pytest</Text>
              <Text>backend/tests/test_drill_crud.py</Text>
            </Stack>
            <Badge tone="success">33/33 通过</Badge>
          </Stack>
          <Stack direction="row" justify="space-between">
            <Stack gap={4}>
              <Text tone="strong">前端 Vitest</Text>
              <Text>drill.spec.js(14) + PlanFormDialog(8) + EvaluationDialog(9)</Text>
            </Stack>
            <Badge tone="success">31/31 通过</Badge>
          </Stack>
          <Stack direction="row" justify="space-between">
            <Stack gap={4}>
              <Text tone="strong">构建健康度</Text>
              <Text>npm.cmd run build</Text>
            </Stack>
            <Badge tone="success">EXIT_CODE=0</Badge>
          </Stack>
          <Stack direction="row" justify="space-between">
            <Stack gap={4}>
              <Text tone="strong">基线回归</Text>
              <Text>全量测试预存失败 = 基线（52=52）</Text>
            </Stack>
            <Badge tone="success">无新增失败</Badge>
          </Stack>
        </Stack>
      </Card>

      {/* Version Release Recommendation */}
      <Stack gap={8}>
        <H2>版本发布建议</H2>
        <Card tone="primary">
          <Stack gap={8}>
            <Text tone="strong" size="large">✅ 推荐发布 v3.8.0</Text>
            <Text>
              条件：单测全部达标 + 手动测试确认核心流程可用。遗留问题跟踪至 v3.9（data scope 优先）。
            </Text>
            <Stack gap={4}>
              <Text tone="secondary">签署人：</Text>
              <Stack direction="row" gap={48}>
                <Text>[产品负责人签字]</Text>
                <Text>[技术负责人签字]</Text>
              </Stack>
            </Stack>
          </Stack>
        </Card>
      </Stack>

      <Text tone="secondary" size="small">
        报告撰写：Qoder AI Agent | 依据 PRD v2.0 第 3.8 节 + 开发计划 v1.0/v1.1
      </Text>
    </Stack>
  );
}
