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
            <el-select
              v-model="p.user_id"
              placeholder="搜索并选择人员"
              filterable
              :loading="candidatesLoading"
              style="width: 200px"
            >
              <el-option
                v-for="opt in optionsFor(idx)"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
                :disabled="opt.disabled"
              >
                <span>{{ opt.label }}</span>
                <span class="option-note">{{ opt.note }}</span>
              </el-option>
            </el-select>
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
import { createDrill, updateDrill, getDrillDetail, getDrillParticipantCandidates } from '@/api/drill'

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

// 候选人来自演练域自己的端点（不是 GET /users —— 后者要 system:user，
// 值班员/维保员没有，实测 403）。
const candidates = ref([])
const candidatesLoading = ref(false)

async function loadCandidates() {
  candidatesLoading.value = true
  try {
    const res = await getDrillParticipantCandidates()
    candidates.value = res.data || []
  } catch (err) {
    console.error(err)
    ElMessage.error('加载人员列表失败')
  } finally {
    candidatesLoading.value = false
  }
}

function addParticipant() {
  form.participants.push({ user_id: undefined, role: '参与者' })
}

function removeParticipant(idx) {
  form.participants.splice(idx, 1)
}

/**
 * 某一行的下拉选项。
 *
 * 两处讲究：
 * 1. **同一人不能占两行** —— 把别行已选的置为 disabled。后端 create/update
 *    不去重，重复 id 会在 participants JSONB 里存成两条。
 * 2. **回填的人可能已不在候选人里**（被停用/删除）。不补这一项的话，
 *    el-select 匹配不到选项会直接显示**裸用户 ID** —— 正是本次要消除的东西。
 */
function optionsFor(idx) {
  const row = form.participants[idx]
  const takenByOthers = new Set(
    form.participants.filter((_, i) => i !== idx).map(p => p.user_id)
  )

  const opts = candidates.value.map(u => ({
    value: u.id,
    label: u.real_name || u.username,
    note: (u.role_names || []).join('、'),
    disabled: takenByOthers.has(u.id),
  }))

  if (row && row.user_id != null && !candidates.value.some(u => u.id === row.user_id)) {
    opts.unshift({
      value: row.user_id,
      label: row.user_name || `#${row.user_id}`,
      note: '已停用或不存在',
      disabled: false,
    })
  }
  return opts
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
    // user_name 一并留下：该人员若已被停用/删除、不在候选人里时，
    // optionsFor() 用它作为回退显示，避免下拉退化成裸 ID。
    form.participants = (data.participants || []).map(p => ({
      user_id: p.user_id,
      role: p.role,
      user_name: p.user_name,
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
    // 只在弹窗打开时取候选人（不要挂 onMounted —— 那样没打开也会发请求）。
    // 已加载过就不重复拉；上次失败的场景 length 仍为 0，会自然重试。
    if (!candidates.value.length) loadCandidates()
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

  // 参与人员 user_id 必填校验。
  // ⚠️ 刻意**留在 el-form rules 之外**做普通 JS 判断：vite.config.js 一旦缺
  // `test.server.deps.inline: ['element-plus']`（DEC-008），async-validator 的
  // CJS 互操作会失效，el-form 校验在测试里**静默恒为通过**，必填拦截用例就全成假绿。
  const invalidParticipants = form.participants.filter(p => !p.user_id)
  if (invalidParticipants.length > 0) {
    ElMessage.warning('请为所有参与人员选择用户')
    return
  }

  submitLoading.value = true
  try {
    const payload = {
      drill_name: form.drill_name,
      drill_type: form.drill_type,
      planned_at: form.planned_at || undefined,
      location: form.location || undefined,
      // 逐人携带角色。此前只发 participant_user_ids，后端把所有人写死
      // 「参与者」—— 界面上填的角色会被**无声丢弃**。
      participants: form.participants.map(p => ({
        user_id: p.user_id,
        role: p.role || '参与者',
      })),
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
.option-note {
  float: right;
  color: #8492a6;
  font-size: 12px;
}
</style>
