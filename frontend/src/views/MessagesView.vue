<script setup lang="ts">
/**
 * 私信页（V1.7）：QQ 式左右布局——左会话列表 + 右聊天窗。
 * 支持 ?to=uid&name=昵称 直达新会话（他人主页"发私信"入口）；
 * 当前会话 8s 轮询刷新消息（无 WebSocket 的轻量方案）。
 */
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, post } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useMessageStore } from '@/stores/message'

interface Peer {
  id: number
  nickname: string
  avatar: string | null
}

interface ConversationItem {
  conversation_id: number
  peer: Peer | null
  last_content: string | null
  last_time: string
  unread: number
}

interface MessageItem {
  id: number
  sender_id: number
  content: string
  created_at: string
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const messageStore = useMessageStore()

const conversations = ref<ConversationItem[]>([])
const activeId = ref<number | null>(null)
const peer = ref<Peer | null>(null)
const messages = ref<MessageItem[]>([])
const draft = ref('')
const sending = ref(false)
const listLoading = ref(false)

// ?to= 发起全新会话（暂无 conversation_id，首条发送后落位）
const newTo = ref<number | null>(null)
const newToName = ref('')

const listRef = ref<HTMLElement>()

let pollTimer: number | undefined

async function fetchConversations() {
  listLoading.value = true
  try {
    const r = await get<{ items: ConversationItem[] }>('/messages/conversations')
    conversations.value = r.items
  } catch {
    // 拦截器已提示
  } finally {
    listLoading.value = false
  }
}

async function fetchMessages() {
  if (activeId.value == null) return
  try {
    const r = await get<{ items: MessageItem[] }>(
      `/messages/conversations/${activeId.value}`,
      { page_size: 50 },
    )
    messages.value = [...r.items].reverse() // 接口倒序 → 正序展示
    scrollToBottom()
  } catch {
    // 拦截器已提示
  }
}

function openConversation(c: ConversationItem) {
  activeId.value = c.conversation_id
  peer.value = c.peer
  newTo.value = null
  newToName.value = ''
  c.unread = 0
  messages.value = []
  fetchMessages()
  void messageStore.fetchUnread()
}

async function send() {
  const content = draft.value.trim()
  if (!content || sending.value) return
  const to = newTo.value ?? peer.value?.id
  if (to == null) return
  sending.value = true
  try {
    const r = await post<{ conversation_id: number }>('/messages', { to_user_id: to, content })
    draft.value = ''
    if (newTo.value != null) {
      // 新会话：首条发送成功后落位
      newTo.value = null
      newToName.value = ''
      activeId.value = r.conversation_id
    }
    await Promise.all([fetchConversations(), fetchMessages()])
    void messageStore.fetchUnread()
  } catch {
    // 拦截器已提示
  } finally {
    sending.value = false
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

function fmtTime(s: string) {
  return new Date(s).toLocaleString('zh-CN', { hour12: false })
}

onMounted(async () => {
  await fetchConversations()
  void messageStore.fetchUnread()

  // ?to= 直达新会话
  const to = Number(route.query.to)
  if (to && to !== auth.user?.id) {
    const existing = conversations.value.find((c) => c.peer?.id === to)
    if (existing) {
      openConversation(existing)
    } else {
      activeId.value = null
      newTo.value = to
      newToName.value = (route.query.name as string) || `用户 ${to}`
    }
  } else if (conversations.value.length) {
    openConversation(conversations.value[0])
  }

  // 8s 轮询：当前会话新消息 + 未读角标（轻量保活，无 WebSocket）
  pollTimer = window.setInterval(() => {
    if (activeId.value != null) fetchMessages()
    void messageStore.fetchUnread()
  }, 8000)
})

onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<template>
  <div class="messages cx-card">
    <!-- 左：会话列表 -->
    <aside class="convs" v-loading="listLoading">
      <div
        v-for="c in conversations"
        :key="c.conversation_id"
        class="conv-item"
        :class="{ active: c.conversation_id === activeId }"
        @click="openConversation(c)"
      >
        <el-badge :value="c.unread" :hidden="!c.unread" :max="99">
          <el-avatar :size="40" :src="c.peer?.avatar || undefined">
            {{ c.peer?.nickname?.slice(0, 1) || '?' }}
          </el-avatar>
        </el-badge>
        <div class="conv-info">
          <div class="conv-name">{{ c.peer?.nickname || '未知用户' }}</div>
          <div class="conv-last">{{ c.last_content || '' }}</div>
        </div>
      </div>
      <el-empty
        v-if="!listLoading && !conversations.length && !newTo"
        description="暂无私信，可到他人主页发起"
        :image-size="60"
      />
    </aside>

    <!-- 右：聊天窗 -->
    <section class="chat">
      <template v-if="activeId != null || newTo != null">
        <header class="chat-head">
          <span>{{ newTo ? newToName : peer?.nickname || '对话' }}</span>
          <el-button
            v-if="peer"
            text
            size="small"
            @click="router.push(`/u/${peer.id}`)"
          >
            主页
          </el-button>
        </header>

        <div ref="listRef" class="msg-list">
          <div
            v-for="m in messages"
            :key="m.id"
            class="msg-row"
            :class="{ mine: m.sender_id === auth.user?.id }"
          >
            <div class="bubble">
              <p class="text">{{ m.content }}</p>
              <span class="time">{{ fmtTime(m.created_at) }}</span>
            </div>
          </div>
          <el-empty
            v-if="newTo && !messages.length"
            :description="`给 ${newToName} 发送第一条私信`"
            :image-size="60"
          />
        </div>

        <footer class="chat-input">
          <el-input
            v-model="draft"
            type="textarea"
            :rows="2"
            maxlength="500"
            show-word-limit
            placeholder="输入私信内容（1-500 字）"
            @keyup.enter.exact.prevent="send"
          />
          <el-button type="primary" :loading="sending" @click="send">发送</el-button>
        </footer>
      </template>

      <el-empty v-else class="chat-empty" description="选择左侧会话开始聊天" />
    </section>
  </div>
</template>

<style scoped>
.messages {
  display: flex;
  height: calc(100vh - 140px);
  min-height: 420px;
  padding: 0;
  overflow: hidden;
}

.convs {
  width: 260px;
  border-right: 1px solid var(--el-border-color-lighter);
  overflow-y: auto;
  padding: 8px;
}

.conv-item {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 10px;
  border-radius: 8px;
  cursor: pointer;
}

.conv-item:hover {
  background: #f5f7fa;
}

.conv-item.active {
  background: #ecf5ff;
}

.conv-info {
  flex: 1;
  min-width: 0;
}

.conv-name {
  font-weight: 600;
  font-size: 14px;
}

.conv-last {
  color: #999;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 4px;
}

.chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-weight: 600;
}

.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.msg-row {
  display: flex;
}

.msg-row.mine {
  justify-content: flex-end;
}

.bubble {
  max-width: 70%;
  background: #f5f6f7;
  border-radius: 10px;
  padding: 8px 12px;
}

.msg-row.mine .bubble {
  background: var(--cx-theme-primary);
  color: #fff;
}

.bubble .text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble .time {
  display: block;
  font-size: 11px;
  opacity: 0.6;
  margin-top: 4px;
  text-align: right;
}

.chat-input {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  padding: 12px 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.chat-input .el-button {
  flex-shrink: 0;
}

.chat-empty {
  margin: auto;
}
</style>
