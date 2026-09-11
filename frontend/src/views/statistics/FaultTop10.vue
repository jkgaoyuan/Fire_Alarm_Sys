<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>故障 TOP10</span>
          <el-button size="small" @click="$router.back()">返回</el-button>
        </div>
      </template>

      <!-- 柱状图容器 -->
      <div ref="chartRef" class="chart-container"></div>

      <!-- 详细表格 -->
      <el-table :data="faultData" border stripe style="margin-top: 20px;">
        <el-table-column type="index" label="排名" width="80" />
        <el-table-column prop="device_code" label="设备编码" />
        <el-table-column prop="device_name" label="设备名称" />
        <el-table-column prop="fault_count" label="故障次数" />
        <el-table-column label="操作">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewDevice(row.device_id)">
              查看详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getFaultTop10 } from '@/api/statistics'

echarts.use([BarChart, TitleComponent, TooltipComponent, GridComponent, CanvasRenderer])

const router = useRouter()
const chartRef = ref(null)
let chart = null

const faultData = ref([])

async function loadData() {
  try {
    const res = await getFaultTop10()
    faultData.value = res.data.items || []
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
      text: '故障次数 TOP10 设备',
      left: 'center',
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true,
    },
    xAxis: {
      type: 'value',
      name: '故障次数',
    },
    yAxis: {
      type: 'category',
      data: faultData.value.map(d => d.device_name).reverse(),
      axisLabel: {
        interval: 0,
        rotate: 0,
      },
    },
    series: [
      {
        name: '故障次数',
        type: 'bar',
        data: faultData.value.map(d => d.fault_count).reverse(),
        itemStyle: {
          color: '#fa8c16',
        },
      },
    ],
  }

  chart.setOption(option)
}

function viewDevice(deviceId) {
  router.push(`/device/archive?id=${deviceId}`)
}

onMounted(() => {
  loadData()
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

.chart-container {
  width: 100%;
  height: 400px;
}
</style>
