<script setup lang="ts">
/** 登录/注册：卡片式切换表单，成功后跳 redirect 或广场。 */
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const mode = ref<'login' | 'register'>('login')
const loading = ref(false)
const form = reactive({ phone: '', password: '', nickname: '' })

async function submit() {
  if (!/^1\d{10}$/.test(form.phone)) {
    ElMessage.warning('请输入 11 位手机号')
    return
  }
  if (form.password.length < 8) {
    ElMessage.warning('密码至少 8 位')
    return
  }
  if (mode.value === 'register' && !form.nickname.trim()) {
    ElMessage.warning('请输入昵称')
    return
  }
  loading.value = true
  try {
    if (mode.value === 'login') {
      await auth.login(form.phone, form.password)
    } else {
      await auth.register(form.phone, form.password, form.nickname.trim())
    }
    ElMessage.success(mode.value === 'login' ? '欢迎回来' : '注册成功，赠送 50 积分')
    const redirect = (route.query.redirect as string) || '/feed'
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

      <el-tabs v-model="mode" stretch>
        <el-tab-pane label="登录" name="login" />
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
        <el-form-item>
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
        <el-button
          type="primary"
          size="large"
          class="submit"
          :loading="loading"
          round
          @click="submit"
        >
          {{ mode === 'login' ? '登录' : '注册并登录' }}
        </el-button>
      </el-form>

      <p class="tip">注册即送 50 积分 · 回答被采纳 +30 积分</p>
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

.submit {
  width: 100%;
}

.tip {
  color: #bbb;
  font-size: 12px;
  margin: 14px 0 4px;
}

.guest {
  color: var(--el-color-primary);
  font-size: 13px;
  text-decoration: none;
}
</style>
