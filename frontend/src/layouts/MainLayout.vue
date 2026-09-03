<script setup lang="ts">
/**
 * 主布局：知乎式固定顶栏（logo / 搜索 / 通知铃铛 / 发帖 / 头像菜单）+ 内容区。
 * 主题装扮（V1.6）：登录后拉取本人 theme_config 注入 CSS 变量，退出恢复默认。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useMessageStore } from '@/stores/message'

const auth = useAuthStore()
const theme = useThemeStore()
const message = useMessageStore()
const route = useRoute()
const router = useRouter()
const keyword = ref((route.query.q as string) || '')

onMounted(() => {
  if (auth.isLogged) {
    auth.fetchUnread()
    theme.fetchAndApply()
    message.fetchUnread()
  }
})

// 顶栏内退出登录时恢复默认主题（登录跳转会重新挂载本布局并拉取装扮）
watch(
  () => auth.isLogged,
  (logged) => {
    if (!logged) {
      theme.apply(null)
      message.reset()
    }
  },
)

const badgeText = computed(() =>
  auth.unreadCount > 99 ? '99+' : auth.unreadCount > 0 ? String(auth.unreadCount) : '',
)

const dmBadgeText = computed(() =>
  message.unreadCount > 99
    ? '99+'
    : message.unreadCount > 0
      ? String(message.unreadCount)
      : '',
)

// 二级导航：主页面功能入口（点击后整页切换内容）
const subTabs = [
  { path: '/feed', label: '广场' },
  { path: '/ranks', label: '助人榜' },
  { path: '/mall', label: '商城' },
]

const subActive = computed(() =>
  subTabs.some((t) => t.path === route.path) ? route.path : '',
)

function onSearch() {
  const q = keyword.value.trim()
  if (!q) return
  router.push({ path: '/search', query: { q } })
}

function onCommand(cmd: string) {
  if (cmd === 'profile') {
    router.push(`/u/${auth.user?.id}`)
  } else if (cmd === 'notifications') {
    router.push('/notifications')
  } else if (cmd === 'messages') {
    router.push('/messages')
  } else if (cmd === 'admin') {
    router.push('/admin')
  } else if (cmd === 'logout') {
    auth.logout()
    ElMessage.success('已退出登录')
    router.push('/login')
  }
}
</script>

<template>
  <el-container class="layout">
    <header class="topbar">
      <div class="topbar-inner">
        <router-link to="/feed" class="logo">畅学</router-link>

        <div class="actions">
          <el-badge :value="badgeText" :hidden="!badgeText" :max="99">
            <el-button circle title="通知" @click="router.push('/notifications')">
              <el-icon><Bell /></el-icon>
            </el-button>
          </el-badge>

          <el-badge :value="dmBadgeText" :hidden="!dmBadgeText" :max="99">
            <el-button circle title="私信" @click="router.push('/messages')">
              <el-icon><ChatDotRound /></el-icon>
            </el-button>
          </el-badge>

          <el-button type="primary" round @click="router.push('/posts/create')">
            提问
          </el-button>

          <template v-if="auth.isLogged">
            <el-dropdown trigger="click" @command="onCommand">
              <el-avatar :size="34" class="avatar">
                {{ auth.user?.nickname?.slice(0, 1) || '?' }}
              </el-avatar>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="profile">
                    {{ auth.user?.nickname }}（{{ auth.user?.credit_balance }} 积分）
                    <el-tag v-if="auth.user?.is_admin" size="small" type="danger" class="admin-tag">
                      管理员
                    </el-tag>
                  </el-dropdown-item>
                  <el-dropdown-item command="notifications" divided>
                    通知中心
                  </el-dropdown-item>
                  <el-dropdown-item command="messages">我的私信</el-dropdown-item>
                  <el-dropdown-item v-if="auth.user?.is_admin" command="admin">
                    管理后台
                  </el-dropdown-item>
                  <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
          <el-button v-else text type="primary" @click="router.push('/login')">
            登录
          </el-button>
        </div>
      </div>
    </header>

    <!-- 第二标题栏：功能入口 + 搜索（点击后整页切换内容） -->
    <nav class="subnav">
      <div class="subnav-inner">
        <router-link
          v-for="t in subTabs"
          :key="t.path"
          :to="t.path"
          class="subtab"
          :class="{ active: subActive === t.path }"
        >
          {{ t.label }}
        </router-link>

        <div class="search-box">
          <el-input
            v-model="keyword"
            placeholder="搜索问题 / 知识库"
            clearable
            @keyup.enter="onSearch"
          >
            <template #append>
              <el-button @click="onSearch">搜索</el-button>
            </template>
          </el-input>
        </div>
      </div>
    </nav>

    <main class="content">
      <router-view :key="route.fullPath" />
    </main>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
  background: transparent; /* 背景由 body（主题装扮变量）统一绘制 */
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.topbar-inner {
  max-width: 1000px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 20px;
  height: 56px;
  padding: 0 16px;
}

.logo {
  font-size: 22px;
  font-weight: 700;
  color: var(--el-color-primary);
  text-decoration: none;
  letter-spacing: 2px;
}

.subnav {
  position: sticky;
  top: 56px; /* 紧贴第一标题栏下沿 */
  z-index: 99;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}

.subnav-inner {
  max-width: 1000px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 4px;
  height: 48px;
  padding: 0 16px;
}

.subtab {
  color: #555;
  text-decoration: none;
  font-size: 15px;
  padding: 6px 16px;
  border-radius: 6px;
  transition: all 0.15s;
}

.subtab:hover {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.subtab.active {
  color: var(--el-color-primary);
  font-weight: 600;
  background: var(--el-color-primary-light-9);
}

.subnav .search-box {
  flex: 1;
  max-width: 360px;
  margin-left: auto;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.avatar {
  cursor: pointer;
  background: var(--el-color-primary-light-5);
}

.admin-tag {
  margin-left: 6px;
}

.content {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px 16px 60px;
  width: 100%;
}
</style>
