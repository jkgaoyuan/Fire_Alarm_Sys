<template>
  <div class="page-container">
    <!-- 综合概览卡片 -->
    <el-row :gutter="20" class="overview-cards">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background: #e6f7ff;">
            <el-icon :size="32" color="#1890ff"><Box /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ overview.device_total || 0 }}</div>
            <div class="stat-label">设备总数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background: #f6ffed;">
            <el-icon :size="32" color="#52c41a"><CircleCheck /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ ((overview.device_normal_rate || 0) * 100).toFixed(1) }}%</div>
            <div class="stat-label">设备完好率</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background: #fff2e8;">
            <el-icon :size="32" color="#fa541c"><Bell /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ overview.alarm_today || 0 }}</div>
            <div class="stat-label">今日报警</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" style="background: #fff0f6;">
            <el-icon :size="32" color="#eb2f96"><Tools /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ overview.repair_pending || 0 }}</div>
            <div class="stat-label">待处理维修</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 看板入口 -->
    <el-row :gutter="20" class="dashboard-entries">
      <el-col :span="12">
        <el-card shadow="hover" class="dashboard-card" @click="$router.push('/statistics/device-status')">
          <div class="card-header">
            <el-icon :size="24" color="#1890ff"><PieChart /></el-icon>
            <span class="card-title">设备完好率看板</span>
          </div>
          <div class="card-desc">查看各状态设备占比，支持区域下钻分析</div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" class="dashboard-card" @click="$router.push('/statistics/alarm-trend')">
          <div class="card-header">
            <el-icon :size="24" color="#fa541c"><TrendCharts /></el-icon>
            <span class="card-title">报警趋势图</span>
          </div>
          <div class="card-desc">分析近 7/30/90 天报警数量趋势，按类型分组</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="dashboard-entries">
      <el-col :span="12">
        <el-card shadow="hover" class="dashboard-card" @click="$router.push('/statistics/fault-top10')">
          <div class="card-header">
            <el-icon :size="24" color="#fa8c16"><Histogram /></el-icon>
            <span class="card-title">故障 TOP10</span>
          </div>
          <div class="card-desc">查看故障次数最多的前 10 台设备</div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" class="dashboard-card" @click="$router.push('/statistics/inspection-completion')">
          <div class="card-header">
            <el-icon :size="24" color="#52c41a"><DataLine /></el-icon>
            <span class="card-title">巡检完成率</span>
          </div>
          <div class="card-desc">按责任人/区域统计巡检完成率与漏检率</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Box, CircleCheck, Bell, Tools, PieChart, TrendCharts, Histogram, DataLine } from '@element-plus/icons-vue'
import { getStatisticsOverview } from '@/api/statistics'

const overview = ref({})

onMounted(async () => {
  try {
    const res = await getStatisticsOverview()
    overview.value = res.data || {}
  } catch (err) {
    ElMessage.error(err.message || '加载概览数据失败')
  }
})
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20px;
}

.overview-cards {
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  padding: 20px;
  cursor: default;

  .stat-icon {
    width: 64px;
    height: 64px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 16px;
  }

  .stat-info {
    .stat-value {
      font-size: 28px;
      font-weight: bold;
      color: #333;
      line-height: 1.2;
    }
    .stat-label {
      font-size: 14px;
      color: #999;
      margin-top: 4px;
    }
  }
}

.dashboard-entries {
  margin-bottom: 20px;
}

.dashboard-card {
  cursor: pointer;
  transition: all 0.3s;

  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  .card-header {
    display: flex;
    align-items: center;
    margin-bottom: 12px;

    .card-title {
      margin-left: 12px;
      font-size: 18px;
      font-weight: 600;
      color: #333;
    }
  }

  .card-desc {
    font-size: 14px;
    color: #666;
    line-height: 1.5;
  }
}
</style>
