<script setup lang="ts">
/** 双层评论组件（知乎式）：点「添加评论」展开输入框；根评论 + 回复（二层封顶，灰底折叠）。 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { get, post as httpPost } from '@/api/http'
import type { CommentItem } from '@/api/types'
import UserDecor from './UserDecor.vue'

const props = defineProps<{
  targetType: 1 | 2 // 1 帖子 2 回答
  targetId: number
}>()

const emit = defineEmits<{ loaded: [total: number] }>()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const comments = ref<CommentItem[]>([])
const content = ref('')
const composing = ref(false) // 知乎式：输入框点击「添加评论」后才出现
const replyTo = ref<{ parentId: number; nickname: string; userId: number | null } | null>(null)
const submitting = ref(false)
const expanded = ref<number | null>(null)

async function load() {
  comments.value = await get<CommentItem[]>('/comments', {
    target_type: props.targetType,
    target_id: props.targetId,
  })
  // 评论总数（含回复）上报父组件，供「N 条评论」入口显示
  emit(
    'loaded',
    comments.value.reduce((n, c) => n + 1 + (c.replies?.length ?? 0), 0),
  )
}

onMounted(load)

/** 展开输入框；未登录跳登录（知乎：未登录点击评论引导登录）。 */
function startCompose() {
  if (!auth.isLogged) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  composing.value = true
}

async function submit() {
  const body = content.value.trim()
  if (!body) {
    ElMessage.warning('评论内容不能为空')
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
    composing.value = false
    await load()
  } finally {
    submitting.value = false
  }
}

function startReply(c: CommentItem) {
  startCompose()
  replyTo.value = { parentId: c.parent_id ?? c.id, nickname: c.author_nickname, userId: c.author_id }
  content.value = ''
}

function timeOf(c: CommentItem) {
  return (c.created_at || '').slice(0, 16).replace('T', ' ')
}
</script>

<template>
  <div class="comments">
    <!-- 知乎式：无输入态只显示「添加评论」入口 -->
    <a v-if="!composing" class="add-comment" @click="startCompose">添加评论…</a>

    <div v-else class="composer">
      <el-input
        v-model="content"
        type="textarea"
        :rows="2"
        :placeholder="replyTo ? `回复 @${replyTo.nickname}：` : '写下你的评论…'"
        maxlength="500"
        show-word-limit
      />
      <div class="composer-actions">
        <el-button
          v-if="replyTo"
          text
          size="small"
          @click="replyTo = null"
        >
          取消回复
        </el-button>
        <el-button text size="small" @click="composing = false">收起</el-button>
        <el-button type="primary" size="small" :loading="submitting" @click="submit">
          发布
        </el-button>
      </div>
    </div>

    <div v-if="!comments.length" class="cx-empty" style="padding: 16px 0">暂无评论</div>

    <div v-for="c in comments" :key="c.id" class="comment">
      <el-avatar :size="24" class="avatar">{{ c.author_nickname.slice(0, 1) }}</el-avatar>
      <div class="body">
        <div class="text-line">
          <span class="author">{{ c.author_nickname }}</span>
          <UserDecor :equipped="c.author_equipped" />
          <span class="text">{{ c.content }}</span>
        </div>
        <div class="meta">
          <span>{{ timeOf(c) }}</span>
          <a @click="startReply(c)">回复</a>
          <a
            v-if="c.replies.length"
            @click="expanded = expanded === c.id ? null : c.id"
          >
            {{ expanded === c.id ? '收起' : `查看 ${c.replies.length} 条回复` }}
          </a>
        </div>

        <div v-show="expanded === c.id" class="replies">
          <div v-for="r in c.replies" :key="r.id" class="reply">
            <div class="text-line">
              <span class="author">{{ r.author_nickname }}</span>
              <UserDecor :equipped="r.author_equipped" />
              <span v-if="r.reply_to_nickname" class="reply-to">@{{ r.reply_to_nickname }}</span>
              <span class="text">{{ r.content }}</span>
            </div>
            <div class="meta">
              <span>{{ timeOf(r) }}</span>
              <a @click="startReply(r)">回复</a>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.add-comment {
  display: inline-block;
  color: #909399;
  font-size: 14px;
  cursor: pointer;
  margin-bottom: 12px;
}

.add-comment:hover {
  color: var(--el-color-primary);
}

.composer {
  margin-bottom: 16px;
}

.composer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}

.comment {
  display: flex;
  gap: 8px;
  padding: 8px 0;
}

.avatar {
  flex-shrink: 0;
  background: var(--el-color-primary-light-7);
}

.body {
  flex: 1;
  min-width: 0;
}

.text-line {
  font-size: 14px;
  line-height: 1.6;
  color: #333;
}

.author {
  color: #409eff;
  margin-right: 4px;
  font-weight: 600;
}

.reply-to {
  color: #409eff;
  margin-right: 4px;
}

.meta {
  display: flex;
  gap: 14px;
  color: #bfbfbf;
  font-size: 12px;
  margin-top: 2px;
}

.meta a {
  color: #999;
  cursor: pointer;
}

.meta a:hover {
  color: var(--el-color-primary);
}

.replies {
  background: #f6f6f6;
  border-radius: 6px;
  padding: 8px 14px;
  margin-top: 6px;
}

.reply {
  padding: 4px 0;
}
</style>
