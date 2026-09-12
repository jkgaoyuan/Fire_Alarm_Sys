<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>设备完好率看板</span>
          <div>
            <el-button size="small" @click="$router.back()">返回</el-button>
            <el-button size="small" type="primary" @click="handleExport">导出Excel</el-button>
          </div>
        </div>
      </template>

      <!-- 面包屑导航 -->
      <el-breadcrumb separator="/" class="breadcrumb">
        <el-breadcrumb-item :to="{ path: '/statistics/device-status' }">全部区域</el-breadcrumb-item>
        <el-breadcrumb-item v-for="(org, idx) in breadcrumbOrgs" :key="idx">
          <span class="breadcrumb-link" @click="drillDown(org.id, org.name)">{{ org.name }}</span>
        </el-breadcrumb-item>
      </el-breadcrumb>

      <!-- 饼图容器 -->
      <div ref="chartRef" class="chart-container"></div>

      <!-- 状态汇总表格 -->
      <el-table :data="statusData" border stripe style="margin-top: 20px;">
        <el-table-column prop="label" label="状态" />
        <el-table-column prop="count" label="数量" />
        <el-table-column label="占比">
          <template #default="{ row }">
            {{ total > 0 ? ((row.count / total) * 100).toFixed(1) : 0 }}%
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getDeviceStatusStats } from '@/api/statistics'
import { createExportTask } from '@/api/reports'

echarts.use([PieChart, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const route = useRoute()
const router = useRouter()
const chartRef = ref(null)
let chart = null

const statusData = ref([])
const total = ref(0)
const currentOrgId = ref(null)
const breadcrumbOrgs = ref([])

async function loadData(orgId = null) {
  try {
    const res = await getDeviceStatusStats({ org_id: orgId })
    statusData.value = res.data.items || []
    total.value = res.data.total || 0
    renderChart()
  } catch (err) {
    ElMessage.error(err.message || '加载数据失败')
  }
}

function renderChart() {
  if (!chartRef.value) return

  if (!chart) {
    chart = echarts.init(chartRef.value)
  }

  const option = {
    title: {
      text: '设备状态分布',
      left: 'center',
    },
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)',
    },
    legend: {
      orient: 'vertical',
      left: 'left',
    },
    series: [
      {
        name: '设备状态',
        type: 'pie',
        radius: '60%',
        data: statusData.value.map(item => ({
          name: item.label,
          value: item.count,
        })),
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
      },
    ],
  }

  chart.setOption(option)
}

async function handleExport() {
  try {
    await createExportTask({
      task_type: 'device_status',
      params: { org_id: currentOrgId.value },
      data: statusData.value,
      format: 'xlsx',
    })
    ElMessage.success('导出任务已创建，请前往导出中心下载')
  } catch (err) {
    ElMessage.error(err.message || '导出失败')
  }
}

function drillDown(orgId, orgName) {
  currentOrgId.value = orgId
  breadcrumbOrgs.value.push({ id: orgId, name: orgName })
  router.replace({ query: { org_id: orgId } })
  loadData(orgId)
}

onMounted(() => {
  const orgId = route.query.org_id
  if (orgId) {
    currentOrgId.value = parseInt(orgId)
    loadData(currentOrgId.value)
  } else {
    loadData()
  }

  window.addEventListener('resize', () => chart?.resize())
})

onBeforeUnmount(() => {
  chart?.dispose()
  window.removeEventListener('resize', () => chart?.resize())
})
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.breadcrumb {
  margin-bottom: 20px;
}

.breadcrumb-link {
  cursor: pointer;
  color: #1890ff;

  &:hover {
    text-decoration: underline;
  }
}

.chart-container {
  width: 100%;
  height: 400px;
}
</style>
