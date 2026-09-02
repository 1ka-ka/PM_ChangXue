<script setup lang="ts">
/** 双层评论组件：根评论 + 回复（二层封顶），自治加载（帖子和回答复用）。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { get, post as httpPost } from '@/api/http'
import type { CommentItem } from '@/api/types'

const props = defineProps<{
  targetType: 1 | 2 // 1 帖子 2 回答
  targetId: number
}>()

const auth = useAuthStore()
const comments = ref<CommentItem[]>([])
const content = ref('')
const replyTo = ref<{ parentId: number; nickname: string; userId: number | null } | null>(null)
const submitting = ref(false)
const expanded = ref<number | null>(null)

async function load() {
  comments.value = await get<CommentItem[]>('/comments', {
    target_type: props.targetType,
    target_id: props.targetId,
  })
}

onMounted(load)

async function submit() {
  const body = content.value.trim()
  if (!body) {
    ElMessage.warning('评论内容不能为空')
    return
  }
  if (!auth.isLogged) {
    ElMessage.warning('请先登录')
    return
  }
  submitting.value = true
  try {
    await httpPost('/comments', {
      target_type: props.targetType,
      target_id: props.targetId,
      content: body,
      parent_id: replyTo.value?.parentId ?? null,
      reply_to_user_id: replyTo.value?.userId ?? null,
    })
    content.value = ''
    replyTo.value = null
    await load()
  } finally {
    submitting.value = false
  }
}

function startReply(c: CommentItem) {
  replyTo.value = { parentId: c.parent_id ?? c.id, nickname: c.author_nickname, userId: c.author_id }
  content.value = ''
}

function timeOf(c: CommentItem) {
  return (c.created_at || '').slice(0, 16).replace('T', ' ')
}
</script>

<template>
  <div class="comments">
    <div v-if="auth.isLogged" class="composer">
      <el-input
        v-model="content"
        type="textarea"
        :rows="2"
        :placeholder="replyTo ? `回复 @${replyTo.nickname}：` : '写下你的评论…'"
        maxlength="500"
        show-word-limit
      />
      <div class="composer-actions">
        <el-button v-if="replyTo" text size="small" @click="replyTo = null">取消回复</el-button>
        <el-button type="primary" size="small" :loading="submitting" @click="submit">
          发表评论
        </el-button>
      </div>
    </div>
    <el-alert v-else title="登录后参与评论" type="info" :closable="false" class="login-tip" />

    <div v-if="!comments.length" class="cx-empty" style="padding: 20px 0">暂无评论</div>

    <div v-for="c in comments" :key="c.id" class="comment">
      <div class="row">
        <el-avatar :size="28" class="avatar">{{ c.author_nickname.slice(0, 1) }}</el-avatar>
        <div class="body">
          <span class="author">{{ c.author_nickname }}</span>
          <span class="text">{{ c.content }}</span>
          <div class="meta">
            <span>{{ timeOf(c) }}</span>
            <a @click="startReply(c)">回复</a>
            <a
              v-if="c.replies.length"
              @click="expanded = expanded === c.id ? null : c.id"
            >
              {{ expanded === c.id ? '收起' : `展开 ${c.replies.length} 条回复` }}
            </a>
          </div>

          <div v-show="expanded === c.id" class="replies">
            <div v-for="r in c.replies" :key="r.id" class="reply">
              <span class="author">{{ r.author_nickname }}</span>
              <span v-if="r.reply_to_nickname" class="reply-to">@{{ r.reply_to_nickname }}</span>
              <span class="text">{{ r.content }}</span>
              <div class="meta">
                <span>{{ timeOf(r) }}</span>
                <a @click="startReply(r)">回复</a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.composer {
  margin-bottom: 16px;
}

.composer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}

.login-tip {
  margin-bottom: 16px;
}

.comment .row {
  display: flex;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid #f2f2f2;
}

.avatar {
  flex-shrink: 0;
  background: var(--el-color-primary-light-7);
}

.body {
  flex: 1;
  min-width: 0;
}

.author {
  color: var(--el-color-primary);
  font-size: 13px;
  margin-right: 8px;
}

.reply-to {
  color: var(--el-color-primary);
  font-size: 13px;
  margin-right: 8px;
}

.text {
  font-size: 14px;
  color: #333;
}

.meta {
  display: flex;
  gap: 14px;
  color: #bbb;
  font-size: 12px;
  margin-top: 4px;
}

.meta a {
  color: #999;
  cursor: pointer;
}

.meta a:hover {
  color: var(--el-color-primary);
}

.replies {
  background: #f8f8f8;
  border-radius: 6px;
  padding: 6px 12px;
  margin-top: 8px;
}

.reply {
  padding: 6px 0;
}
</style>
