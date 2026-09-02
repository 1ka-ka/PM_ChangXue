<script setup lang="ts">
/** 帖子卡片：广场/搜索/我的帖子 复用。 */
import type { PostCard } from '@/api/types'
import { useRouter } from 'vue-router'

defineProps<{ post: PostCard }>()
const router = useRouter()
</script>

<template>
  <div class="cx-card post-card" @click="router.push(`/posts/${post.id}`)">
    <div class="head">
      <el-tag :type="post.status === 1 ? 'success' : 'warning'" size="small" effect="dark">
        {{ post.status === 1 ? '已解决' : '待解决' }}
      </el-tag>
      <span class="title">{{ post.title }}</span>
      <el-tag v-if="post.reward > 0" type="danger" size="small" effect="plain" class="reward">
        悬赏 {{ post.reward }}
      </el-tag>
    </div>
    <p class="summary">{{ post.summary }}</p>
    <div class="meta">
      <span class="tags">
        <el-tag v-for="t in post.tags" :key="t.id" size="small" effect="plain">{{ t.name }}</el-tag>
      </span>
      <span class="stats">
        <span v-if="post.no_answer_days" class="no-answer">已 {{ post.no_answer_days }} 天未有回答</span>
        <span>{{ post.answer_count }} 回答</span>
        <span>{{ post.like_count }} 赞</span>
        <span>{{ post.view_count }} 浏览</span>
        <span class="author">{{ post.author_nickname }}</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.post-card {
  cursor: pointer;
  transition: box-shadow 0.2s;
}

.post-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.title {
  font-size: 16px;
  font-weight: 600;
  color: #222;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reward {
  flex-shrink: 0;
}

.summary {
  color: #666;
  margin: 8px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  color: #999;
  font-size: 12px;
}

.tags {
  display: flex;
  gap: 4px;
  overflow: hidden;
}

.stats {
  display: flex;
  gap: 12px;
  flex-shrink: 0;
}

.no-answer {
  color: var(--el-color-danger);
}

.author {
  color: #777;
}
</style>
