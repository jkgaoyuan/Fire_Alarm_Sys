<template>
  <div class="login-page">
    <div class="login-box">
      <div class="login-header">
        <h1 class="title">消防监控管理系统</h1>
        <div class="divider" />
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="login-form"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            size="large"
            :prefix-icon="User"
            clearable
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            clearable
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="loading"
            :disabled="isLocked"
            @click="handleLogin"
          >
            {{ isLocked ? `已锁定 (${countdown}s)` : '登 录' }}
          </el-button>
        </el-form-item>

        <div v-if="errorMsg" class="error-msg">
          {{ errorMsg }}
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const formRef = ref()
const loading = ref(false)
const errorMsg = ref('')
const isLocked = ref(false)
const countdown = ref(0)
let countdownTimer = null

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码长度至少 8 位', trigger: 'blur' },
  ],
}

function startCountdown(seconds) {
  isLocked.value = true
  countdown.value = seconds
  countdownTimer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) {
      clearInterval(countdownTimer)
      isLocked.value = false
      errorMsg.value = ''
    }
  }, 1000)
}

async function handleLogin() {
  if (isLocked.value) return

  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  errorMsg.value = ''

  try {
    await authStore.login({
      username: form.username,
      password: form.password,
    })
    ElMessage.success('登录成功')
    // Router guard will automatically redirect to dashboard after routes are loaded
    // No manual navigation needed - let the guard handle it
  } catch (err) {
    const code = err.code
    const data = err.data || {}

    if (code === 4001) {
      // 密码错误
      const remaining = data.remaining_attempts
      errorMsg.value = remaining !== undefined
        ? `用户名或密码错误，剩余 ${remaining} 次尝试`
        : '用户名或密码错误'
    } else if (code === 4003) {
      // 账户锁定
      const lockedUntil = data.locked_until
      if (lockedUntil) {
        const end = new Date(lockedUntil).getTime()
        const now = Date.now()
        const seconds = Math.max(0, Math.ceil((end - now) / 1000))
        errorMsg.value = `账户已锁定，请 ${Math.ceil(seconds / 60)} 分钟后重试`
        startCountdown(seconds)
      } else {
        errorMsg.value = '账户已锁定，请稍后重试'
      }
    } else if (code === 4004) {
      errorMsg.value = '账户已被禁用，请联系管理员'
    } else {
      errorMsg.value = err.message || '登录失败，请重试'
    }
  } finally {
    loading.value = false
  }
}

onBeforeUnmount(() => {
  if (countdownTimer) clearInterval(countdownTimer)
})
</script>

<style lang="scss" scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
}

.login-box {
  width: 420px;
  padding: 48px 40px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;

  .title {
    margin: 0;
    font-size: 24px;
    font-weight: 600;
    color: #1a1a2e;
    letter-spacing: 2px;
  }

  .divider {
    width: 60px;
    height: 3px;
    margin: 12px auto 0;
    background: #c23531;
    border-radius: 2px;
  }
}

.login-form {
  .login-btn {
    width: 100%;
    font-size: 16px;
    font-weight: 500;
    letter-spacing: 4px;
    background: #c23531;
    border-color: #c23531;

    &:hover,
    &:focus {
      background: #d44a46;
      border-color: #d44a46;
    }
  }
}

.error-msg {
  margin-top: 12px;
  text-align: center;
  color: #c23531;
  font-size: 14px;
}
</style>
