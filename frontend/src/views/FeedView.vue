<script setup lang="ts">
/** 广场：三 Tab（最新/待解决/推荐）+ 分页帖子流。 */
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { get } from '@/api/http'
import type { Page, PostCard } from '@/api/types'
import PostCardItem from '@/components/PostCardItem.vue'

const route = useRoute()
const tab = ref<'latest' | 'unsolved' | 'recommend'>(
  (route.query.tab as 'latest') || 'latest',
)
const page = ref(1)
const total = ref(0)
const items = ref<PostCard[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await get<Page<PostCard>>('/feed', {
      tab: tab.value,
      page: page.value,
      page_size: 20,
    })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch([tab, page], load)
</script>

<template>
  <div>
    <el-tabs v-model="tab" class="feed-tabs">
      <el-tab-pane label="最新" name="latest" />
      <el-tab-pane label="待解决" name="unsolved" />
      <el-tab-pane label="推荐" name="recommend" />
    </el-tabs>

    <div v-loading="loading">
      <template v-if="items.length">
        <PostCardItem v-for="p in items" :key="p.id" :post="p" />
      </template>
      <div v-else-if="!loading" class="cx-empty">
        <p>暂无帖子</p>
        <p style="font-size: 12px">成为第一个提问的人吧</p>
      </div>
    </div>

    <div v-if="total > 20" class="pager">
      <el-pagination
        v-model:current-page="page"
        :total="total"
        :page-size="20"
        layout="prev, pager, next"
        background
      />
    </div>
  </div>
</template>

<style scoped>
.feed-tabs {
  background: #fff;
  border-radius: 8px;
  padding: 0 16px;
  margin-bottom: 12px;
}

.pager {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
