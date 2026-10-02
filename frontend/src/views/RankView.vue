<script setup lang="ts">
/**
 * S11d 助人榜（M7-F29）+ V1.14 多维化 + V1.15 感谢值当期实时：
 * 感谢值/回答数/采纳数均为当期实时榜，点击跳个人主页。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { get } from '@/api/http'
import DecorAvatar from '@/components/DecorAvatar.vue'
import UserDecor from '@/components/UserDecor.vue'

interface RankUser {
  id: number
  nickname: string
  avatar: string | null
  school: string
  major: string
  equipped?: Record<string, { product_id: number; name: string; payload: string }> | null
}

interface RankItem {
  rank: number
  user: RankUser
  value: number
}

interface RankData {
  period: string
  settling: boolean
  items: RankItem[]
}

type Metric = 'gratitude' | 'answers' | 'accepts'

const router = useRouter()
const metric = ref<Metric>('gratitude')
const period = ref<'day' | 'week' | 'month'>('week')
const data = ref<RankData | null>(null)
const loading = ref(false)

const unitText = computed(() =>
  metric.value === 'gratitude' ? '感谢值' : metric.value === 'answers' ? '回答' : '采纳',
)

const emptyText = computed(() =>
  metric.value === 'gratitude'
    ? '暂无上榜数据，回答被采纳即可累积感谢值'
    : metric.value === 'answers'
      ? '本期暂无回答，回答问题即可上榜'
      : '本期暂无采纳，回答被提问者采纳即可上榜',
)

function onMetricChange(val: Metric) {
  metric.value = val
  // 感谢值仅支持周/月：从日榜切回时纠正（watch(period) 会触发重新拉取）
  if (val === 'gratitude' && period.value === 'day') {
    period.value = 'week'
    return
  }
  fetchRank()
}

async function fetchRank() {
  loading.value = true
  try {
    data.value = await get<RankData>('/ranks', { metric: metric.value, period: period.value })
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

onMounted(fetchRank)
watch(period, fetchRank)
</script>

<template>
  <div class="cx-card rank">
    <div class="head-row">
      <h2>助人榜</h2>
      <div class="switches">
        <el-radio-group :model-value="metric" size="small" @change="onMetricChange">
          <el-radio-button value="gratitude">感谢值</el-radio-button>
          <el-radio-button value="answers">回答数</el-radio-button>
          <el-radio-button value="accepts">采纳数</el-radio-button>
        </el-radio-group>
        <el-radio-group v-model="period" size="small">
          <el-radio-button v-if="metric !== 'gratitude'" value="day">日榜</el-radio-button>
          <el-radio-button value="week">周榜</el-radio-button>
          <el-radio-button value="month">月榜</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <div v-loading="loading" class="list">
      <template v-if="data?.items.length">
        <!-- 前三名领奖台 -->
        <div class="podium">
          <div
            v-for="it in data.items.slice(0, 3)"
            :key="it.rank"
            class="podium-item"
            :class="`top-${it.rank}`"
            @click="router.push(`/u/${it.user.id}`)"
          >
            <div class="medal">{{ it.rank }}</div>
            <DecorAvatar :size="48" :src="it.user.avatar" :name="it.user.nickname" :equipped="it.user.equipped" />
            <span class="p-name">{{ it.user.nickname }}</span>
            <UserDecor :equipped="it.user.equipped" />
            <span class="p-value">{{ it.value }} {{ unitText }}</span>
          </div>
        </div>

        <!-- 4 名以后列表 -->
        <div v-if="data.items.length > 3" class="rest">
          <div
            v-for="it in data.items.slice(3)"
            :key="it.rank"
            class="rest-item"
            @click="router.push(`/u/${it.user.id}`)"
          >
            <span class="r-rank">{{ it.rank }}</span>
            <span class="r-name">{{ it.user.nickname }}</span>
            <UserDecor :equipped="it.user.equipped" />
            <span v-if="it.user.school" class="r-school">{{ it.user.school }}</span>
            <span class="r-value">{{ it.value }}</span>
          </div>
        </div>
      </template>
      <el-empty v-else-if="!loading" :description="emptyText" />
    </div>
  </div>
</template>

<style scoped>
.rank {
  padding: 20px 24px 24px;
}

.head-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.head-row h2 {
  margin: 0;
  font-size: 18px;
}

.switches {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.settling-tip {
  margin-bottom: 12px;
}

.list {
  min-height: 160px;
}

.podium {
  display: flex;
  justify-content: center;
  align-items: flex-end;
  gap: 16px;
  padding: 16px 0 8px;
}

.podium-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 12px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
  min-width: 110px;
  transition: transform 0.2s;
}

.podium-item:hover {
  transform: translateY(-2px);
}

.medal {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  background: #999;
}

.top-1 .medal {
  background: #f5a623;
}

.top-1 {
  order: 2;
  padding-top: 20px;
}

.top-2 .medal {
  background: #b8b8b8;
}

.top-2 {
  order: 1;
}

.top-3 .medal {
  background: #cd7f57;
}

.top-3 {
  order: 3;
}

.p-avatar {
  background: var(--el-color-primary-light-5);
}

.p-name {
  font-weight: 600;
  font-size: 14px;
}

.p-value {
  color: #999;
  font-size: 12px;
}

.rest {
  margin-top: 12px;
}

.rest-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  font-size: 14px;
}

.rest-item:hover {
  background: var(--el-fill-color-light);
}

.r-rank {
  width: 24px;
  text-align: center;
  color: #999;
  font-weight: 600;
}

.r-name {
  font-weight: 600;
}

.r-school {
  color: #999;
  font-size: 12px;
  flex: 1;
}

.r-value {
  margin-left: auto;
  color: #f5a623;
  font-weight: 600;
}
</style>
