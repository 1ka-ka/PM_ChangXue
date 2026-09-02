<script setup lang="ts">
/** 帖子详情：正文渲染 + 回答列表（提交/点赞）+ 帖子评论。采纳按钮 S11b 仅登录提问者可见（调 S6 接口）。 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiError, get, post as httpPost } from '@/api/http'
import type { PostDetail } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import CommentThread from '@/components/CommentThread.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const post = ref<PostDetail | null>(null)
const loading = ref(true)
const answerText = ref('')
const submitting = ref(false)

async function load() {
  loading.value = true
  try {
    post.value = await get<PostDetail>(`/posts/${route.params.id}`)
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function submitAnswer() {
  if (!auth.isLogged) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  const content = answerText.value.trim()
  if (!content) {
    ElMessage.warning('回答内容不能为空')
    return
  }
  submitting.value = true
  try {
    await httpPost(`/posts/${route.params.id}/answers`, { content })
    answerText.value = ''
    ElMessage.success('回答已提交')
    await load()
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '提交失败')
  } finally {
    submitting.value = false
  }
}

async function toggleLike(targetType: 1 | 2, targetId: number, current: { is_liked: boolean; like_count: number }) {
  if (!auth.isLogged) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  const r = await httpPost<{ liked: boolean; like_count: number }>('/likes/toggle', {
    target_type: targetType,
    target_id: targetId,
  })
  current.is_liked = r.liked
  current.like_count = r.like_count
}

async function acceptAnswer(answerId: number) {
  try {
    await httpPost(`/answers/${answerId}/accept`)
    // 首个采纳自动设为最佳（后端语义：采纳与设最佳两步）
    try {
      await httpPost(`/answers/${answerId}/set-best`)
    } catch {
      /* 已有最佳时忽略 */
    }
    ElMessage.success('已采纳并设为最佳，回答者获得 30 积分')
    await load()
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '采纳失败')
  }
}

function fmtTime(s: string) {
  return (s || '').slice(0, 16).replace('T', ' ')
}
</script>

<template>
  <div v-loading="loading">
    <template v-if="post">
      <!-- 帖子正文 -->
      <div class="cx-card post">
        <div class="head">
          <el-tag :type="post.status === 1 ? 'success' : 'warning'" effect="dark" size="small">
            {{ post.status === 1 ? '已解决' : '待解决' }}
          </el-tag>
          <h1 class="title">{{ post.title }}</h1>
          <el-tag v-if="post.reward > 0" type="danger" effect="plain">悬赏 {{ post.reward }} 积分</el-tag>
        </div>

        <div class="meta">
          <span class="author" @click="router.push(`/u/${post.author_id}`)">
            {{ post.author_nickname }}
          </span>
          <span>{{ fmtTime(post.created_at) }}</span>
          <span>{{ post.view_count }} 浏览</span>
          <span v-if="post.edited" class="edited">已编辑</span>
        </div>

        <p class="content">{{ post.content }}</p>

        <div v-if="post.images.length" class="images">
          <el-image
            v-for="(img, i) in post.images"
            :key="i"
            :src="img"
            :preview-src-list="post.images"
            :initial-index="i"
            fit="cover"
            class="img"
          />
        </div>

        <div class="foot">
          <span class="tags">
            <el-tag v-for="t in post.tags" :key="t.id" size="small" effect="plain">{{ t.name }}</el-tag>
          </span>
          <span class="ops">
            <el-button
              size="small"
              :type="post.is_liked ? 'primary' : 'default'"
              round
              @click="toggleLike(1, post.id, post)"
            >
              <el-icon><Pointer /></el-icon>&nbsp;{{ post.like_count }}
            </el-button>
          </span>
        </div>
      </div>

      <!-- 回答区 -->
      <div class="cx-card">
        <h3 class="section-title">{{ post.answers.length }} 个回答</h3>

        <div v-if="!post.answers.length" class="cx-empty">还没有回答，来抢第一个吧</div>

        <div v-for="a in post.answers" :key="a.id" class="answer">
          <div class="answer-head">
            <el-avatar :size="32" class="avatar">{{ a.author_nickname.slice(0, 1) }}</el-avatar>
            <div>
              <span class="author" @click="router.push(`/u/${a.author_id}`)">
                {{ a.author_nickname }}
              </span>
              <div class="meta">{{ fmtTime(a.created_at) }}</div>
            </div>
            <div class="badges">
              <el-tag v-if="a.is_best" type="success" effect="dark" size="small">最佳</el-tag>
              <el-tag v-else-if="a.is_accepted" type="success" effect="plain" size="small">已采纳</el-tag>
            </div>
          </div>

          <p class="answer-content">{{ a.content }}</p>

          <div class="answer-ops">
            <el-button
              size="small"
              text
              :type="a.is_liked ? 'primary' : 'default'"
              @click="toggleLike(2, a.id, a)"
            >
              <el-icon><Pointer /></el-icon>&nbsp;{{ a.like_count }}
            </el-button>
            <el-button
              v-if="auth.user?.id === post.author_id && post.status === 0 && !a.is_accepted"
              size="small"
              type="success"
              plain
              @click="acceptAnswer(a.id)"
            >
              采纳
            </el-button>
          </div>

          <el-divider class="comment-divider" content-position="left">
            <span class="comment-toggle">评论</span>
          </el-divider>
          <CommentThread :target-type="2" :target-id="a.id" />
        </div>
      </div>

      <!-- 提交回答 -->
      <div class="cx-card">
        <h3 class="section-title">写下你的回答</h3>
        <template v-if="auth.user?.id !== post.author_id">
          <el-input
            v-model="answerText"
            type="textarea"
            :rows="4"
            placeholder="认真回答，被采纳可获得 30 积分…"
            maxlength="5000"
            show-word-limit
          />
          <div class="answer-actions">
            <el-button type="primary" :loading="submitting" @click="submitAnswer">
              提交回答
            </el-button>
          </div>
        </template>
        <el-alert v-else title="不能回答自己的提问" type="info" :closable="false" />
      </div>

      <!-- 帖子评论 -->
      <div class="cx-card">
        <h3 class="section-title">帖子评论</h3>
        <CommentThread :target-type="1" :target-id="post.id" />
      </div>
    </template>

    <div v-else-if="!loading" class="cx-empty">
      <p>帖子不存在或已删除</p>
      <router-link to="/feed">返回广场</router-link>
    </div>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title {
  font-size: 20px;
  margin: 0;
  flex: 1;
}

.meta {
  display: flex;
  gap: 14px;
  color: #999;
  font-size: 12px;
  margin: 10px 0;
}

.author {
  color: var(--el-color-primary);
  cursor: pointer;
}

.edited {
  color: #ccc;
}

.content {
  color: #333;
  line-height: 1.7;
  white-space: pre-wrap;
  margin: 12px 0;
}

.images {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.img {
  width: 140px;
  height: 140px;
  border-radius: 6px;
}

.foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}

.tags {
  display: flex;
  gap: 4px;
}

.section-title {
  margin: 0 0 14px;
  font-size: 16px;
}

.answer {
  padding: 14px 0;
  border-bottom: 1px solid #f2f2f2;
}

.answer-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar {
  background: var(--el-color-primary-light-7);
}

.badges {
  margin-left: auto;
}

.answer-content {
  color: #333;
  line-height: 1.7;
  white-space: pre-wrap;
  margin: 10px 0;
}

.answer-ops {
  display: flex;
  gap: 8px;
}

.comment-divider {
  margin: 8px 0 4px;
}

.comment-toggle {
  color: #999;
  font-size: 13px;
}

.answer-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
