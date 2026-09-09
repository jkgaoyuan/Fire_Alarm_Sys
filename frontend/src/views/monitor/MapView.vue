<template>
  <div class="map-view">
    <div class="map-view__bar">
      <div class="map-view__info">
        <span v-if="meta?.resolved_org_name">
          平面图所属楼层：{{ meta.resolved_org_name }}
          <span class="map-view__dim">
            （基准 {{ meta.map_image_width }}×{{ meta.map_image_height }}px）
          </span>
        </span>
        <span v-else class="map-view__dim">未定位到楼层平面图</span>
        <span class="map-view__dim">点位 {{ points.length }} / 共 {{ total }}</span>
      </div>
      <div>
        <el-button size="small" @click="reload">刷新点位</el-button>
        <PermissionButton permission="monitor:config" size="small" type="primary" plain @click="emit('open-setting')">
          配置平面图
        </PermissionButton>
      </div>
    </div>

    <DeviceMap
      v-if="meta?.map_image_url"
      :meta="meta"
      :points="points"
      :total="total"
      :loading="loading"
      :active-alarm-device-ids="store.activeAlarmDeviceIds"
      :status-patches="store.devicePatches"
      @viewport="handleViewport"
      @select-device="openDevice"
    />
    <el-empty v-else description="该区域及其上级楼层尚未上传平面图，请先在「配置平面图」中上传">
      <PermissionButton permission="monitor:config" type="primary" @click="emit('open-setting')">
        上传平面图
      </PermissionButton>
    </el-empty>

    <ArchiveDetail v-model="detailVisible" :device-id="detailDeviceId" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import DeviceMap from '@/components/map/DeviceMap.vue'
import ArchiveDetail from '@/views/device/ArchiveDetail.vue'
import PermissionButton from '@/components/PermissionButton.vue'
import { getMapDevices, getMapMeta } from '@/api/monitor'
import { useMonitorStore } from '@/stores/monitor'

const props = defineProps({
  /** 定位到的楼层/区域节点（语义为"定位到该楼层"，含其全部后代区域） */
  orgId: { type: Number, default: null },
})
const emit = defineEmits(['open-setting', 'focus-device'])

const store = useMonitorStore()

const meta = ref(null)
const points = ref([])
const total = ref(0)
const loading = ref(false)
const bbox = ref('')
const detailVisible = ref(false)
const detailDeviceId = ref(null)

const targetOrgId = computed(() => props.orgId || null)

onMounted(() => {
  loadAll()
})

watch(targetOrgId, () => {
  bbox.value = ''
  loadAll()
})

async function loadAll() {
  await loadMeta()
  await loadPoints()
}

async function loadMeta() {
  if (!targetOrgId.value) {
    meta.value = null
    return
  }
  try {
    const res = await getMapMeta(targetOrgId.value)
    meta.value = res.data
  } catch (err) {
    meta.value = null
    ElMessage.error(err.message || '加载平面图失败')
  }
}

async function loadPoints() {
  if (!targetOrgId.value) {
    points.value = []
    total.value = 0
    return
  }
  loading.value = true
  try {
    const params = { org_id: targetOrgId.value }
    if (bbox.value) params.bbox = bbox.value
    const res = await getMapDevices(params)
    const data = res.data || {}
    points.value = data.items || []
    total.value = data.total || 0
  } catch (err) {
    ElMessage.error(err.message || '加载设备点位失败')
  } finally {
    loading.value = false
  }
}

/** 视口懒加载：拖拽/缩放后只按当前 bbox 重查 */
function handleViewport(nextBbox) {
  if (!nextBbox || nextBbox === bbox.value) return
  bbox.value = nextBbox
  loadPoints()
}

async function reload() {
  await loadMeta()
  await loadPoints()
}

function openDevice(point) {
  if (!point || !point.id) return
  detailDeviceId.value = point.id
  detailVisible.value = true
  emit('focus-device', point)
}

defineExpose({ reload })
</script>

<style lang="scss" scoped>
.map-view {
  &__bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }

  &__info {
    display: flex;
    gap: 16px;
    font-size: 13px;
  }

  &__dim {
    color: #909399;
  }
}
</style>
