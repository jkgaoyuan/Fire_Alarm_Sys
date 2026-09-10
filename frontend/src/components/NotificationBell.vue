<template>
  <div ref="bellRef" class="notification-bell" @click.stop="showDropdown = !showDropdown">
    <!-- 铃铛图标 -->
    <el-badge :value="unreadCount" :max="99" :hidden="unreadCount === 0">
      <el-icon :size="20"><Bell /></el-icon>
    </el-badge>

    <!-- 未读红点动画 -->
    <span v-if="unreadCount > 0" class="notification-dot" />

    <!-- 下拉通知列表 -->
    <div v-show="showDropdown" class="notification-dropdown">
      <div class="dropdown-header">
        <span class="title">消息通知</span>
        <el-button link type="primary" size="small" @click.stop="markAllRead()">全部已读</el-button>
      </div>

      <div class="notification-list">
        <div v-if="notifications.length === 0" class="empty-state">
          <el-empty description="暂无消息" :image-size="80" />
        </div>

        <el-scrollbar v-else height="400px">
          <div
            v-for="msg in notifications"
            :key="msg.id"
            class="notification-item"
            :class="{ unread: !msg.is_read }"
            @click.stop="handleClick(msg)"
          >
            <el-badge is-dot class="item-badge" :hidden="msg.is_read" />
            <div class="content">
              <div class="message-title">{{ msg.title }}</div>
              <div class="message-desc">{{ messageContent(msg) }}</div>
            </div>
            <div class="timestamp">{{ formatTime(msg.created_at) }}</div>
          </div>
        </el-scrollbar>
      </div>

      <div class="dropdown-footer">
        <el-button link type="primary" size="small">查看更多 →</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell } from '@element-plus/icons-vue'
import { getNotifications, markNotificationRead, markNotificationsAsRead } from '@/api/emergency'

const showDropdown = ref(false)
const notifications = ref([])
const bellRef = ref(null)

const unreadCount = computed(() => notifications.value.filter((n) => !n.is_read).length)

async function loadNotifications() {
  try {
    const res = await getNotifications({ page: 1, page_size: 50 })
    notifications.value = res.data?.items || []
  } catch (err) {
    // 通知加载失败不打断页面，仅控制台留痕
    console.warn('加载通知失败:', err)
  }
}

function messageContent(msg) {
  // 根据事件类型生成不同的提示文本
  switch (msg.category) {
    case 'emergency_escalation':
      return `应急升级：报警 #${msg.alarm_id} 超时未确认`
    case 'emergency_created':
      return `应急事件 #${msg.event_no} 已生成`
    case 'timeline_node_added':
      return `处置记录：${msg.title}`
    default:
      return msg.title
  }
}

function formatTime(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date

  // 小于 60 秒
  if (diffMs < 60000) return `${Math.floor(diffMs / 1000)}秒前`
  // 小于 60 分钟
  if (diffMs < 3600000) return `${Math.floor(diffMs / 60000)}分钟前`
  // 小于 24 小时
  if (diffMs < 86400000) return `${Math.floor(diffMs / 3600000)}小时前`
  // 超过 24 小时显示完整日期
  return (
    date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) +
    ' ' +
    date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  )
}

async function markAllRead() {
  try {
    await markNotificationsAsRead()
    ElMessage.success('已标记全部为已读')
    await loadNotifications()
  } catch (err) {
    ElMessage.error(err.message || '操作失败')
  }
}

async function handleClick(msg) {
  if (!msg.is_read) {
    try {
      await markNotificationRead(msg.id)
      await loadNotifications()
    } catch (err) {
      console.warn('标记已读失败:', err)
    }
  }
  // TODO: 跳转到对应页面
  showDropdown.value = false
}

// 点击外部关闭下拉框
function closeOnOutsideClick(event) {
  if (bellRef.value && !bellRef.value.contains(event.target)) {
    showDropdown.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', closeOnOutsideClick)
  loadNotifications()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', closeOnOutsideClick)
})
</script>

<style lang="scss" scoped>
.notification-bell {
  position: relative;
  cursor: pointer;
  display: inline-block;
  padding: 8px;
  border-radius: 50%;
  transition: background-color 0.3s;

  &:hover {
    background-color: #f5f7fa;
  }
}

.notification-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 8px;
  height: 8px;
  background-color: #ff0000;
  border-radius: 50%;
  animation: blink 1s infinite;
}

@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}

.notification-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 2000;
  width: 360px;
  background-color: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  box-shadow: 0 12px 32px 4px rgba(0, 0, 0, 0.04), 0 8px 20px rgba(0, 0, 0, 0.08);

  .dropdown-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid #e4e7ed;

    .title {
      font-weight: bold;
      font-size: 14px;
      color: #303133;
    }
  }

  .notification-list {
    .empty-state {
      padding: 40px 20px;
    }

    .notification-item {
      display: flex;
      align-items: flex-start;
      padding: 12px 16px;
      cursor: pointer;
      transition: background-color 0.2s;

      &:hover {
        background-color: #f5f7fa;
      }

      &.unread {
        background-color: #fafcff;
        border-left: 3px solid #409eff;
      }

      .item-badge {
        margin-right: 12px;
        margin-top: 4px;
      }

      .content {
        flex: 1;
        min-width: 0;
      }

      .message-title {
        font-weight: 500;
        font-size: 13px;
        color: #303133;
        margin-bottom: 4px;
      }

      .message-desc {
        font-size: 12px;
        color: #909399;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .timestamp {
        font-size: 11px;
        color: #c0c4cc;
        margin-left: 8px;
        white-space: nowrap;
      }
    }
  }

  .dropdown-footer {
    padding: 12px 16px;
    border-top: 1px solid #e4e7ed;
    text-align: center;
  }
}
</style>
