<template>
  <div class="page-container alarm-center">
    <el-card class="search-card" shadow="never">
      <el-form :model="filters" inline>
        <el-form-item label="报警类型">
          <el-select v-model="filters.alarm_type" placeholder="全部类型" clearable style="width: 130px">
            <el-option
              v-for="item in ALARM_TYPE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="filters.alarm_level" placeholder="全部级别" clearable style="width: 120px">
            <el-option
              v-for="item in ALARM_LEVEL_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="filters.status"
            placeholder="全部状态"
            multiple
            collapse-tags
            clearable
            style="width: 200px"
          >
            <el-option
              v-for="item in ALARM_STATUS_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="区域">
          <el-cascader
            v-model="filters.org_id"
            :options="orgOptions"
            :props="cascaderProps"
            placeholder="全部区域"
            clearable
            style="width: 200px"
          />
        </el-form-item>
        <el-form-item label="报警时间">
          <el-date-picker
            v-model="filters.range"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 380px"
          />
        </el-form-item>
        <el-form-item label="含演练">
          <el-switch v-model="filters.include_drill" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>报警记录（共 {{ pagination.total }} 条）</span>
          <div class="card-header__right">
            <el-tag :type="store.connected ? 'success' : 'info'" size="small" effect="plain">
              {{ store.connected ? '实时推送已连接' : '实时推送未连接' }}
            </el-tag>
            <el-checkbox v-model="unresolvedOnly">只看未收敛</el-checkbox>
          </div>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="rows"
        :row-class-name="rowClassName"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="device_code" label="设备编码" width="140" />
        <el-table-column prop="device_name" label="设备名称" min-width="140" show-overflow-tooltip />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <span class="alarm-dot" :class="`alarm-dot--${row.alarm_type}`" />
            {{ alarmTypeLabel(row.alarm_type) }}
          </template>
        </el-table-column>
        <el-table-column label="级别" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="alarmLevelTag(row.alarm_level)" size="small" effect="dark">
              {{ alarmLevelLabel(row.alarm_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="alarmStatusTag(row.status)" size="small">{{ row.statusLabel }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="org_name" label="区域" width="120" show-overflow-tooltip />
        <el-table-column prop="location_description" label="位置描述" min-width="140" show-overflow-tooltip />
        <el-table-column label="报警时间" width="160">
          <template #default="{ row }">{{ formatAlarmTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="演练/消音" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_drill" size="small" type="info">演练</el-tag>
            <el-tag v-if="isSilenced(row)" size="small" type="info" effect="plain">已消音</el-tag>
            <span v-if="!row.is_drill && !isSilenced(row)">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openRow(row)">详情</el-button>
            <el-button
              v-if="row.status === 'pending'"
              v-permission="'alarm:confirm'"
              link
              type="danger"
              @click="openConfirm(row)"
            >
              确认
            </el-button>
            <el-button
              v-if="canSilence(row)"
              v-permission="'alarm:silence'"
              link
              type="warning"
              @click="handleSilence(row)"
            >
              消音
            </el-button>
            <el-button
              v-if="row.status !== 'resolved'"
              v-permission="'alarm:reset'"
              link
              type="success"
              @click="openReset(row)"
            >
              复位
            </el-button>
            <el-button
              v-if="row.device_id"
              v-permission="'device:view'"
              link
              type="info"
              @click="gotoDevice(row)"
            >
              设备
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :page-sizes="[10, 20, 50, 100]"
        :total="pagination.total"
        layout="total, sizes, prev, pager, next, jumper"
        class="pagination"
        @size-change="handleSizeChange"
        @current-change="loadAlarms"
      />
    </el-card>

    <!-- 详情 -->
    <el-dialog v-model="detailVisible" title="报警详情" width="620px">
      <el-descriptions v-if="current" :column="2" border size="small">
        <el-descriptions-item label="设备">
          {{ current.device_name }}（{{ current.device_code }}）
        </el-descriptions-item>
        <el-descriptions-item label="区域">{{ current.org_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ alarmTypeLabel(current.alarm_type) }}</el-descriptions-item>
        <el-descriptions-item label="级别">{{ alarmLevelLabel(current.alarm_level) }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ alarmStatusLabel(current.status) }}</el-descriptions-item>
        <el-descriptions-item label="报警时间">
          {{ formatAlarmTime(current.created_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="位置描述" :span="2">
          {{ current.location_description || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="确认人/时间">
          {{ current.confirmed_by || '-' }} / {{ formatAlarmTime(current.confirmed_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="确认结论">
          {{ current.confirm_result === 'real' ? '真实火警' : current.confirm_result === 'false_alarm' ? '误报' : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="误报原因" :span="2">
          {{ current.false_reason || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="消音时间">{{ formatAlarmTime(current.silenced_at) }}</el-descriptions-item>
        <el-descriptions-item label="复位时间">{{ formatAlarmTime(current.reset_at) }}</el-descriptions-item>
        <el-descriptions-item label="复位备注" :span="2">
          {{ current.reset_remark || '-' }}
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 确认（FR-025 / FR-026） -->
    <el-dialog v-model="confirmVisible" title="报警确认" width="520px">
      <el-form :model="confirmForm" label-width="96px">
        <el-form-item label="报警">
          <span>{{ current?.device_name }}｜{{ alarmTypeLabel(current?.alarm_type) }}</span>
        </el-form-item>
        <el-form-item label="确认结论">
          <el-radio-group v-model="confirmForm.confirm_result">
            <el-radio value="real" :disabled="current?.is_drill">现场属实</el-radio>
            <el-radio value="false_alarm">误报</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="confirmForm.confirm_result === 'false_alarm'">
          <el-form-item label="误报原因">
            <el-select v-model="confirmForm.false_reason" placeholder="请选择原因" style="width: 100%">
              <el-option v-for="item in FALSE_REASON_OPTIONS" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item label="补充说明">
            <el-input
              v-model="confirmForm.remark"
              type="textarea"
              :rows="2"
              maxlength="255"
              placeholder="选填，将与误报原因一并留痕"
            />
          </el-form-item>
        </template>
        <el-alert
          v-if="current?.is_drill"
          title="演练告警"
          type="warning"
          :closable="false"
          show-icon
        >
          这是演练告警，不能确认为真实火警，也不会创建应急处置事件。
        </el-alert>
        <el-alert v-else-if="confirmForm.confirm_result === 'real'" title="提示" type="info" :closable="false" show-icon>
          确认为真实火警后，系统将自动创建<strong>应急处置事件</strong>，并启动处置流程。
        </el-alert>
      </el-form>
      <template #footer>
        <el-button @click="confirmVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitConfirm">提交确认</el-button>
      </template>
    </el-dialog>

    <!-- 复位（FR-016.2） -->
    <el-dialog v-model="resetVisible" title="系统复位" width="520px">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="复位会把报警置为已解决并使设备回到正常状态"
        description="请先确认现场设备物理状态已恢复，否则复位后设备仍处于报警状态会被重新上报。"
      />
      <el-form :model="resetForm" label-width="52px" class="reset-form">
        <el-checkbox v-model="resetForm.physical_restored">
          我已确认现场设备物理状态恢复正常
        </el-checkbox>
        <el-form-item label="备注">
          <el-input
            v-model="resetForm.remark"
            type="textarea"
            :rows="2"
            maxlength="255"
            placeholder="选填，复位留痕"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!resetForm.physical_restored"
          :loading="submitting"
          @click="submitReset"
        >
          确认复位
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ALARM_LEVEL_OPTIONS,
  ALARM_STATUS_OPTIONS,
  ALARM_TYPE_OPTIONS,
  FALSE_REASON_OPTIONS,
  alarmIdOf,
  alarmLevelLabel,
  alarmLevelTag,
  alarmStatusLabel,
  alarmStatusTag,
  alarmTypeLabel,
  formatAlarmTime,
  isSilenced,
} from '@/utils/alarm'
import { getAlarm, getAlarms, confirmAlarm, resetAlarm, silenceAlarm } from '@/api/alarm'
import { getOrganizationTree } from '@/api/organization'
import { sortAlarms, useMonitorStore } from '@/stores/monitor'
import { stripEmptyChildren } from '@/utils/device'

const cascaderProps = {
  label: 'org_name',
  value: 'id',
  children: 'children',
  checkStrictly: true,
  emitPath: false,
}

const UNRESOLVED_STATUSES = ['pending', 'confirmed', 'processing']

const route = useRoute()
const router = useRouter()
const store = useMonitorStore()

const loading = ref(false)
const submitting = ref(false)
const list = ref([])
const orgOptions = ref([])
const unresolvedOnly = ref(false)

const filters = reactive({
  alarm_type: null,
  alarm_level: null,
  status: [],
  org_id: null,
  range: null,
  include_drill: false,
})
const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const detailVisible = ref(false)
const confirmVisible = ref(false)
const resetVisible = ref(false)
const current = ref(null)

const confirmForm = reactive({ confirm_result: 'real', false_reason: null, remark: '' })
const resetForm = reactive({ physical_restored: false, remark: '' })

const statusFilterValue = computed(() =>
  unresolvedOnly.value ? UNRESOLVED_STATUSES : filters.status
)

/**
 * 服务端分页 + WS 增量：
 * 同一报警以推送数据为准（状态更新更及时），推送里新增且匹配筛选的报警直接插入当前页顶部。
 * 带区域筛选时不插入，因为推送帧只带设备所在楼层，跨层继承关系只有后端解析得准。
 */
const rows = computed(() => {
  const live = store.alarms
    .filter((item) => !filters.org_id || item.org_id === filters.org_id)
    .filter(matchesFilters)
    .map((item) => ({ ...item, id: alarmIdOf(item), statusLabel: alarmStatusLabel(item.status) }))
  const merged = new Map()
  for (const item of list.value) merged.set(alarmIdOf(item), { ...item, statusLabel: alarmStatusLabel(item.status) })
  for (const item of live) merged.set(item.id, { ...merged.get(item.id), ...item })
  return sortAlarms([...merged.values()])
})

onMounted(() => {
  loadAlarms()
  loadOrgTree()
  store.acquire()
})

onBeforeUnmount(() => store.release())

// 大屏「处置」跳转带 alarm_id，直接打开该条详情
watch(
  () => route.query.alarm_id,
  async (value) => {
    if (!value) return
    try {
      const res = await getAlarm(value)
      if (res.data) openRow(res.data)
    } catch {
      // 深链失败只影响弹窗自动打开，列表仍可手动查询
    }
  },
  { immediate: true }
)

function matchesFilters(item) {
  if (filters.alarm_type && item.alarm_type !== filters.alarm_type) return false
  if (filters.alarm_level && item.alarm_level !== filters.alarm_level) return false
  const statuses = statusFilterValue.value
  if (statuses.length && !statuses.includes(item.status)) return false
  if (!filters.include_drill && item.is_drill) return false
  if (filters.range?.length === 2) {
    const time = Date.parse(item.created_at || '')
    const [start, end] = filters.range.map((value) => Date.parse(value))
    if (Number.isNaN(time) || time < start || time > end) return false
  }
  return true
}

function buildParams() {
  const [start, end] = filters.range || []
  return {
    page: pagination.page,
    page_size: pagination.page_size,
    alarm_type: filters.alarm_type || undefined,
    alarm_level: filters.alarm_level || undefined,
    status: statusFilterValue.value.length ? statusFilterValue.value.join(',') : undefined,
    org_id: filters.org_id || undefined,
    start: start || undefined,
    end: end || undefined,
    include_drill: filters.include_drill,
  }
}

async function loadAlarms() {
  loading.value = true
  try {
    const res = await getAlarms(buildParams())
    const data = res.data || {}
    list.value = data.items || []
    pagination.total = data.total || 0
  } catch (err) {
    ElMessage.error(err.message || '加载报警列表失败')
  } finally {
    loading.value = false
  }
}

async function loadOrgTree() {
  try {
    const res = await getOrganizationTree()
    orgOptions.value = stripEmptyChildren(res.data || [])
  } catch (err) {
    ElMessage.error(err.message || '加载组织架构失败')
  }
}

function handleSearch() {
  pagination.page = 1
  loadAlarms()
}

function handleReset() {
  filters.alarm_type = null
  filters.alarm_level = null
  filters.status = []
  filters.org_id = null
  filters.range = null
  filters.include_drill = false
  unresolvedOnly.value = false
  handleSearch()
}

function handleSizeChange(size) {
  pagination.page_size = size
  pagination.page = 1
  loadAlarms()
}

function rowClassName({ row }) {
  return isPendingFireRow(row) ? 'alarm-row--breathing' : ''
}

function isPendingFireRow(row) {
  return row.status === 'pending' && row.alarm_type === 'fire' && !isSilenced(row)
}

/** 消音只对仍未收敛且未消音的报警有意义（FR-016.1） */
function canSilence(row) {
  return !isSilenced(row) && UNRESOLVED_STATUSES.includes(row.status)
}

function openRow(row) {
  current.value = row
  detailVisible.value = true
}

function openConfirm(row) {
  current.value = row
  // 演练告警不能确认为真实火警（后端同口径拒绝），默认落在误报上，
  // 免得用户一点「提交确认」就撞 400
  confirmForm.confirm_result = row?.is_drill ? 'false_alarm' : 'real'
  confirmForm.false_reason = null
  confirmForm.remark = ''
  confirmVisible.value = true
}

function openReset(row) {
  current.value = row
  resetForm.physical_restored = false
  resetForm.remark = ''
  resetVisible.value = true
}

async function submitConfirm() {
  if (confirmForm.confirm_result === 'false_alarm' && !confirmForm.false_reason) {
    ElMessage.warning('确认为误报时必须选择误报原因')
    return
  }
  submitting.value = true
  try {
    await confirmAlarm(alarmIdOf(current.value), {
      confirm_result: confirmForm.confirm_result,
      false_reason:
        confirmForm.confirm_result === 'false_alarm'
          ? [confirmForm.false_reason, confirmForm.remark].filter(Boolean).join('：')
          : undefined,
    })
    ElMessage.success('确认成功')
    confirmVisible.value = false
    await loadAlarms()
  } catch (err) {
    ElMessage.error(err.message || '确认失败')
  } finally {
    submitting.value = false
  }
}

async function submitReset() {
  submitting.value = true
  try {
    await resetAlarm(alarmIdOf(current.value), {
      physical_restored: resetForm.physical_restored,
      remark: resetForm.remark || undefined,
    })
    ElMessage.success('复位成功')
    resetVisible.value = false
    await loadAlarms()
  } catch (err) {
    ElMessage.error(err.message || '复位失败')
  } finally {
    submitting.value = false
  }
}

async function handleSilence(row) {
  try {
    await silenceAlarm(alarmIdOf(row))
    store.markSilenced({ alarm_id: alarmIdOf(row) })
    ElMessage.success('已消音，报警状态保持不变')
  } catch (err) {
    ElMessage.error(err.message || '消音失败')
  }
}

function gotoDevice(row) {
  router.push({ path: '/device/archive', query: { detail: row.device_id } })
}

watch(unresolvedOnly, handleSearch)
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20px;
}

.search-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;

  &__right {
    display: flex;
    align-items: center;
    gap: 12px;
  }
}

.table-card {
  .pagination {
    margin-top: 16px;
    justify-content: flex-end;
  }
}

.reset-form {
  margin-top: 12px;
}
</style>
