<template>
  <div class="device-map">
    <div ref="mapEl" class="device-map__canvas" />
    <div v-if="loading" class="device-map__mask">点位加载中…</div>
    <div class="device-map__legend map-legend">
      <span v-for="item in LEGEND" :key="item.value">
        <span class="alarm-dot" :class="`alarm-dot--${item.value}`" />{{ item.label }}
      </span>
      <span v-if="total > points.length" class="device-map__hint">
        视口外仍有 {{ total - points.length }} 台设备，请放大后再看
      </span>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet.markercluster'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'
import { bboxQuery, imageBounds, pixelToLatLng } from '@/utils/geo'
import { deviceStatusLabel } from '@/utils/device'

const props = defineProps({
  meta: { type: Object, default: null },
  points: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
  /** 未收敛报警的设备 id 集合，用于实时标红 */
  activeAlarmDeviceIds: { type: Object, default: () => new Set() },
  /** device_id → { status } 实时状态补丁 */
  statusPatches: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['viewport', 'select-device'])

/** 超过该点位数才启用客户端聚合（后端已按视口上限做网格聚合） */
const CLUSTER_THRESHOLD = 500

const LEGEND = [
  { value: 'normal', label: deviceStatusLabel('normal') },
  { value: 'fire', label: '火警/报警' },
  { value: 'fault', label: deviceStatusLabel('fault') },
  { value: 'shield', label: deviceStatusLabel('shield') },
  { value: 'offline', label: deviceStatusLabel('offline') },
]

const mapEl = ref(null)
let map = null
let overlay = null
let pointLayer = null

function baseSize() {
  return {
    width: props.meta?.map_image_width || 1000,
    height: props.meta?.map_image_height || 600,
  }
}

function markerClass(point) {
  const status = props.statusPatches[point.id]?.status || point.status
  if (props.activeAlarmDeviceIds.has(point.id) || point.has_active_alarm) {
    return `device-marker device-marker--${point.alarm_type === 'fault' ? 'fault' : 'alarm'}`
  }
  if (status === 'fault' || status === 'shield' || status === 'offline') {
    return `device-marker device-marker--${status}`
  }
  return 'device-marker'
}

function iconFor(point) {
  const isCluster = Number(point.count || 1) > 1
  return L.divIcon({
    className: isCluster ? 'device-marker device-marker--cluster' : markerClass(point),
    html: isCluster
      ? `<div class="device-marker__pin">${point.count}</div>`
      : '<div class="device-marker__pin"></div>',
    iconSize: isCluster ? [28, 28] : [18, 18],
    iconAnchor: isCluster ? [14, 14] : [9, 9],
  })
}

function redraw() {
  if (!map) return
  if (pointLayer) {
    pointLayer.remove()
    pointLayer = null
  }
  const { width, height } = baseSize()
  const origin = props.meta?.map_origin
  const useCluster = props.points.length > CLUSTER_THRESHOLD
  pointLayer = useCluster ? L.markerClusterGroup({ chunkedLoading: true }) : L.layerGroup()

  for (const point of props.points) {
    if (point.map_x == null || point.map_y == null) continue
    const marker = L.marker(pixelToLatLng(point.map_x, point.map_y, width, height, origin), {
      icon: iconFor(point),
      title: `${point.device_name || point.device_code}（${deviceStatusLabel(
        props.statusPatches[point.id]?.status || point.status
      )}）`,
      alt: point.device_code,
    })
    marker.on('click', () => emit('select-device', point))
    pointLayer.addLayer(marker)
  }
  pointLayer.addTo(map)
}

function syncBasemap() {
  if (!map) return
  const { width, height } = baseSize()
  const bounds = imageBounds(width, height)
  if (overlay) {
    overlay.remove()
    overlay = null
  }
  if (props.meta?.map_image_url) {
    overlay = L.imageOverlay(props.meta.map_image_url, bounds, { interactive: false }).addTo(map)
  }
  map.setMaxBounds(bounds)
  map.fitBounds(bounds)
  if (props.meta?.map_image_url) map.invalidateSize()
}

function emitViewport() {
  if (!map) return
  const { width, height } = baseSize()
  emit('viewport', bboxQuery(map.getBounds(), width, height, props.meta?.map_origin))
}

function initMap() {
  map = L.map(mapEl.value, {
    crs: L.CRS.Simple,
    // 平面图单位为像素，缩放级别必须能小数步进，否则放大倍率跳档过大
    zoomSnap: 0.25,
    minZoom: -2,
    maxZoom: 4,
    attributionControl: false,
    maxBoundsViscosity: 0.8,
  })
  map.on('moveend zoomend', emitViewport)
  syncBasemap()
  redraw()
  emitViewport()
}

watch(
  () => [props.meta?.map_image_url, props.meta?.map_image_width, props.meta?.map_image_height],
  syncBasemap
)
// points / statusPatches / activeAlarmDeviceIds 都整体替换引用，无需 deep 遍历点位
watch(() => [props.points, props.statusPatches, props.activeAlarmDeviceIds], redraw)

onMounted(initMap)

onBeforeUnmount(() => {
  if (!map) return
  map.off()
  map.remove()
  map = null
  overlay = null
  pointLayer = null
})
</script>

<style lang="scss" scoped>
.device-map {
  position: relative;

  &__canvas {
    height: 560px;
    background: #f5f7fa;
    border: 1px solid #ebeef5;
    border-radius: 4px;
  }

  &__mask {
    position: absolute;
    top: 8px;
    right: 8px;
    padding: 2px 8px;
    font-size: 12px;
    color: #606266;
    background: rgba(255, 255, 255, 0.85);
    border-radius: 3px;
  }

  &__legend {
    margin-top: 10px;
  }

  &__hint {
    color: #e6a23c;
  }
}
</style>
