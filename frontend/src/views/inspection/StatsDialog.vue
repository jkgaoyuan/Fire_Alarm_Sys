<!--
统计信息弹窗 (StatsDialog)
3.6-F2 配套组件
功能：展示**某个巡检任务**的统计信息

2026-09-14 两处修复：

1. **弹窗打不开**：与 RecordViewer / PlanDetail 同根因 —— `v-model` 绑在局部
   `ref(false)` 上，`props.modelValue` 从未被读，局部 ref 无人置 true。
   现改为 computed 代理（见下方注释）。

2. **内容是编造的**：原实现写死 `plan_name: '示例计划'`、`task_date: new Date()`、
   `status: 'pending'`，而 `recordsCount / abnormalCount / completionRate` 三个 ref
   **从未被赋值**，恒为 0 —— 弹窗会一本正经地显示「示例计划 / 0个 / 0次」，
   **看着像真数据**。这正是本项目反复栽的坑（维修统计页四项指标恒为 0、
   已记录数恒为 0）。现改为：任务事实全部取自行数据，异常次数取后端真实计数。

   **「完成率」已移除**：任务级没有真实分母（应检设备数要按计划的 org + 设备类型
   再查一次设备表才能算），计划级完成率在「计划详情」里。用一个恒 0 的假百分比
   顶替，比不显示更糟 —— 不显示的空白会让人追问，假的 0% 不会。
-->
<template>
  <el-dialog
    v-model="visible"
    title="任务统计信息"
    width="600px"
  >
    <el-descriptions v-if="task" v-loading="loading" :column="1" border>
      <el-descriptions-item label="任务日期">{{ formatDate(task.task_date) }}</el-descriptions-item>
      <el-descriptions-item label="所属计划">{{ task.plan_name || '-' }}</el-descriptions-item>
      <el-descriptions-item label="周期类型">{{ cycleTypeLabel(task.plan_cycle_type) }}</el-descriptions-item>
      <el-descriptions-item label="责任人">{{ task.responsible_user_name || '-' }}</el-descriptions-item>
      <el-descriptions-item label="当前状态">
        <el-tag :type="taskStatusType(task.status)">
          {{ taskStatusLabel(task.status) }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="已记录设备数">{{ task.records_count || 0 }} 个</el-descriptions-item>
      <el-descriptions-item label="其中异常">{{ abnormalCount }} 次</el-descriptions-item>
      <el-descriptions-item label="其中正常">{{ normalCount }} 次</el-descriptions-item>
    </el-descriptions>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getInspectionRecords } from '@/api/inspection'

const props = defineProps({
  modelValue: Boolean,
  // 任务列表的整行数据。任务事实（日期/计划/周期/状态/责任人/记录数）全都已经在
  // 行里了，直接传进来即可，不必再为这些字段请求一次后端。
  task: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['update:modelValue'])

// ⚠️ 必须是 computed 代理到 props.modelValue，**不能**写成 `const visible = ref(false)`：
// 那样写父组件的 v-model 就完全改不动弹窗，永远打不开且不报错。
// 见 tests/dialogContract.spec.js 的静态守卫。
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const loading = ref(false)
const abnormalCount = ref(0)

// 正常次数由「已记录数 − 异常次数」推出，不再单独请求一次：
// 两个数字同源，分开查反而可能因两次查询之间产生新记录而自相矛盾。
const normalCount = computed(() =>
  Math.max(0, (props.task?.records_count || 0) - abnormalCount.value)
)

// 打开时才拉取（监听 prop 而非 visible —— 后者修复后已由 prop 派生）。
// ⚠️ 必须 immediate：只监听「变化」的话，挂载时已打开（modelValue 初值 true）
// 永远不会触发回调，弹窗开着但统计恒为 0。
watch(
  () => props.modelValue,
  (val) => {
    if (val) loadStats()
  },
  { immediate: true }
)

async function loadStats() {
  const taskId = props.task?.id
  if (!taskId) return

  loading.value = true
  try {
    // 只取 total，所以 page_size 给 1 即可：后端用 count_stmt 算总数，
    // 不受分页截断影响（若改用「查全部再 filter」的写法，记录数超过一页就会少算）。
    const res = await getInspectionRecords({
      task_id: taskId,
      result: 'abnormal',
      page: 1,
      page_size: 1,
    })
    abnormalCount.value = res.data?.total ?? 0
  } catch (err) {
    // 统计拿不到不该把弹窗搞崩：降级为 0，其余字段照常显示
    abnormalCount.value = 0
    ElMessage.error(err.message || '加载统计信息失败')
  } finally {
    loading.value = false
  }
}

// ==================== 辅助函数 ====================

function formatDate(dateStr) {
  if (!dateStr) return '-'
  return dateStr.toString().slice(0, 10)
}

function cycleTypeLabel(type) {
  const map = { daily: '每日', weekly: '每周', monthly: '每月', quarterly: '每季度', yearly: '每年' }
  return map[type] || type || '-'
}

function taskStatusLabel(status) {
  const map = { pending: '待执行', doing: '执行中', completed: '已完成', missed: '漏检' }
  return map[status] || status
}

function taskStatusType(status) {
  // 兜底必须是合法 type 或 undefined：空串会拼出不存在的 class `el-tag--`，
  // 既触发 Element Plus 的 prop 校验告警，又让标签回落到基础 .el-tag（蓝色）
  // 反而最显眼。default: 'primary' 只在 undefined 时生效，拦不住显式空串。
  // 同 Task.vue / PlanDetail.vue。
  const map = { pending: undefined, doing: 'warning', completed: 'success', missed: 'danger' }
  return map[status]
}
</script>

<style lang="scss" scoped>
.stats-content {
  line-height: 2;
}
</style>
