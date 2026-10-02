<script setup lang="ts">
/** 帖子详情（V1.11 知乎式改版）：双栏布局（主列：问题/写回答/回答列表 + 侧栏：数据/相关问题），
 * 回答评论默认收起（点「N 条评论」展开），赞同大按钮 + 收藏/分享/举报；功能与接口维持不变。 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiError, get, post as httpPost } from '@/api/http'
import type { PostCard, PostDetail } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import CommentThread from '@/components/CommentThread.vue'
import ReportDialog from '@/components/ReportDialog.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const post = ref<PostDetail | null>(null)
const loading = ref(true)
const answerText = ref('')
const submitting = ref(false)
const reportRef = ref<InstanceType<typeof ReportDialog>>()
const similar = ref<PostCard[]>([])

// 回答排序（知乎式切换，前端本地排序；默认=后端序：最佳>采纳>点赞>时间）
const sortMode = ref<'default' | 'time'>('default')
const sortedAnswers = computed(() => {
  if (!post.value) return []
  if (sortMode.value === 'default') return post.value.answers
  return [...post.value.answers].sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
})

// 各回答的评论数与展开态（知乎：评论默认收起，点「N 条评论」展开）
const commentCounts = ref<Record<number, number>>({})
const expandedComments = ref<Record<number, boolean>>({})

function onCommentsLoaded(answerId: number, total: number) {
  commentCounts.value[answerId] = total
}

function toggleComments(answerId: number) {
  expandedComments.value[answerId] = !expandedComments.value[answerId]
}

async function load() {
  loading.value = true
  try {
    post.value = await get<PostDetail>(`/posts/${route.params.id}`)
    // 相关问题推荐（V1.1）：失败静默不影响主内容
    try {
      const r = await get<{ items: PostCard[] }>(`/posts/${route.params.id}/similar`)
      similar.value = r.items
    } catch {
      similar.value = []
    }
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

async function toggleFavorite() {
  if (!post.value) return
  if (!auth.isLogged) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  const r = await httpPost<{ favorited: boolean }>('/favorites/toggle', {
    target_type: 1,
    target_id: post.value.id,
  })
  post.value.is_favorite = r.favorited
  ElMessage.success(r.favorited ? '已收藏' : '已取消收藏')
}

/** 分享（V1.11 新增）：复制本页链接到剪贴板 */
async function share() {
  const url = window.location.href
  try {
    await navigator.clipboard.writeText(url)
    ElMessage.success('链接已复制，去分享吧')
  } catch {
    // 非 https / 旧浏览器降级
    const input = document.createElement('textarea')
    input.value = url
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    document.body.removeChild(input)
    ElMessage.success('链接已复制，去分享吧')
  }
}

// 生成 AI 参考回答（V1.3）：登录触发，同步生成（约 10-30s），结果缓存
const aiAnswerLoading = ref(false)

async function generateAiAnswer() {
  if (!auth.isLogged) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  aiAnswerLoading.value = true
  try {
    await httpPost(`/posts/${route.params.id}/ai-answer`)
    await load()
    ElMessage.success('AI 参考回答已生成')
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '生成失败，请稍后再试')
  } finally {
    aiAnswerLoading.value = false
  }
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
      <div class="detail">
        <!-- ============ 左主列：问题 + 写回答 + 回答列表 + 问题评论 ============ -->
        <div class="main">
          <!-- 问题卡 -->
          <div class="cx-card post">
            <div class="q-head">
              <el-tag :type="post.status === 1 ? 'success' : 'warning'" effect="dark" size="small">
                {{ post.status === 1 ? '已解决' : '待解决' }}
              </el-tag>
              <el-tag v-if="post.reward > 0" type="danger" effect="plain" size="small">
                悬赏 {{ post.reward }} 积分
              </el-tag>
            </div>

            <h1 class="title">{{ post.title }}</h1>

            <!-- AI 摘要（V1.2）：后台异步生成，生成中/降级时整块不渲染 -->
            <div v-if="post.ai_summary" class="ai-summary">
              <div class="ai-head">
                <el-icon><MagicStick /></el-icon>
                <span>AI 摘要</span>
                <span class="ai-tip">由 AI 自动生成，仅供参考</span>
              </div>
              <p class="ai-text">{{ post.ai_summary }}</p>
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

            <div class="q-tags">
              <el-tag v-for="t in post.tags" :key="t.id" size="small" effect="plain">{{ t.name }}</el-tag>
            </div>

            <!-- 问题操作栏（知乎式） -->
            <div class="q-actions">
              <button
                class="vote-btn"
                :class="{ voted: post.is_liked }"
                @click="toggleLike(1, post.id, post)"
              >
                <el-icon><CaretTop /></el-icon>
                <span>赞同</span>
                <span class="vote-num">{{ post.like_count }}</span>
              </button>
              <button class="op-btn" :class="{ on: post.is_favorite }" @click="toggleFavorite">
                <el-icon><Star /></el-icon>
                <span>{{ post.is_favorite ? '已收藏' : '收藏' }}</span>
              </button>
              <button class="op-btn" @click="share">
                <el-icon><Share /></el-icon>
                <span>分享</span>
              </button>
              <el-dropdown trigger="click">
                <button class="op-btn">
                  <el-icon><MoreFilled /></el-icon>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="reportRef?.open(1, post.id)">
                      <el-icon><WarningFilled /></el-icon>举报问题
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>

          <!-- 写回答（知乎：问题卡下方常驻输入） -->
          <div class="cx-card write-answer">
            <template v-if="auth.user?.id !== post.author_id">
              <el-input
                v-model="answerText"
                type="textarea"
                :rows="3"
                placeholder="写你的回答…（认真回答，被采纳可获得 30 积分）"
                maxlength="5000"
                show-word-limit
              />
              <div class="write-actions">
                <el-button type="primary" :loading="submitting" @click="submitAnswer">
                  发布回答
                </el-button>
              </div>
            </template>
            <el-alert v-else title="不能回答自己的提问" type="info" :closable="false" />
          </div>

          <!-- 回答列表 -->
          <div class="cx-card">
            <div class="answers-head">
              <h3 class="section-title">{{ post.answers.length }} 个回答</h3>
              <el-radio-group v-model="sortMode" size="small">
                <el-radio-button value="default">默认排序</el-radio-button>
                <el-radio-button value="time">按时间排序</el-radio-button>
              </el-radio-group>
            </div>

            <!-- AI 参考回答（V1.3）：人答优先，无人回答时可触发 AI 兜底 -->
            <div v-if="post.ai_answer" class="ai-ref-answer">
              <div class="ai-head">
                <el-icon><MagicStick /></el-icon>
                <span>AI 参考回答</span>
                <span class="ai-tip">由 AI 生成，仅供参考，不可被采纳</span>
              </div>
              <p class="ai-ref-text">{{ post.ai_answer }}</p>
            </div>
            <div v-else-if="!post.answers.length && auth.isLogged" class="ai-ref-trigger">
              <el-button :loading="aiAnswerLoading" plain round @click="generateAiAnswer">
                <el-icon v-if="!aiAnswerLoading"><MagicStick /></el-icon>
                {{ aiAnswerLoading ? 'AI 正在思考，约需 10-30 秒…' : '暂无回答，生成 AI 参考回答' }}
              </el-button>
            </div>

            <div v-if="!post.answers.length" class="cx-empty">还没有回答，来抢第一个吧</div>

            <div v-for="a in sortedAnswers" :key="a.id" class="answer">
              <div class="answer-head">
                <el-avatar :size="38" class="avatar" @click="router.push(`/u/${a.author_id}`)">
                  {{ a.author_nickname.slice(0, 1) }}
                </el-avatar>
                <div class="who">
                  <div class="who-line">
                    <span class="author" @click="router.push(`/u/${a.author_id}`)">
                      {{ a.author_nickname }}
                    </span>
                    <el-tag v-if="a.is_best" type="success" effect="dark" size="small">最佳</el-tag>
                    <el-tag v-else-if="a.is_accepted" type="success" effect="plain" size="small">已采纳</el-tag>
                    <!-- AI 可靠性徽标（V1.3）：异步生成，仅供参考 -->
                    <el-tooltip
                      v-if="a.ai_rel_level"
                      :content="`AI 可靠性评估：${a.ai_rel_score} 分（仅供参考，不代表官方认定）`"
                    >
                      <el-tag
                        size="small"
                        effect="plain"
                        :type="a.ai_rel_level === '高' ? 'success' : a.ai_rel_level === '中' ? 'warning' : 'danger'"
                      >
                        <el-icon><MagicStick /></el-icon>&nbsp;{{ a.ai_rel_level }}
                      </el-tag>
                    </el-tooltip>
                  </div>
                  <div class="answer-time">{{ fmtTime(a.created_at) }}</div>
                </div>
              </div>

              <p class="answer-content">{{ a.content }}</p>

              <!-- 回答操作栏（知乎式：赞同大按钮 + 分享 + 评论入口 + 采纳 + ···） -->
              <div class="answer-actions-bar">
                <button
                  class="vote-btn"
                  :class="{ voted: a.is_liked }"
                  @click="toggleLike(2, a.id, a)"
                >
                  <el-icon><CaretTop /></el-icon>
                  <span>赞同</span>
                  <span class="vote-num">{{ a.like_count }}</span>
                </button>
                <button class="op-btn" @click="share">
                  <el-icon><Share /></el-icon>
                  <span>分享</span>
                </button>
                <button class="op-btn" @click="toggleComments(a.id)">
                  <el-icon><ChatDotRound /></el-icon>
                  <span>
                    {{ expandedComments[a.id] ? '收起评论' : `${commentCounts[a.id] ?? 0} 条评论` }}
                  </span>
                </button>
                <el-button
                  v-if="auth.user?.id === post.author_id && post.status === 0 && !a.is_accepted"
                  size="small"
                  type="success"
                  plain
                  class="accept-btn"
                  @click="acceptAnswer(a.id)"
                >
                  采纳
                </el-button>
                <el-dropdown trigger="click">
                  <button class="op-btn">
                    <el-icon><MoreFilled /></el-icon>
                  </button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item @click="reportRef?.open(2, a.id)">
                        <el-icon><WarningFilled /></el-icon>举报回答
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>

              <!-- 评论（知乎式：默认收起） -->
              <div v-show="expandedComments[a.id]" class="answer-comments">
                <CommentThread
                  :target-type="2"
                  :target-id="a.id"
                  @loaded="(n: number) => onCommentsLoaded(a.id, n)"
                />
              </div>
            </div>
          </div>

          <!-- 问题评论（功能保留：主列底部） -->
          <div class="cx-card">
            <h3 class="section-title">问题评论</h3>
            <CommentThread :target-type="1" :target-id="post.id" />
          </div>
        </div>

        <!-- ============ 右侧栏：数据卡 + 相关问题 ============ -->
        <aside class="side">
          <div class="cx-card side-card">
            <div class="side-title">问题信息</div>
            <div class="info-rows">
              <div class="info-row">
                <span class="k">状态</span>
                <span class="v">{{ post.status === 1 ? '已解决' : '待解决' }}</span>
              </div>
              <div class="info-row">
                <span class="k">回答</span>
                <span class="v">{{ post.answers.length }}</span>
              </div>
              <div class="info-row">
                <span class="k">浏览</span>
                <span class="v">{{ post.view_count }}</span>
              </div>
              <div v-if="post.reward > 0" class="info-row">
                <span class="k">悬赏</span>
                <span class="v reward">{{ post.reward }} 积分</span>
              </div>
              <div class="info-row">
                <span class="k">发布</span>
                <span class="v">{{ fmtTime(post.created_at) }}</span>
              </div>
              <div class="info-row">
                <span class="k">提问者</span>
                <span class="v link" @click="router.push(`/u/${post.author_id}`)">
                  {{ post.author_nickname }}
                </span>
              </div>
            </div>
          </div>

          <div v-if="similar.length" class="cx-card side-card">
            <div class="side-title">相关问题</div>
            <div
              v-for="s in similar"
              :key="s.id"
              class="similar-row"
              @click="router.push(`/posts/${s.id}`)"
            >
              <el-tag size="small" :type="s.status === 1 ? 'success' : 'warning'" effect="plain">
                {{ s.status === 1 ? '已解决' : '待解决' }}
              </el-tag>
              <div class="s-body">
                <div class="s-title">{{ s.title }}</div>
                <div class="s-meta">{{ s.answer_count }} 回答 · {{ s.view_count }} 浏览</div>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </template>

    <div v-else-if="!loading" class="cx-empty">
      <p>帖子不存在或已删除</p>
      <router-link to="/feed">返回广场</router-link>
    </div>

    <ReportDialog ref="reportRef" />
  </div>
</template>

<style scoped>
/* ===== 双栏骨架（知乎式：主列 + 侧栏，整体铺满内容区） ===== */
.detail {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 16px;
  align-items: start;
}

.main {
  min-width: 0;
}

.side {
  position: sticky;
  top: 120px; /* 双标题栏总高（56+48）+ 间距 */
}

@media (max-width: 1000px) {
  .detail {
    grid-template-columns: 1fr;
  }

  .side {
    position: static;
  }
}

/* ===== 问题卡 ===== */
.q-head {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.title {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 10px;
  line-height: 1.4;
}

.meta {
  display: flex;
  gap: 14px;
  color: #999;
  font-size: 13px;
  margin: 8px 0;
}

.author {
  color: var(--el-color-primary);
  cursor: pointer;
}

.content {
  color: #333;
  line-height: 1.8;
  white-space: pre-wrap;
  margin: 12px 0;
  font-size: 15px;
}

.ai-summary {
  margin: 12px 0;
  padding: 12px 14px;
  border-left: 3px solid #a29bfe;
  border-radius: 6px;
  background: linear-gradient(135deg, rgba(108, 92, 231, 0.06), rgba(162, 155, 254, 0.1));
}

.ai-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #6c5ce7;
}

.ai-tip {
  font-weight: 400;
  font-size: 11px;
  color: #b3aef0;
}

.ai-text {
  margin: 8px 0 0;
  color: #555;
  line-height: 1.7;
  font-size: 14px;
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

.q-tags {
  display: flex;
  gap: 6px;
  margin-top: 12px;
}

/* ===== 操作栏（知乎式按钮） ===== */
.q-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f2f2f2;
}

.vote-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 14px;
  border: 1px solid var(--el-color-primary);
  border-radius: 6px;
  background: #fff;
  color: var(--el-color-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.vote-btn:hover {
  background: var(--el-color-primary-light-9);
}

.vote-btn.voted {
  background: var(--el-color-primary);
  color: #fff;
}

.vote-num {
  font-weight: 700;
}

.op-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 7px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #666;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.op-btn:hover {
  background: #f5f5f6;
  color: var(--el-color-primary);
}

.op-btn.on {
  color: var(--el-color-warning);
}

/* ===== 写回答 ===== */
.write-answer {
  margin-top: 16px;
}

.write-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

/* ===== 回答列表 ===== */
.cx-card + .cx-card {
  margin-top: 16px;
}

.answers-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.section-title {
  margin: 0;
  font-size: 16px;
}

.ai-ref-answer {
  margin: 4px 0 16px;
  padding: 14px 16px;
  border: 1px dashed #b3aef0;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(108, 92, 231, 0.04), rgba(162, 155, 254, 0.08));
}

.ai-ref-text {
  margin: 10px 0 0;
  color: #444;
  line-height: 1.8;
  font-size: 14px;
  white-space: pre-wrap;
}

.ai-ref-trigger {
  margin-bottom: 12px;
}

.answer {
  padding: 18px 0 14px;
  border-bottom: 1px solid #f2f2f2;
}

.answer:last-child {
  border-bottom: none;
}

.answer-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar {
  background: var(--el-color-primary-light-7);
  cursor: pointer;
  flex-shrink: 0;
}

.who {
  min-width: 0;
}

.who-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.answer-time {
  color: #999;
  font-size: 12px;
  margin-top: 2px;
}

.answer-content {
  color: #333;
  line-height: 1.8;
  white-space: pre-wrap;
  margin: 10px 0 12px;
  font-size: 15px;
}

/* ===== 回答操作栏 ===== */
.answer-actions-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.accept-btn {
  margin-left: 4px;
}

.answer-comments {
  margin-top: 12px;
  padding: 12px 14px;
  background: #fafafa;
  border-radius: 8px;
}

/* ===== 侧栏 ===== */
.side-card + .side-card {
  margin-top: 16px;
}

.side-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
}

.info-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}

.info-row .k {
  color: #999;
}

.info-row .v {
  color: #333;
  font-weight: 600;
}

.info-row .v.reward {
  color: var(--el-color-danger);
}

.info-row .v.link {
  color: var(--el-color-primary);
  cursor: pointer;
}

.similar-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 0;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;
}

.similar-row:last-child {
  border-bottom: none;
}

.s-body {
  flex: 1;
  min-width: 0;
}

.s-title {
  font-size: 14px;
  line-height: 1.5;
  color: #333;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.similar-row:hover .s-title {
  color: var(--el-color-primary);
}

.s-meta {
  color: #999;
  font-size: 12px;
  margin-top: 3px;
}
</style>
