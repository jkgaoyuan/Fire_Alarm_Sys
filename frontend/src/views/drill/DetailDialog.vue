<!--
演练详情弹窗 (3.8-F1/F2)
功能：展示演练详细信息、参与人员、现场记录、评估结果
     支持执行控制（开始/完成/取消演练）、参与人员签到
权限码：drill:view/create/update/delete/execute/evaluate
-->
<template>
  <el-dialog v-model="visible" :title="dialogTitle" width="900px" @close="handleClose">
    <el-descriptions v-if="drillInfo" :column="2" border>
      <el-descriptions-item label="演练名称">{{ drillInfo.drill_name }}</el-descriptions-item>
      <el-descriptions-item label="演练类型">
        <el-tag :type="getTypeTag(drillInfo.drill_type)">
          {{ getTypeLabel(drillInfo.drill_type) }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="计划时间">{{ formatDate(drillInfo.planned_at) }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="getStatusTag(drillInfo.status)">{{ getStatusLabel(drillInfo.status) }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="地点" :span="2">{{ drillInfo.location || '-' }}</el-descriptions-item>
      <el-descriptions-item label="参与人数" :span="2">{{ drillInfo.participant_count || 0 }}人</el-descriptions-item>
      <el-descriptions-item label="实际开始">{{ formatDate(drillInfo.actual_start_at) || '未开始' }}</el-descriptions-item>
      <el-descriptions-item label="实际结束">{{ formatDate(drillInfo.actual_end_at) || '未完成' }}</el-descriptions-item>
      <el-descriptions-item label="当前阶段" :span="2">
        <el-tag v-if="drillInfo.status === 'planned'" type="info">准备阶段</el-tag>
        <el-tag v-else-if="drillInfo.status === 'ongoing'" type="warning">执行中</el-tag>
        <el-tag v-else-if="drillInfo.status === 'completed'" type="success">已完成</el-tag>
        <el-tag v-else-if="drillInfo.status === 'cancelled'" type="danger">已取消</el-tag>
      </el-descriptions-item>
    </el-descriptions>

    <!-- 执行控制区 -->
    <el-card class="action-card" shadow="never" v-if="showActions()">
      <template #header>操作控制</template>
      <div class="action-buttons">
        <PermissionButton permission="drill:execute" type="success" @click="triggerStartExecute">开始执行</PermissionButton>
        <PermissionButton v-if="canComplete()" permission="drill:execute" type="warning" @click="triggerCompleteDrill">完成演练</PermissionButton>
        <PermissionButton v-if="canCancel()" permission="drill:update" type="danger" plain @click="triggerCancelDrill">取消演练</PermissionButton>
      </div>
    </el-card>

    <!-- 现场总结 -->
    <el-descriptions v-if="drillInfo?.summary" :column="1" border style="margin-top: 20px">
      <el-descriptions-item label="现场总结">{{ drillInfo.summary }}</el-descriptions-item>
    </el-descriptions>

    <!-- 照片列表 -->
    <div v-if="photos.length > 0" class="media-section">
      <h4>📷 现场照片</h4>
      <el-row :gutter="16">
        <el-col :span="8" v-for="(photo, idx) in photos" :key="idx">
          <el-image :src="photo.url" fit="cover" style="width: 100%; height: 150px" />
          <div class="caption">{{ photo.caption }}</div>
        </el-col>
      </el-row>
    </div>

    <!-- 视频列表 -->
    <div v-if="videos.length > 0" class="media-section">
      <h4>🎥 现场视频</h4>
      <el-row :gutter="16">
        <el-col :span="24" v-for="(video, idx) in videos" :key="idx">
          <video controls :src="video.url" style="width: 100%" />
          <div class="caption">{{ video.caption }}</div>
        </el-col>
      </el-row>
    </div>

    <!-- 参与人员 -->
    <el-card class="participant-card" shadow="never" style="margin-top: 20px">
      <template #header>
        <span class="card-header-title">参与人员 ({{ participants?.length }}人)</span>
        <PermissionButton permission="drill:execute" size="small" @click="openAddParticipant">添加人员</PermissionButton>
      </template>
      <el-table :data="participants" stripe>
        <el-table-column prop="user_id" label="用户 ID" width="100" />
        <el-table-column prop="role" label="参与角色" min-width="150" />
        <el-table-column prop="sign_in_at" label="签到时间" width="180">
          <template #default="{ row }">{{ formatDate(row.sign_in_at) || '-' }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 评估结果 -->
    <el-card class="evaluation-card" shadow="never" style="margin-top: 20px">
      <template #header>
        <span class="card-header-title">评估结果</span>
        <PermissionButton permission="drill:evaluate" size="small" @click="triggerEvaluate">提交评估</PermissionButton>
      </template>
      <div v-if="evaluation">
        <el-result :title="`总分：${evaluation.total_score}分 / ${maxTotalScore}`" icon="success">
          <template #sub-title>总体评估摘要：{{ evaluation.evaluation_summary || '-' }}</template>
        </el-result>
        <div class="items-list">
          <div v-for="(item, idx) in evaluation.items" :key="idx" class="score-item">
            <span>{{ item.label }}</span>
            <span>{{ item.score }}/{{ item.max_score }}分（{{ (item.score/item.max_score*100).toFixed(0) }}%）</span>
          </div>
        </div>
        <div v-if="evaluation.problems" class="section-box warning"><strong>⚠️ 存在问题：</strong>{{ evaluation.problems }}</div>
        <div v-if="evaluation.improvements" class="section-box info"><strong>💡 改进措施：</strong>{{ evaluation.improvements }}</div>
      </div>
      <el-empty v-else description="暂无评估数据" />
    </el-card>

    <template #footer>关闭</template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PermissionButton from '@/components/PermissionButton.vue'
import { getDrillDetail, executeDrill, completeDrill as apiCompleteDrill, cancelDrill as apiCancelDrill, addDrillParticipant, signInDrillParticipant } from '@/api/drill'

const props = defineProps({
  modelValue: Boolean,
  drillId: Number,
})

const emit = defineEmits(['update:modelValue', 'completed'])

const visible = computed({
  get: () => props.modelValue,
  set: val => emit('update:modelValue', val),
})

const drillInfo = ref(null)
const participants = ref([])
const evaluation = ref(null)
const loading = ref(false)

const dialogTitle = computed(() => `演练详情 - ${drillInfo.value?.drill_name || ''}`)

const maxTotalScore = computed(() => {
  const items = evaluation.value?.items || []
  return items.reduce((sum, item) => sum + item.max_score, 0)
})

const photos = computed(() => drillInfo.value?.photos || [])
const videos = computed(() => drillInfo.value?.videos || [])

// ==================== 辅助函数 ====================

function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

function getTypeLabel(type) {
  const map = { evacuation: '疏散演练', firefighting: '灭火演练', comprehensive: '综合演练' }
  return map[type] || type
}

function getTypeTag(type) {
  const map = { evacuation: 'primary', firefighting: 'success', comprehensive: 'warning' }
  return map[type] || 'info'
}

function getStatusLabel(status) {
  const map = { planned: '计划中', ongoing: '执行中', completed: '已完成', cancelled: '已取消' }
  return map[status] || status
}

function getStatusTag(status) {
  const map = { planned: 'info', ongoing: 'warning', completed: 'success', cancelled: 'danger' }
  return map[status] || 'info'
}

// ==================== 数据加载 ====================

async function loadDetail() {
  if (!props.drillId) return
  loading.value = true
  try {
    const res = await getDrillDetail(props.drillId)
    const data = res.data || {}
    drillInfo.value = data
    participants.value = data.participants || []
    evaluation.value = data.evaluation || null
  } catch (err) {
    console.error(err)
    ElMessage.error('获取详情失败')
  } finally {
    loading.value = false
  }
}

// ==================== 执行控制 ====================

function showActions() {
  const s = drillInfo.value?.status
  return ['planned', 'ongoing'].includes(s) || s === 'completed'
}

function canComplete() { return drillInfo.value?.status === 'ongoing' }
function canCancel() {
  const s = drillInfo.value?.status
  return ['planned', 'ongoing'].includes(s)
}

function triggerStartExecute() {
  ElMessageBox.confirm('确认开始执行该演练？将标记为“执行中”并记录现场照片与视频。', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(async () => {
    try {
      await executeDrill(props.drillId, {})
      ElMessage.success('演练已开始执行')
      loadDetail()
    } catch (err) {
      ElMessage.error(err.message || '执行失败')
    }
  }).catch(() => {})
}

function triggerCompleteDrill() {
  ElMessageBox.prompt('请填写演练总结（含现场情况、成效等）', '完成演练', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '请描述演练情况...',
  }).then(async ({ value }) => {
    try {
      await apiCompleteDrill(props.drillId, { summary: value })
      ElMessage.success('演练已完成')
      loadDetail()
      emit('completed')
    } catch (err) {
      ElMessage.error(err.message || '完成失败')
    }
  }).catch(() => {})
}

function triggerCancelDrill() {
  ElMessageBox.prompt('请输入取消原因', '取消演练', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '取消原因',
  }).then(async ({ value }) => {
    try {
      await apiCancelDrill(props.drillId, { reason: value })
      ElMessage.success('演练已取消')
      loadDetail()
      emit('completed')
    } catch (err) {
      ElMessage.error(err.message || '取消失败')
    }
  }).catch(() => {})
}

function openAddParticipant() {
  ElMessageBox.prompt('请输入用户 ID（需先有系统用户）', '添加参与人员', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPattern: /^[1-9]\d*$/,
    inputErrorMessage: '请输入有效的用户 ID',
  }).then(async ({ value }) => {
    try {
      const role = prompt('请输入参与角色（如：指挥员、疏散员、操作员等）：')
      if (!role) throw new Error('必须输入角色')
      await addDrillParticipant(props.drillId, { user_id: parseInt(value) }, role)
      ElMessage.success('参与人员已添加')
      loadDetail()
    } catch (err) {
      if (err !== 'cancel') {
        ElMessage.error(err.message || '添加失败')
      }
    }
  }).catch(() => {})
}

function triggerEvaluate() {
  emit('evaluate-request')
}

function handleClose() {
  loadDetail() // 重新加载以保持最新数据
}

onMounted(() => {
  if (visible.value && props.drillId) {
    loadDetail()
  }
})
</script>

<style scoped lang="scss">
.page-container { padding: 20px }
.action-card { margin-top: 20px }
.action-buttons { display: flex; gap: 10px }
.media-section { margin-top: 20px }
.media-section h4 { margin-bottom: 15px; color: #333 }
.caption { text-align: center; margin-top: 8px; color: #666; font-size: 12px }
.participant-card { margin-top: 20px }
.card-header-title { font-weight: bold }
.evaluation-card { margin-top: 20px }
.items-list { margin: 20px 0 }
.score-item { display: flex; justify-content: space-between; padding: 10px; border-bottom: 1px dashed #eee }
.section-box { padding: 15px; border-radius: 5px; margin-top: 15px }
.section-box.warning { background: #fff5f5; border: 1px solid #feca57; color: #c0392b }
.section-box.info { background: #e8f8f5; border: 1px solid #2ecc71; color: #16a085 }
</style>
