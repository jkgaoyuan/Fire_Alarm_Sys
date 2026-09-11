<!--
演练评估打分弹窗 (3.8-F4)
功能：评估项打分、问题与改进措施、总分计算
权限码：drill:evaluate
-->
<template>
  <el-dialog v-model="visible" :title="`演练评估 - ${drillName}`" width="700px" @close="handleClose">
    <el-form :model="form">
      <!-- 评估项列表 -->
      <div class="items-section">
        <h4>评估项清单</h4>
        <el-row v-for="(item, idx) in form.items" :key="idx" gutter="16">
          <el-col :span="10">
            <el-input v-model="item.label" placeholder="评估项标签" />
          </el-col>
          <el-col :span="5">
            <el-input-number v-model="item.score" :min="0" :max="item.max_score || 10" controls-position="right" />
          </el-col>
          <el-col :span="4">
            <el-input-number v-model="item.max_score" :min="1" controls-position="right" />
          </el-col>
          <el-col :span="5">
            <el-input v-model="item.comment" placeholder="评价说明" style="width: 100%" />
          </el-col>
          <el-col :span="0"><el-button type="danger" plain @click="removeItem(idx)">删除</el-button></el-col>
        </el-row>
        <el-button type="primary" plain @click="addItem">+ 添加评估项</el-button>
      </div>

      <!-- 总分显示 -->
      <div class="total-score-box">当前总分：<strong>{{ totalScore }}</strong> / {{ maxTotalScore }}</div>

      <!-- 问题与改进 -->
      <el-form-item label="存在问题">
        <el-input v-model="form.problems" type="textarea" :rows="4" maxlength="500" show-word-limit placeholder="请描述演练中存在的问题..." />
      </el-form-item>
      <el-form-item label="改进措施">
        <el-input v-model="form.improvements" type="textarea" :rows="4" maxlength="500" show-word-limit placeholder="请提出具体的改进措施..." />
      </el-form-item>
      <el-form-item label="总体评估摘要">
        <el-input v-model="form.evaluation_summary" type="textarea" :rows="4" maxlength="1000" show-word-limit placeholder="提供本次演练的总体评估（OQ-4 新增字段）..." />
      </el-form-item>

      <el-form-item>
        <PermissionButton permission="drill:evaluate" type="primary" @click="handleSubmit" :loading="submitLoading">提交评估</PermissionButton>
        <el-button @click="resetForm">重置</el-button>
      </el-form-item>
    </el-form>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PermissionButton from '@/components/PermissionButton.vue'
import { submitDrillEvaluation, getDrillDetail } from '@/api/drill'

const props = defineProps({
  modelValue: Boolean,
  drillId: Number,
})

const emit = defineEmits(['update:modelValue', 'submitted'])

const visible = computed({
  get: () => props.modelValue,
  set: val => emit('update:modelValue', val),
})

const drillInfo = ref(null)
const submitLoading = ref(false)

const drillName = computed(() => drillInfo.value?.drill_name || '')

const form = reactive({
  items: [], // {label, score, max_score, comment}
  problems: '',
  improvements: '',
  evaluation_summary: '',
})

const totalScore = computed(() => form.items.reduce((sum, item) => sum + (item.score || 0), 0))
const maxTotalScore = computed(() => form.items.reduce((sum, item) => sum + (item.max_score || 0), 0))

// ==================== 辅助函数 ====================

function addItem() {
  form.items.push({ label: '', score: 0, max_score: 10, comment: '' })
}

function removeItem(index) {
  form.items.splice(index, 1)
}

function resetForm() {
  ElMessageBox.confirm('确认重置？已填写内容将丢失。', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(() => {
    form.items.forEach(item => { item.score = 0; item.comment = '' })
    form.problems = ''
    form.improvements = ''
    form.evaluation_summary = ''
  }).catch(() => {})
}

// ==================== 数据加载 ====================

async function loadDrillInfo() {
  if (!props.drillId) return
  try {
    const res = await getDrillDetail(props.drillId)
    drillInfo.value = res.data || null
  } catch (err) {
    console.error(err)
  }
}

// ==================== 提交逻辑 ====================

async function handleSubmit() {
  const invalidItems = form.items.filter(item => !item.label.trim())
  if (invalidItems.length > 0) {
    ElMessage.warning('请填写所有评估项的标签')
    return
  }

  submitLoading.value = true
  try {
    await submitDrillEvaluation({
      drill_id: props.drillId,
      items: form.items.map(item => ({
        item: item.label.toLowerCase().replace(/\s+/g, '_'),
        label: item.label,
        score: item.score,
        max_score: item.max_score,
        comment: item.comment,
      })),
      problems: form.problems || undefined,
      improvements: form.improvements || undefined,
      evaluation_summary: form.evaluation_summary || undefined,
    })
    ElMessage.success('评估提交成功')
    visible.value = false
    emit('submitted')
  } catch (err) {
    console.error(err)
    ElMessage.error(err.message || '提交失败')
  } finally {
    submitLoading.value = false
  }
}

function handleClose() {
  // 关闭时不自动重置，由下一次打开时重置
}

// 弹窗打开时初始化默认评估项并加载演练信息
watch(visible, (val) => {
  if (val && props.drillId) {
    form.items = []
    addItem(); addItem(); addItem(); addItem() // 默认 4 个评估项
    form.problems = ''
    form.improvements = ''
    form.evaluation_summary = ''
    loadDrillInfo()
  }
}, { immediate: true })
</script>

<style scoped lang="scss">
.page-container { padding: 20px }
.info-card { margin-bottom: 20px }
.evaluation-card { margin-top: 20px }
.card-title { font-size: 16px; font-weight: bold }
.items-section { margin-bottom: 30px }
.items-section h4 { margin-bottom: 15px; color: #333 }
.total-score-box { padding: 15px; background: #f5f7fa; border-radius: 5px; text-align: center; margin: 20px 0; font-size: 18px }
</style>
