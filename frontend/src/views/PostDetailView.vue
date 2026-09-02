<script setup lang="ts">
// S11b 实现：帖子详情（回答/评论渲染/采纳）（占位）
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="cx-empty">
    <h2>帖子详情 #{{ route.params.id }}</h2>
    <p>S11b 子增量实现</p>
  </div>
</template>
