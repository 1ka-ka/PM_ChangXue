<script setup lang="ts">
/** 登录/注册（V1.4）：密码/短信双登录 Tab + 注册 + 忘记密码（短信验证码重置）。 */
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiError, post } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const mode = ref<'login' | 'sms' | 'register' | 'reset'>('login')
const loading = ref(false)

const form = reactive({ phone: '', password: '', nickname: '', code: '', newPassword: '' })

function validPhone(): boolean {
  if (!/^1\d{10}$/.test(form.phone)) {
    ElMessage.warning('请输入 11 位手机号')
    return false
  }
  return true
}

// ---- 短信验证码：发送 + 60s 倒计时（登录 scene=2 / 找回 scene=3）----
const smsSending = ref(false)
const countdown = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

async function sendCode(scene: 2 | 3) {
  if (!validPhone()) return
  smsSending.value = true
  try {
    const r = await post<{ debug_code?: string }>('/auth/sms/send', {
      phone: form.phone,
      scene,
    })
    countdown.value = 60
    timer = setInterval(() => {
      countdown.value--
      if (countdown.value <= 0 && timer) clearInterval(timer)
    }, 1000)
    if (r.debug_code) {
      // dev 模式：后端回传验证码，自动填入便于联调（真实短信不会返回）
      form.code = r.debug_code
      ElMessage.success(`开发模式验证码：${r.debug_code}（已自动填入）`)
    } else {
      ElMessage.success('验证码已发送，请注意查收短信')
    }
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '发送失败')
  } finally {
    smsSending.value = false
  }
}

async function submit() {
  if (!validPhone()) return
  if (mode.value === 'login' || mode.value === 'register') {
    if (form.password.length < 8) {
      ElMessage.warning('密码至少 8 位')
      return
    }
  }
  if (mode.value === 'register' && !form.nickname.trim()) {
    ElMessage.warning('请输入昵称')
    return
  }
  if (mode.value === 'sms' && form.code.length < 4) {
    ElMessage.warning('请输入短信验证码')
    return
  }
  if (mode.value === 'reset' && form.newPassword.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }

  loading.value = true
  try {
    if (mode.value === 'login') {
      await auth.login(form.phone, form.password)
      ElMessage.success('欢迎回来')
    } else if (mode.value === 'sms') {
      await auth.smsLogin(form.phone, form.code)
      ElMessage.success('欢迎回来')
    } else if (mode.value === 'register') {
      await auth.register(form.phone, form.password, form.nickname.trim())
      ElMessage.success('注册成功，赠送 50 积分')
    } else {
      await post('/auth/reset-password', {
        phone: form.phone,
        code: form.code,
        new_password: form.newPassword,
      })
      ElMessage.success('密码已重置，请使用新密码登录')
      mode.value = 'login'
      form.password = ''
      return
    }
    // 登录页统一，但登录后区分身份：管理员默认进管理后台，普通用户进广场
    const redirect =
      (route.query.redirect as string) || (auth.user?.is_admin ? '/admin' : '/feed')
    router.replace(redirect)
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <div class="card">
      <h1 class="logo">畅学</h1>
      <p class="slogan">大学生学习问答社区 · 提问、解答、沉淀知识</p>

      <!-- 找回密码视图（无 Tab，返回登录） -->
      <template v-if="mode === 'reset'">
        <h2 class="reset-title">找回密码</h2>
        <el-form @submit.prevent="submit">
          <el-form-item>
            <el-input v-model="form.phone" placeholder="手机号" maxlength="11" size="large">
              <template #prefix><el-icon><Iphone /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item>
            <el-input v-model="form.code" placeholder="短信验证码" maxlength="6" size="large">
              <template #prefix><el-icon><ChatDotRound /></el-icon></template>
              <template #append>
                <el-button :disabled="countdown > 0 || smsSending" @click="sendCode(3)">
                  {{ countdown > 0 ? `${countdown}s 后重发` : smsSending ? '发送中…' : '获取验证码' }}
                </el-button>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item>
            <el-input
              v-model="form.newPassword"
              type="password"
              placeholder="新密码（至少 8 位）"
              show-password
              size="large"
              @keyup.enter="submit"
            >
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-button type="primary" size="large" class="submit" :loading="loading" round @click="submit">
            重置密码
          </el-button>
        </el-form>
        <p class="switch">
          <a @click="mode = 'login'">← 返回登录</a>
        </p>
      </template>

      <!-- 登录/注册视图（三 Tab） -->
      <template v-else>
        <el-tabs v-model="mode" stretch>
          <el-tab-pane label="密码登录" name="login" />
          <el-tab-pane label="短信登录" name="sms" />
          <el-tab-pane label="注册" name="register" />
        </el-tabs>

        <el-form @submit.prevent="submit">
          <el-form-item>
            <el-input v-model="form.phone" placeholder="手机号" maxlength="11" size="large">
              <template #prefix><el-icon><Iphone /></el-icon></template>
            </el-input>
          </el-form-item>

          <el-form-item v-if="mode === 'register'">
            <el-input v-model="form.nickname" placeholder="昵称" maxlength="20" size="large">
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>

          <!-- 短信登录：验证码 + 发送按钮 -->
          <el-form-item v-if="mode === 'sms'">
            <el-input v-model="form.code" placeholder="短信验证码" maxlength="6" size="large">
              <template #prefix><el-icon><ChatDotRound /></el-icon></template>
              <template #append>
                <el-button :disabled="countdown > 0 || smsSending" @click="sendCode(2)">
                  {{ countdown > 0 ? `${countdown}s 后重发` : smsSending ? '发送中…' : '获取验证码' }}
                </el-button>
              </template>
            </el-input>
          </el-form-item>

          <el-form-item v-if="mode !== 'sms'">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="密码（至少 8 位）"
              show-password
              size="large"
              @keyup.enter="submit"
            >
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>

          <el-button type="primary" size="large" class="submit" :loading="loading" round @click="submit">
            {{ mode === 'login' ? '登录' : mode === 'sms' ? '验证并登录' : '注册并登录' }}
          </el-button>
        </el-form>

        <p v-if="mode === 'login'" class="switch">
          <a @click="mode = 'reset'">忘记密码？</a>
        </p>
        <p class="tip">注册即送 50 积分 · 回答被采纳 +30 积分</p>
      </template>

      <router-link to="/feed" class="guest">先逛逛广场 →</router-link>
    </div>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--cx-theme-bg);
  padding: 20px;
}

.card {
  width: 380px;
  background: #fff;
  border-radius: 12px;
  padding: 32px 36px 24px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  text-align: center;
}

.logo {
  color: var(--el-color-primary);
  letter-spacing: 4px;
  margin: 0 0 4px;
}

.slogan {
  color: #999;
  font-size: 13px;
  margin-bottom: 16px;
}

.reset-title {
  font-size: 16px;
  color: #333;
  margin: 8px 0 16px;
}

.submit {
  width: 100%;
}

.switch {
  text-align: right;
  margin: 10px 0 0;
}

.switch a {
  color: var(--el-color-primary);
  font-size: 13px;
  cursor: pointer;
  text-decoration: none;
}

.tip {
  color: #bbb;
  font-size: 12px;
  margin: 10px 0 4px;
}

.guest {
  color: var(--el-color-primary);
  font-size: 13px;
  text-decoration: none;
}
</style>
