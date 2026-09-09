<template>
  <div class="device-trajectory">
    <div class="trajectory-toolbar">
      <el-date-picker
        v-model="range"
        type="datetimerange"
        range-separator="至"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
        :shortcuts="shortcuts"
        value-format="YYYY-MM-DDTHH:mm:ss"
        style="width: 380px"
        @change="handleRangeChange"
      />
      <el-button type="primary" :loading="loading" @click="loadTrajectory">查询</el-button>
      <el-dropdown :disabled="!points.length" @command="handleExport">
        <el-button :disabled="!points.length">
          导出<el-icon class="el-icon--right"><arrow-down /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="xlsx">Excel（.xlsx）</el-dropdown-item>
            <el-dropdown-item command="csv">CSV（.csv）</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="trajectory-tip">
        区间最长 {{ MAX_DAYS }} 天，默认近 {{ DEFAULT_DAYS }} 天
      </span>
    </div>

    <div v-loading="loading">
      <div v-show="points.length" ref="chartRef" class="trajectory-chart" />
      <el-empty v-if="!loading && !points.length" description="所选区间内无状态变更" />

      <el-table v-if="points.length" :data="points" size="small" border max-height="280">
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.time) }}</template>
        </el-table-column>
        <el-table-column label="状态变更" width="150">
          <template #default="{ row }">
            <span class="text-muted">{{ deviceStatusLabel(row.old_status) }}</span>
            →
            <el-tag :type="deviceStatusType(row.new_status)" size="small">
              {{ row.status_label || deviceStatusLabel(row.new_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="变更原因" min-width="160" show-overflow-tooltip />
        <el-table-column prop="operator" label="操作人" width="120" />
      </el-table>

      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        class="trajectory-pagination"
        @current-change="loadTrajectory"
      />
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { exportDeviceTrajectory, getDeviceTrajectory } from '@/api/device'
import { DEVICE_STATUS_OPTIONS, deviceStatusLabel, deviceStatusType } from '@/utils/device'

const props = defineProps({
  deviceId: { type: Number, default: null },
})

/** 与后端 resolve_window 的缺省口径保持一致 */
const DEFAULT_DAYS = 7
const MAX_DAYS = 90

const loading = ref(false)
const points = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(200)
const range = ref([])
const chartRef = ref(null)
const meta = ref(null)

let chart = null

const shortcuts = [
  { text: '近 24 小时', value: () => [shiftHours(24), new Date()] },
  { text: '近 7 天', value: () => [shiftDays(7), new Date()] },
  { text: '近 30 天', value: () => [shiftDays(30), new Date()] },
]

function shiftDays(days) {
  return new Date(Date.now() - days * 86400000)
}

function shiftHours(hours) {
  return new Date(Date.now() - hours * 3600000)
}

/** el-date-picker 的 value-format 用本地时间渲染，统一按本地时间序列化 */
function toLocalIso(date) {
  const pad = (value) => String(value).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  )
}

function queryParams() {
  const [start, end] = range.value || []
  return { start: start || undefined, end: end || undefined }
}

/** 与后端 Content-Disposition 保持一致的区间标记 */
function rangeTag() {
  const day = (value) => (value ? String(value).slice(0, 10).replace(/-/g, '') : '')
  const [start, end] = range.value || []
  const today = toLocalIso(new Date()).slice(0, 10).replace(/-/g, '')
  return `${day(start) || today}_${day(end) || today}`
}

onMounted(() => {
  range.value = [toLocalIso(shiftDays(DEFAULT_DAYS)), toLocalIso(new Date())]
  loadTrajectory()
  window.addEventListener('resize', resizeChart)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
  chart = null
})

watch(
  () => props.deviceId,
  () => {
    page.value = 1
    loadTrajectory()
  }
)

async function loadTrajectory() {
  if (!props.deviceId) return
  loading.value = true
  try {
    const res = await getDeviceTrajectory(props.deviceId, {
      ...queryParams(),
      page: page.value,
      page_size: pageSize.value,
    })
    const data = res.data || {}
    meta.value = data
    points.value = data.items || []
    total.value = data.total || 0
    renderChart()
  } catch (err) {
    ElMessage.error(err.message || '加载历史轨迹失败')
  } finally {
    loading.value = false
  }
}

function handleRangeChange() {
  page.value = 1
  loadTrajectory()
}

/**
 * 状态是离散量，用阶梯线（step）而不是平滑线，
 * 才能表达"变更从这一刻起持续到下一次变更"。
 */
function renderChart() {
  if (!points.value.length) {
    chart?.clear()
    return
  }
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)

  const statusAxis = DEVICE_STATUS_OPTIONS.map((item) => item.label)
  chart.setOption(
    {
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          const point = points.value[params[0]?.dataIndex]
          if (!point) return ''
          const lines = [
            formatTime(point.time),
            `${deviceStatusLabel(point.old_status)} → ${
              point.status_label || deviceStatusLabel(point.new_status)
            }`,
          ]
          if (point.reason) lines.push(`原因：${point.reason}`)
          if (point.operator) lines.push(`操作人：${point.operator}`)
          return lines.join('<br/>')
        },
      },
      grid: { left: 60, right: 24, top: 24, bottom: 48 },
      xAxis: { type: 'time', axisLabel: { hideOverlap: true } },
      yAxis: { type: 'category', data: statusAxis },
      series: [
        {
          type: 'line',
          step: 'end',
          symbolSize: 7,
          lineStyle: { width: 2 },
          data: points.value.map((point) => [
            new Date(point.time).getTime(),
            point.status_label || deviceStatusLabel(point.new_status),
          ]),
        },
      ],
    },
    true
  )
  // 抽屉内的图表容器在数据到达前宽度为 0，需要在有尺寸后重新测量
  chart.resize()
}

function resizeChart() {
  chart?.resize()
}

function formatTime(value) {
  return value ? String(value).replace('T', ' ').slice(0, 19) : '-'
}

/**
 * 导出走 axios 拿文件流：后端超限或区间非法时返回的是 {code,message} JSON，
 * 直接落成 .xlsx 会得到一个打不开的"错误文件"，因此先探一次 blob 类型。
 */
async function handleExport(format) {
  try {
    const blob = await exportDeviceTrajectory(props.deviceId, {
      ...queryParams(),
      format,
    })
    if (blob?.type?.includes('application/json')) {
      const payload = JSON.parse(await blob.text())
      ElMessage.error(payload.message || '导出失败')
      return
    }
    const filename = `${meta.value?.device_code || 'device'}_trajectory_${rangeTag()}.${format}`
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`已导出 ${total.value} 条状态变更`)
  } catch (err) {
    ElMessage.error(err?.message || '导出失败')
  }
}
</script>

<style lang="scss" scoped>
.trajectory-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.trajectory-tip {
  color: #909399;
  font-size: 12px;
}

.trajectory-chart {
  width: 100%;
  height: 260px;
}

.trajectory-pagination {
  margin-top: 12px;
  justify-content: flex-end;
}

.text-muted {
  color: #909399;
}
</style>
