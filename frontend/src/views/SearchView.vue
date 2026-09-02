<script setup lang="ts">
/**
 * S11c 搜索页（M4-F14）：知识库优先 → 降级广场（提示）→ 空态引导。
 * 关键词 + 标签筛选（至少一项）；结果复用 PostCardItem。
 */
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { get } from '@/api/http'
import type { Page, PostCard, TagItem } from '@/api/types'
import PostCardItem from '@/components/PostCardItem.vue'
import { useAuthStore } from '@/stores/auth'

interface SearchResult extends Page<PostCard> {
  source: 'kb' | 'plaza' | 'empty'
  degraded?: boolean
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const keyword = ref('')
const tagId = ref<number | null>(null)
const tags = ref<TagItem[]>([])
const result = ref<SearchResult | null>(null)
const loading = ref(false)
const page = ref(1)

onMounted(async () => {
  try {
    const r = await get<{ items: TagItem[] }>('/tags')
    tags.value = r.items
  } catch {
    // 标签加载失败不阻塞搜索
  }
  keyword.value = (route.query.q as string) || ''
  tagId.value = route.query.tag_id ? Number(route.query.tag_id) : null
  if (keyword.value || tagId.value) fetchResult()
})

// 顶栏搜索框跳转（query 变化）时同步并搜索（本页发起的 replace 已 fetch，跳过）
watch(
  () => route.query,
  (q) => {
    const newKw = (q.q as string) || ''
    const newTag = q.tag_id ? Number(q.tag_id) : null
    if (newKw === keyword.value && newTag === tagId.value) return
    keyword.value = newKw
    tagId.value = newTag
    if (newKw || newTag) fetchResult()
  },
)

function applySearch() {
  page.value = 1
  router.replace({
    path: '/search',
    query: {
      ...(keyword.value.trim() ? { q: keyword.value.trim() } : {}),
      ...(tagId.value ? { tag_id: String(tagId.value) } : {}),
    },
  })
  fetchResult()
}

async function fetchResult() {
  if (!keyword.value.trim() && !tagId.value) {
    ElMessage.warning('请输入关键词或选择标签')
    return
  }
  loading.value = true
  try {
    result.value = await get<SearchResult>('/search', {
      q: keyword.value.trim() || undefined,
      tag_id: tagId.value ?? undefined,
      page: page.value,
    })
  } catch {
    // http 拦截器已提示
  } finally {
    loading.value = false
  }
}

function changePage(p: number) {
  page.value = p
  fetchResult()
}
</script>

<template>
  <div class="cx-card search">
    <div class="search-bar">
      <el-input
        v-model="keyword"
        placeholder="搜索问题（知识库优先）"
        size="large"
        maxlength="50"
        clearable
        @keyup.enter="applySearch"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select
        v-model="tagId"
        placeholder="按标签筛选"
        clearable
        size="large"
        class="tag-select"
      >
        <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
      </el-select>
      <el-button type="primary" size="large" round :loading="loading" @click="applySearch">
        搜索
      </el-button>
    </div>

    <template v-if="result">
      <!-- 来源提示：知识库命中 / 降级广场 -->
      <el-alert
        v-if="result.source === 'kb'"
        :title="`知识库命中 ${result.total} 条已采纳沉淀的问答`"
        type="success"
        :closable="false"
        class="source-tip"
      />
      <el-alert
        v-else-if="result.source === 'plaza'"
        title="知识库暂无相关内容，已为你搜索广场帖子"
        type="warning"
        :closable="false"
        class="source-tip"
      />

      <div v-loading="loading" class="results">
        <template v-if="result.items.length">
          <PostCardItem v-for="p in result.items" :key="p.id" :post="p" />
        </template>
        <!-- 空态引导 -->
        <div v-else class="cx-empty empty-guide">
          <h3>没有找到相关内容</h3>
          <p>换个关键词试试，或切换标签筛选</p>
          <el-button
            v-if="auth.isLogged"
            type="primary"
            round
            @click="router.push('/posts/create')"
          >
            我要提问
          </el-button>
          <span v-else class="login-tip" @click="router.push('/login')">登录后提问，获取学长学姐帮助</span>
        </div>
      </div>

      <div v-if="result.total > 20" class="pager">
        <el-pagination
          :current-page="page"
          :total="result.total"
          :page-size="20"
          layout="prev, pager, next"
          background
          @current-change="changePage"
        />
      </div>
    </template>

    <!-- 初始态：未搜索 -->
    <div v-else-if="!loading" class="cx-empty init">
      <h3>搜一搜学长学姐的答案</h3>
      <p>输入关键词或选择学科标签开始搜索，已采纳的优质问答会优先展示</p>
    </div>
  </div>
</template>

<style scoped>
.search {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px;
}

.search-bar {
  display: flex;
  gap: 12px;
}

.tag-select {
  width: 160px;
  flex-shrink: 0;
}

.source-tip {
  margin-top: 16px;
}

.results {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 120px;
}

.empty-guide {
  padding: 40px 0;
}

.empty-guide h3,
.init h3 {
  margin: 0 0 8px;
}

.empty-guide p,
.init p {
  color: #999;
  margin: 0 0 16px;
}

.login-tip {
  color: var(--el-color-primary);
  cursor: pointer;
  font-size: 14px;
}

.init {
  padding: 60px 0;
}

.pager {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
