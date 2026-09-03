<script setup lang="ts">
/**
 * 主页面（V1.10 布局改版）：顶部按钮栏激活功能子页（广场/助人榜/商城），
 * 子页通过嵌套路由渲染在本页内，默认展示广场；替代此前独立整页切换导致主页面空旷的问题。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const tabs = [
  { path: '/feed', label: '广场' },
  { path: '/ranks', label: '助人榜' },
  { path: '/mall', label: '商城' },
]

const active = computed(() =>
  tabs.some((t) => t.path === route.path) ? route.path : '/feed',
)
</script>

<template>
  <div class="home">
    <div class="home-tabs">
      <button
        v-for="t in tabs"
        :key="t.path"
        class="home-tab"
        :class="{ active: active === t.path }"
        @click="router.push(t.path)"
      >
        {{ t.label }}
      </button>
    </div>
    <router-view />
  </div>
</template>

<style scoped>
.home-tabs {
  display: flex;
  gap: 8px;
  background: #fff;
  border-radius: 8px;
  padding: 8px 16px;
  margin-bottom: 12px;
}

.home-tab {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 15px;
  color: #555;
  padding: 7px 18px;
  border-radius: 6px;
  transition: all 0.15s;
}

.home-tab:hover {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.home-tab.active {
  color: #fff;
  background: var(--el-color-primary);
  font-weight: 600;
}
</style>
