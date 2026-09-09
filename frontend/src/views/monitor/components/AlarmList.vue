<template>
  <div v-loading="loading" class="alarm-list">
    <el-empty v-if="!loading && rows.length === 0" description="当前无待处置报警" />
    <transition-group tag="ul" name="alarm-list" class="alarm-list__ul">
      <li
        v-for="alarm in rows"
        :key="alarmKey(alarm)"
        class="alarm-list__item alarm-row"
        :class="rowClass(alarm)"
      >
        <div class="alarm-row__main">
          <span class="alarm-dot" :class="`alarm-dot--${alarm.alarm_type}`" />
          <span class="alarm-row__type">{{ alarmTypeLabel(alarm.alarm_type) }}</span>
          <span class="alarm-row__device" :title="alarm.device_code">
            {{ alarm.device_name || alarm.device_code || `设备 ${alarm.device_id}` }}
          </span>
          <el-tag v-if="alarm.is_drill" size="small" type="info">演练</el-tag>
          <el-tag size="small" :type="alarmStatusTag(alarm.status)">
            {{ alarmStatusLabel(alarm.status) }}
          </el-tag>
          <el-tag v-if="isSilenced(alarm)" size="small" type="info" effect="plain">已消音</el-tag>
        </div>
        <div class="alarm-row__meta">
          <span>{{ formatAlarmTime(alarm.created_at) }}</span>
          <span v-if="alarm.org_name">｜{{ alarm.org_name }}</span>
          <span v-if="alarm.location_description">｜{{ alarm.location_description }}</span>
        </div>
        <div class="alarm-row__actions">
          <el-button
            v-if="canSilence(alarm)"
            v-permission="'alarm:silence'"
            link
            type="warning"
            size="small"
            @click="emit('silence', alarm)"
          >
            消音
          </el-button>
          <el-button link type="primary" size="small" @click="emit('handle', alarm)">处置</el-button>
          <el-button
            v-if="alarm.device_id"
            v-permission="'device:view'"
            link
            type="info"
            size="small"
            @click="emit('focus-device', alarm)"
          >
            设备
          </el-button>
        </div>
      </li>
    </transition-group>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import {
  alarmIdOf,
  alarmStatusLabel,
  alarmStatusTag,
  alarmTypeLabel,
  formatAlarmTime,
  isPendingFire,
  isSilenced,
} from '@/utils/alarm'

const props = defineProps({
  alarms: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['silence', 'handle', 'focus-device'])

// 演练报警默认不占大屏席位（FR-045 隔离），需要时由报警中心查看
const rows = computed(() => props.alarms.filter((item) => !item.is_drill))

/** 大屏帧用 alarm_id、REST 分页用 id */
function alarmKey(alarm) {
  return alarmIdOf(alarm) ?? `${alarm.device_id}-${alarm.created_at}`
}

/** 消音只对仍未收敛且未消音的报警有意义（FR-016.1） */
function canSilence(alarm) {
  return !isSilenced(alarm) && ['pending', 'processing'].includes(alarm.status)
}

function rowClass(alarm) {
  return {
    [`alarm-row--${alarm.alarm_type}`]: true,
    'alarm-row--breathing': isPendingFire(alarm) && !isSilenced(alarm),
    'alarm-row--resolved': alarm.status === 'resolved' || alarm.status === 'false_alarm',
  }
}
</script>

<style lang="scss" scoped>
.alarm-list {
  min-height: 200px;

  &__ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  &__item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-bottom: 1px solid #ebeef5;
    flex-wrap: wrap;
  }
}

.alarm-row {
  &__main {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 320px;
  }

  &__type {
    font-weight: 600;
  }

  &__device {
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__meta {
    flex: 1;
    color: #909399;
    font-size: 12px;
    min-width: 240px;
  }

  &__actions {
    display: flex;
    gap: 4px;
  }
}

/* 新报警滑入（FR-014） */
.alarm-list-enter-active {
  transition: all 0.35s ease-out;
}

.alarm-list-enter-from {
  opacity: 0;
  transform: translateX(-28px);
}

.alarm-list-move {
  transition: transform 0.35s ease;
}
</style>
