<script setup lang="ts">
/**
 * V1.12 个人中心（/me）：本人个性化内容一站式管理。
 * 六 Tab：我的提问/回答/评论/点赞/收藏/积分明细（个人主页 /u/:id 只留基本信息与公开内容）。
 */
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { get } from '@/api/http'
import type { MyAnswerItem, MyCommentItem, MyLikeItem, Page, PostCard } from '@/api/types'
import PostCardItem from '@/components/PostCardItem.vue'

const router = useRouter()

const tab = ref('posts')
const statusFilter = ref<0 | 1 | null>(null)
const favType = ref<1 | 2>(1)
const page = ref(1)
const total = ref(0)
const listLoading = ref(false)

const posts = ref<PostCard[]>([])
const answers = ref<MyAnswerItem[]>([])
const comments = ref<MyCommentItem[]>([])
const likes = ref<MyLikeItem[]>([])
const favPosts = ref<PostCard[]>([])
const favAnswers = ref<{
  answer_id: number
  post_id: number
  post_title: string
  content: string
  author_nickname: string
  created_at: string
}[]>([])
const creditLogs = ref<{
  id: number
  change: number
  balance_after: number
  source_text: string
  note: string
  created_at: string
}[]>([])

async function fetchList() {
  listLoading.value = true
  try {
    if (tab.value === 'posts') {
      const r = await get<Page<PostCard>>('/account/my-posts', {
        status: statusFilter.value ?? undefined,
        page: page.value,
      })
      posts.value = r.items
      total.value = r.total
    } else if (tab.value === 'answers') {
      const r = await get<Page<MyAnswerItem>>('/account/my-answers', { page: page.value })
      answers.value = r.items
      total.value = r.total
    } else if (tab.value === 'comments') {
      const r = await get<Page<MyCommentItem>>('/account/my-comments', { page: page.value })
      comments.value = r.items
      total.value = r.total
    } else if (tab.value === 'likes') {
      const r = await get<Page<MyLikeItem>>('/account/my-likes', { page: page.value })
      likes.value = r.items
      total.value = r.total
    } else if (tab.value === 'favorites') {
      if (favType.value === 1) {
        const r = await get<Page<PostCard>>('/favorites', { target_type: 1, page: page.value })
        favPosts.value = r.items
        total.value = r.total
      } else {
        const r = await get<Page<(typeof favAnswers.value)[number]>>('/favorites', {
          target_type: 2,
          page: page.value,
        })
        favAnswers.value = r.items
        total.value = r.total
      }
    } else {
      const r = await get<Page<(typeof creditLogs.value)[number]>>('/credit/logs', { page: page.value })
      creditLogs.value = r.items
      total.value = r.total
    }
  } catch {
    // 拦截器已提示
  } finally {
    listLoading.value = false
  }
}

function resetAndFetch() {
  page.value = 1
  total.value = 0
  fetchList()
}

onMounted(fetchList)
watch([tab, statusFilter, favType], resetAndFetch)
watch(page, fetchList)

function fmtTime(s: string | null) {
  return s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : ''
}

const LIKE_TYPE_TEXT: Record<number, string> = { 1: '帖子', 2: '回答', 3: '评论' }
</script>

<template>
  <div class="cx-card me-center">
    <el-tabs v-model="tab">
      <el-tab-pane label="我的提问" name="posts" />
      <el-tab-pane label="我的回答" name="answers" />
      <el-tab-pane label="我的评论" name="comments" />
      <el-tab-pane label="我的点赞" name="likes" />
      <el-tab-pane label="我的收藏" name="favorites" />
      <el-tab-pane label="积分明细" name="credits" />
    </el-tabs>

    <!-- 我的提问 -->
    <template v-if="tab === 'posts'">
      <el-radio-group v-model="statusFilter" size="small" class="filter">
        <el-radio-button :value="null">全部</el-radio-button>
        <el-radio-button :value="0">待解决</el-radio-button>
        <el-radio-button :value="1">已解决</el-radio-button>
      </el-radio-group>
      <div v-loading="listLoading" class="list">
        <PostCardItem v-for="p in posts" :key="p.id" :post="p" />
        <el-empty v-if="!listLoading && !posts.length" description="还没有发布过提问" />
      </div>
    </template>

    <!-- 我的回答 -->
    <template v-else-if="tab === 'answers'">
      <div v-loading="listLoading" class="list">
        <div
          v-for="a in answers"
          :key="a.id"
          class="row-card"
          @click="a.post_id && router.push(`/posts/${a.post_id}`)"
        >
          <div class="row-head">
            <span class="row-title">
              {{ a.post_title || '原提问已删除' }}
            </span>
            <span class="badges">
              <el-tag v-if="a.is_best" type="success" effect="dark" size="small">最佳</el-tag>
              <el-tag v-else-if="a.is_accepted" type="success" effect="plain" size="small">已采纳</el-tag>
            </span>
          </div>
          <p class="row-content">{{ a.content }}</p>
          <div class="row-meta">
            <span>{{ fmtTime(a.created_at) }}</span>
            <span>获赞 {{ a.like_count }}</span>
          </div>
        </div>
        <el-empty v-if="!listLoading && !answers.length" description="还没有回答过问题" />
      </div>
    </template>

    <!-- 我的评论 -->
    <template v-else-if="tab === 'comments'">
      <div v-loading="listLoading" class="list">
        <div
          v-for="c in comments"
          :key="c.id"
          class="row-card"
          @click="c.post_id && router.push(`/posts/${c.post_id}`)"
        >
          <div class="row-head">
            <el-tag size="small" effect="plain" :type="c.target_type === 1 ? 'primary' : 'warning'">
              {{ c.target_type === 1 ? '问题评论' : '回答评论' }}
            </el-tag>
            <span class="row-title">{{ c.post_title || '原内容已删除' }}</span>
          </div>
          <p class="row-content">{{ c.content }}</p>
          <div class="row-meta">
            <span>{{ fmtTime(c.created_at) }}</span>
          </div>
        </div>
        <el-empty v-if="!listLoading && !comments.length" description="还没有发表过评论" />
      </div>
    </template>

    <!-- 我的点赞 -->
    <template v-else-if="tab === 'likes'">
      <div v-loading="listLoading" class="list">
        <div
          v-for="(l, i) in likes"
          :key="`${l.target_type}-${l.target_id}-${i}`"
          class="row-card"
          @click="l.post_id && router.push(`/posts/${l.post_id}`)"
        >
          <div class="row-head">
            <el-tag size="small" effect="plain">
              赞过{{ LIKE_TYPE_TEXT[l.target_type] }}
            </el-tag>
            <span class="row-title">{{ l.post_title || '原内容已删除' }}</span>
          </div>
          <p class="row-content">{{ l.content }}</p>
          <div class="row-meta">
            <span v-if="l.author_nickname">作者 {{ l.author_nickname }}</span>
            <span>{{ fmtTime(l.created_at) }}</span>
          </div>
        </div>
        <el-empty v-if="!listLoading && !likes.length" description="还没有点赞过内容" />
      </div>
    </template>

    <!-- 我的收藏 -->
    <template v-else-if="tab === 'favorites'">
      <el-radio-group v-model="favType" size="small" class="filter">
        <el-radio-button :value="1">帖子</el-radio-button>
        <el-radio-button :value="2">回答</el-radio-button>
      </el-radio-group>
      <div v-loading="listLoading" class="list">
        <template v-if="favType === 1">
          <PostCardItem v-for="p in favPosts" :key="p.id" :post="p" />
        </template>
        <template v-else>
          <div
            v-for="f in favAnswers"
            :key="f.answer_id"
            class="row-card"
            @click="router.push(`/posts/${f.post_id}`)"
          >
            <div class="row-head">
              <span class="row-title">{{ f.post_title }}</span>
            </div>
            <p class="row-content">{{ f.content }}</p>
            <div class="row-meta">
              <span>{{ f.author_nickname }}</span>
              <span>{{ fmtTime(f.created_at) }}</span>
            </div>
          </div>
        </template>
        <el-empty
          v-if="!listLoading && ((favType === 1 && !favPosts.length) || (favType === 2 && !favAnswers.length))"
          description="还没有收藏内容"
        />
      </div>
    </template>

    <!-- 积分明细 -->
    <template v-else>
      <div v-loading="listLoading" class="list">
        <div v-for="l in creditLogs" :key="l.id" class="credit-row">
          <div class="credit-info">
            <span class="credit-source">{{ l.source_text }}</span>
            <span class="credit-note">{{ l.note }}</span>
            <span class="credit-time">{{ fmtTime(l.created_at) }}</span>
          </div>
          <div class="credit-right">
            <span class="change" :class="l.change > 0 ? 'plus' : 'minus'">
              {{ l.change > 0 ? '+' : '' }}{{ l.change }}
            </span>
            <span class="after">余额 {{ l.balance_after }}</span>
          </div>
        </div>
        <el-empty v-if="!listLoading && !creditLogs.length" description="暂无积分流水" />
      </div>
    </template>

    <div v-if="total > 20" class="pager">
      <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="prev, pager, next" background />
    </div>
  </div>
</template>

<style scoped>
.me-center {
  padding: 16px 24px 24px;
}

.filter {
  margin-bottom: 12px;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 100px;
}

.row-card {
  padding: 14px 16px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  cursor: pointer;
  transition: box-shadow 0.15s;
}

.row-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.row-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.row-title {
  font-weight: 600;
  font-size: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-content {
  color: #666;
  margin: 8px 0 6px;
  font-size: 14px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.row-meta {
  display: flex;
  gap: 14px;
  color: #999;
  font-size: 12px;
}

.credit-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.credit-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.credit-source {
  font-weight: 600;
  font-size: 14px;
}

.credit-note {
  color: #999;
  font-size: 12px;
}

.credit-time {
  color: #bbb;
  font-size: 12px;
}

.credit-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}

.change.plus {
  color: var(--el-color-success);
  font-weight: 700;
}

.change.minus {
  color: var(--el-color-danger);
  font-weight: 700;
}

.after {
  color: #999;
  font-size: 12px;
}

.pager {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
