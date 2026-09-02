<script setup lang="ts">
// S11.3 实现：个人主页（资料/积分明细/收藏/我的帖子）（占位）
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="cx-empty">
    <h2>个人主页 #{{ route.params.id }}</h2>
    <p>S11.3 子增量实现</p>
  </div>
</template>
