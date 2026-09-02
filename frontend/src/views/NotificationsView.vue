<script setup lang="ts">
/**
 * S11d 通知中心（M6-F21）：五类通知列表 + 全部已读 + 未读角标联动 + 点击直达帖子。
 */
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { get, post } from '@/api/http'
import type { Page } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

interface Actor {
  id: number
  nickname: string
}

interface NotificationItem {
  id: number
  type: number
  type_text: string
  actor: Actor | null
  target_type: number
  target_id: number
  post_id: number | null
  is_read: boolean
  invalid: boolean
  created_at: string
}

const router = useRouter()
const auth = useAuthStore()

const items = ref<NotificationItem[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const marking = ref(false)

async function fetchList() {
  loading.value = true
  try {
    const r = await get<Page<NotificationItem>>('/notifications', { page: page.value })
    items.value = r.items
    total.value = r.total
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function markAll() {
  marking.value = true
  try {
    await post('/notifications/read-all')
    items.value = items.value.map((n) => ({ ...n, is_read: true }))
    auth.fetchUnread()
  } catch {
    // 拦截器已提示
  } finally {
    marking.value = false
  }
}

function onClick(n: NotificationItem) {
  if (!n.is_read) {
    n.is_read = true
    auth.fetchUnread()
  }
  if (n.post_id) router.push(`/posts/${n.post_id}`)
}

function fmtTime(s: string) {
  return new Date(s).toLocaleString('zh-CN', { hour12: false })
}

onMounted(fetchList)
watch(page, fetchList)
</script>

<template>
  <div class="cx-card notify">
    <div class="head-row">
      <h2>通知中心</h2>
      <el-button
        size="small"
        round
        :loading="marking"
        :disabled="!items.some((n) => !n.is_read)"
        @click="markAll"
      >
        全部已读
      </el-button>
    </div>

    <div v-loading="loading" class="list">
      <div
        v-for="n in items"
        :key="n.id"
        class="item"
        :class="{ unread: !n.is_read }"
        @click="onClick(n)"
      >
        <el-avatar :size="36" class="avatar">{{ n.actor?.nickname?.slice(0, 1) || '系' }}</el-avatar>
        <div class="body">
          <div class="line">
            <b class="actor">{{ n.actor?.nickname || '系统' }}</b>
            <span class="text">{{ n.type_text }}</span>
            <el-tag v-if="!n.is_read" size="small" type="danger" effect="dark" class="dot">未读</el-tag>
          </div>
          <span class="time">{{ fmtTime(n.created_at) }}</span>
        </div>
        <span v-if="n.invalid" class="invalid-tag">内容已删除</span>
        <el-icon v-else-if="n.post_id" class="arrow"><ArrowRight /></el-icon>
      </div>
      <el-empty v-if="!loading && !items.length" description="暂无通知" />
    </div>

    <div v-if="total > 20" class="pager">
      <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="prev, pager, next" background />
    </div>
  </div>
</template>

<style scoped>
.notify {
  max-width: 720px;
  margin: 0 auto;
  padding: 20px 24px 24px;
}

.head-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.head-row h2 {
  margin: 0;
  font-size: 18px;
}

.list {
  display: flex;
  flex-direction: column;
  min-height: 120px;
}

.item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  border-radius: 6px;
}

.item:hover {
  background: var(--el-fill-color-light);
}

.item.unread {
  background: var(--el-color-primary-light-9);
}

.avatar {
  flex-shrink: 0;
  background: var(--el-color-primary-light-5);
}

.body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.line {
  display: flex;
  align-items: center;
  gap: 6px;
}

.actor {
  font-size: 14px;
}

.text {
  color: #555;
  font-size: 14px;
}

.dot {
  flex-shrink: 0;
}

.time {
  color: #bbb;
  font-size: 12px;
}

.invalid-tag {
  color: #bbb;
  font-size: 12px;
  flex-shrink: 0;
}

.arrow {
  color: #ccc;
}

.pager {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
