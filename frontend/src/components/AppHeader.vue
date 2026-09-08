<template>
  <el-header class="app-header">
    <div class="header-left">
      <breadcrumb />
    </div>
    <div class="header-right">
      <el-dropdown trigger="click" @command="handleCommand">
        <span class="user-info">
          {{ userInfo?.real_name || userInfo?.username || '用户' }}
          <el-icon class="el-icon--right"><arrow-down /></el-icon>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="profile">个人中心</el-dropdown-item>
            <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </el-header>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { usePermissionStore } from '@/stores/permission'

const router = useRouter()
const authStore = useAuthStore()
const permissionStore = usePermissionStore()

const userInfo = computed(() => authStore.userInfo)

async function handleCommand(command) {
  if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      })
      await authStore.logout()
      permissionStore.resetPermission()
      router.push('/login')
      ElMessage.success('已退出登录')
    } catch {
      // 取消退出
    }
  } else if (command === 'profile') {
    // 预留：个人中心
    ElMessage.info('个人中心功能开发中')
  }
}
</script>

<style lang="scss" scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  padding: 0 20px;

  .header-right {
    .user-info {
      cursor: pointer;
      color: #606266;
      font-size: 14px;
      display: flex;
      align-items: center;
      gap: 4px;

      &:hover {
        color: #c23531;
      }
    }
  }
}
</style>
