<template>
  <div class="timeline-editor">
    <!-- 只读模式：仅展示 -->
    <div v-if="readOnly" class="read-only-mode">
      <el-timeline v-if="timelines.length > 0">
        <el-timeline-item
          v-for="node in timelines"
          :key="node.id"
          :timestamp="formatTime(node.created_at)"
          placement="top"
          :type="nodeColor(node.node_type)"
          :hollow="isSystemNode(node.node_type)"
        >
          <el-card shadow="never" class="timeline-card">
            <div class="node-content">
              <span class="node-type">{{ nodeLabel(node.node_type) }}</span>
              <span class="node-detail">{{ nodeDetail(node) }}</span>
            </div>
            <div v-if="node.attachments?.length" class="attachments">
              <el-button link type="primary" size="small" v-for="(att, idx) in node.attachments" :key="idx">
                附件 {{ idx + 1 }}
              </el-button>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>

      <el-empty v-else description="暂无处置记录" />
    </div>

    <!-- 编辑模式：可增删节点 -->
    <div v-else class="edit-mode">
      <div class="toolbar">
        <el-button type="primary" size="small" @click="showAddNodeDialog = true">添加节点</el-button>
        <el-button @click="loadTimelines">刷新</el-button>
      </div>

      <el-timeline v-if="timelines.length > 0">
        <el-timeline-item
          v-for="node in timelines"
          :key="node.id"
          :timestamp="formatTime(node.created_at)"
          placement="top"
          :type="nodeColor(node.node_type)"
        >
          <el-card shadow="never" class="timeline-card">
            <div class="node-content">
              <span class="node-type">{{ nodeLabel(node.node_type) }}</span>
              <span class="node-detail">{{ nodeDetail(node) }}</span>
            </div>
            <div class="node-actions">
              <el-button link type="danger" size="small" @click="deleteNode(node)">删除</el-button>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>

      <el-empty v-else description="暂无处置记录" />
    </div>

    <!-- 添加节点弹窗 -->
    <el-dialog v-model="showAddNodeDialog" title="添加处置节点" width="600px">
      <el-form :model="nodeForm" label-width="100px">
        <el-form-item label="节点类型" required>
          <el-select v-model="nodeForm.node_type" placeholder="请选择" style="width: 100%">
            <el-option v-for="item in NODE_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注信息">
          <el-input
            v-model="nodeForm.remark"
            type="textarea"
            :rows="3"
            maxlength="500"
            placeholder="选填，详细说明"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddNodeDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitAddNode">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { addTimelineNode, getEventTimelines, deleteTimelineNode } from '@/api/emergency'

const props = defineProps({
  eventId: { type: [String, Number], required: true },
  readOnly: { type: Boolean, default: true },
})

const NODE_TYPE_OPTIONS = [
  { label: '报警发生', value: 'alarm_occurred' },
  { label: '人工确认', value: 'manual_confirm' },
  { label: '现场确认', value: 'field_confirmed' },
  { label: '启动联动', value: 'linkage_started' },
  { label: '人员疏散', value: 'evacuation_started' },
  { label: '火情控制', value: 'fire_controlled' },
  { label: '处置完成', value: 'disposal_completed' },
]

const submitting = ref(false)
const timelines = ref([])
const showAddNodeDialog = ref(false)
const nodeForm = reactive({ node_type: null, remark: '' })

async function loadTimelines() {
  try {
    const res = await getEventTimelines(props.eventId)
    timelines.value = res.data || []
  } catch (err) {
    console.error('加载时间轴失败:', err)
  }
}

function nodeColor(nodeType) {
  const map = {
    alarm_occurred: 'warning',
    manual_confirm: 'info',
    field_confirmed: 'success',
    linkage_started: 'primary',
    evacuation_started: 'danger',
    fire_controlled: 'success',
    disposal_completed: 'success',
  }
  return map[nodeType] || 'default'
}

function isSystemNode(nodeType) {
  return ['alarm_occurred'].includes(nodeType)
}

function nodeLabel(nodeType) {
  const option = NODE_TYPE_OPTIONS.find((o) => o.value === nodeType)
  return option?.label || nodeType
}

function nodeDetail(node) {
  if (node.remark) return node.remark
  switch (node.node_type) {
    case 'alarm_occurred':
      return '自动记录报警发生'
    case 'manual_confirm':
      return `值班员 ${node.user_id || '-'} 人工确认`
    case 'field_confirmed':
      return '现场核实真实火警'
    case 'linkage_started':
      return '启动消防联动系统'
    case 'evacuation_started':
      return '组织人员疏散'
    case 'fire_controlled':
      return '火情已控制'
    case 'disposal_completed':
      return '处置流程已完成'
    default:
      return '-'
  }
}

function formatTime(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function submitAddNode() {
  if (!nodeForm.node_type) {
    ElMessage.warning('请选择节点类型')
    return
  }

  submitting.value = true
  try {
    await addTimelineNode(props.eventId, {
      node_type: nodeForm.node_type,
      remark: nodeForm.remark || undefined,
    })

    ElMessage.success('节点添加成功')
    showAddNodeDialog.value = false
    await loadTimelines()
  } catch (err) {
    ElMessage.error(err.message || '添加节点失败')
  } finally {
    submitting.value = false
  }
}

async function deleteNode(node) {
  try {
    await deleteTimelineNode(node.id)
    ElMessage.success('节点删除成功')
    await loadTimelines()
  } catch (err) {
    ElMessage.error(err.message || '删除节点失败')
  }
}

onMounted(() => {
  loadTimelines()
})
</script>

<style lang="scss" scoped>
.timeline-editor {
  .toolbar {
    margin-bottom: 16px;
    text-align: right;
  }

  .timeline-card {
    padding: 12px;

    .node-content {
      display: flex;
      align-items: center;
      gap: 12px;

      .node-type {
        font-weight: bold;
        color: #303133;
      }

      .node-detail {
        color: #606266;
      }
    }

    .node-actions {
      margin-top: 8px;
      text-align: right;
    }
  }

  .attachments {
    margin-top: 8px;
  }
}
</style>
