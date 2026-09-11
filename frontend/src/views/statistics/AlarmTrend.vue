<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>报警趋势图</span>
          <div>
            <el-radio-group v-model="days" size="small" @change="loadData">
              <el-radio-button :label="7">近 7 天</el-radio-button>
              <el-radio-button :label="30">近 30 天</el-radio-button>
              <el-radio-button :label="90">近 90 天</el-radio-button>
            </el-radio-group>
            <el-button size="small" style="margin-left: 12px;" @click="$router.back()">返回</el-button>
          </div>
        </div>
      </template>

      <!-- 折线图容器 -->
      <div ref="chartRef" class="chart-container"></div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getAlarmTrend } from '@/api/statistics'

echarts.use([LineChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

const chartRef = ref(null)
let chart = null

const days = ref(7)

async function loadData() {
  try {
    const res = await getAlarmTrend({ days: days.value })
    const data = res.data || {}
    renderChart(data.dates || [], data.series || [])
  } catch (err) {
    ElMessage.error(err.message || '加载数据失败')
  }
}

function renderChart(dates, series) {
  if (!chartRef.value) return

  if (!chart) {
    chart = echarts.init(chartRef.value)
  }

  const typeNames = {
    fire: '火警',
    pre_fire: '预警',
    fault: '故障',
    shield: '屏蔽',
  }

  const option = {
    title: {
      text: `近 ${days.value} 天报警趋势`,
      left: 'center',
    },
    tooltip: {
      trigger: 'axis',
    },
    legend: {
      data: series.map(s => typeNames[s.type] || s.type),
      top: 30,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dates,
    },
    yAxis: {
      type: 'value',
    },
    series: series.map(s => ({
      name: typeNames[s.type] || s.type,
      type: 'line',
      data: s.data,
      smooth: true,
    })),
  }

  chart.setOption(option)
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
  height: 500px;
}
</style>
