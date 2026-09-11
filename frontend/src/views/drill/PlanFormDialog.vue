<!--
演练计划表单弹窗 (3.8-F2)
功能：新增/编辑演练计划（名称、类型、时间、地点、参与人员）
权限码：drill:create / drill:update
-->
<template>
  <el-dialog v-model="visible" :title="isEdit ? '编辑演练计划' : '新增演练计划'" width="600px" @close="handleClose">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="演练名称" prop="drill_name">
        <el-input v-model="form.drill_name" placeholder="请输入演练名称" maxlength="100" show-word-limit />
      </el-form-item>

      <el-form-item label="演练类型" prop="drill_type">
        <el-select v-model="form.drill_type" placeholder="请选择演练类型" style="width: 100%">
          <el-option label="疏散演练" value="evacuation" />
          <el-option label="灭火演练" value="firefighting" />
          <el-option label="综合演练" value="comprehensive" />
        </el-select>
      </el-form-item>

      <el-form-item label="计划时间" prop="planned_at">
        <el-date-picker
          v-model="form.planned_at"
          type="datetime"
          placeholder="选择计划执行时间"
          value-format="YYYY-MM-DDTHH:mm:ss"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="演练地点" prop="location">
        <el-input v-model="form.location" placeholder="请输入演练地点" maxlength="255" />
      </el-form-item>

      <el-form-item label="参与人员">
        <div class="participants-editor">
          <div v-for="(p, idx) in form.participants" :key="idx" class="participant-row">
            <el-input-number v-model="p.user_id" :min="1" placeholder="用户 ID" controls-position="right" style="width: 140px" />
            <el-input v-model="p.role" placeholder="角色（如：指挥员）" style="flex: 1" />
            <el-button type="danger" plain size="small" @click="removeParticipant(idx)">删除</el-button>
          </div>
          <el-button type="primary" plain size="small" @click="addParticipant">+ 添加参与人员</el-button>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createDrill, updateDrill, getDrillDetail } from '@/api/drill'

const props = defineProps({
  modelValue: Boolean,
  // 编辑模式时传入 { id }；新增模式传 null
  planData: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'submitted'])

const visible = computed({
  get: () => props.modelValue,
  set: val => emit('update:modelValue', val),
})

const isEdit = computed(() => !!(props.planData && props.planData.id))

const formRef = ref(null)
const submitLoading = ref(false)

const form = reactive({
  drill_name: '',
  drill_type: '',
  planned_at: '',
  location: '',
  participants: [], // [{user_id, role}]
})

const rules = {
  drill_name: [
    { required: true, message: '请输入演练名称', trigger: 'blur' },
    { max: 100, message: '名称不能超过 100 字', trigger: 'blur' },
  ],
  drill_type: [
    { required: true, message: '请选择演练类型', trigger: 'change' },
  ],
}

// ==================== 参与人员编辑 ====================

function addParticipant() {
  form.participants.push({ user_id: undefined, role: '' })
}

function removeParticipant(idx) {
  form.participants.splice(idx, 1)
}

// ==================== 数据回填（编辑模式） ====================

async function loadForEdit(id) {
  try {
    const res = await getDrillDetail(id)
    const data = res.data || {}
    form.drill_name = data.drill_name || ''
    form.drill_type = data.drill_type || ''
    form.planned_at = data.planned_at || ''
    form.location = data.location || ''
    form.participants = (data.participants || []).map(p => ({
      user_id: p.user_id,
      role: p.role,
    }))
  } catch (err) {
    console.error(err)
    ElMessage.error('加载演练详情失败')
  }
}

watch(visible, (val) => {
  if (val) {
    // 重置表单
    form.drill_name = ''
    form.drill_type = ''
    form.planned_at = ''
    form.location = ''
    form.participants = []
    if (isEdit.value && props.planData.id) {
      loadForEdit(props.planData.id)
    }
  }
}, { immediate: true })

// ==================== 提交 ====================

async function handleSubmit() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  // 参与人员 user_id 必填校验
  const invalidParticipants = form.participants.filter(p => !p.user_id)
  if (invalidParticipants.length > 0) {
    ElMessage.warning('请填写所有参与人员的用户 ID')
    return
  }

  submitLoading.value = true
  try {
    const payload = {
      drill_name: form.drill_name,
      drill_type: form.drill_type,
      planned_at: form.planned_at || undefined,
      location: form.location || undefined,
      participant_user_ids: form.participants.map(p => p.user_id),
    }

    if (isEdit.value) {
      await updateDrill(props.planData.id, payload)
    } else {
      await createDrill(payload)
    }
    ElMessage.success(isEdit.value ? '演练计划已更新' : '演练计划已创建')
    visible.value = false
    emit('submitted')
  } catch (err) {
    console.error(err)
    ElMessage.error(err.message || '保存失败')
  } finally {
    submitLoading.value = false
  }
}

function handleClose() {
  formRef.value?.resetFields?.()
}
</script>

<style scoped lang="scss">
.participants-editor {
  width: 100%;
}
.participant-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}
</style>
