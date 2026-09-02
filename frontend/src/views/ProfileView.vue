<script setup lang="ts">
/**
 * S11d 个人主页（M2-F05/F06）：公开视角 + 本人视角 Tabs（我的帖子/收藏/积分明细）+ 资料编辑。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { get, put } from '@/api/http'
import type { Page, PostCard } from '@/api/types'
import PostCardItem from '@/components/PostCardItem.vue'
import { useAuthStore } from '@/stores/auth'

interface Gratitude {
  week: number
  month: number
  total: number
}

interface ProfileInfo {
  id: number
  nickname: string
  avatar: string | null
  school: string
  major: string
  gratitude: Gratitude
  is_self: boolean
  phone?: string
  credit_balance?: number
}

interface CreditLogItem {
  id: number
  change: number
  balance_after: number
  source_text: string
  note: string
  created_at: string
}

interface FavAnswerItem {
  answer_id: number
  post_id: number
  post_title: string
  content: string
  author_nickname: string
  created_at: string
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const info = ref<ProfileInfo | null>(null)
const loading = ref(false)
const tab = ref('posts')
const statusFilter = ref<0 | 1 | null>(null)
const favType = ref<1 | 2>(1)
const page = ref(1)
const total = ref(0)
const items = ref<PostCard[]>([])
const favAnswerItems = ref<FavAnswerItem[]>([])
const creditLogs = ref<CreditLogItem[]>([])
const listLoading = ref(false)

// 资料编辑
const editVisible = ref(false)
const editForm = ref({ nickname: '', school: '', major: '' })
const saving = ref(false)

const isSelf = computed(() => info.value?.is_self ?? false)

async function fetchInfo() {
  loading.value = true
  try {
    info.value = await get<ProfileInfo>(`/account/users/${route.params.id}`)
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function fetchList() {
  if (!isSelf.value) return
  listLoading.value = true
  try {
    if (tab.value === 'posts') {
      const r = await get<Page<PostCard>>('/account/my-posts', {
        status: statusFilter.value ?? undefined,
        page: page.value,
      })
      items.value = r.items
      total.value = r.total
    } else if (tab.value === 'favorites') {
      if (favType.value === 1) {
        const r = await get<Page<PostCard>>('/favorites', { target_type: 1, page: page.value })
        items.value = r.items
        total.value = r.total
      } else {
        const r = await get<Page<FavAnswerItem>>('/favorites', { target_type: 2, page: page.value })
        favAnswerItems.value = r.items
        total.value = r.total
      }
    } else {
      const r = await get<Page<CreditLogItem>>('/credit/logs', { page: page.value })
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
  items.value = []
  favAnswerItems.value = []
  creditLogs.value = []
  fetchList()
}

onMounted(fetchInfo)
watch(() => route.params.id, () => fetchInfo())
watch([tab, statusFilter, favType], resetAndFetch)
watch(isSelf, (v) => v && fetchList())
watch(page, fetchList)

function openEdit() {
  if (!info.value) return
  editForm.value = {
    nickname: info.value.nickname,
    school: info.value.school || '',
    major: info.value.major || '',
  }
  editVisible.value = true
}

async function saveEdit() {
  if (!editForm.value.nickname.trim()) {
    ElMessage.warning('昵称不能为空')
    return
  }
  saving.value = true
  try {
    await put('/account/profile', {
      nickname: editForm.value.nickname.trim(),
      school: editForm.value.school.trim(),
      major: editForm.value.major.trim(),
    })
    ElMessage.success('资料已更新')
    editVisible.value = false
    await fetchInfo()
    await auth.fetchMe()
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

async function uploadAvatar(evt: Event) {
  const file = (evt.target as HTMLInputElement).files?.[0]
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  try {
    const { http } = await import('@/api/http')
    const r = (await http.post('/account/avatar', fd)) as { url: string }
    ElMessage.success('头像已更新')
    await fetchInfo()
    await auth.fetchMe()
    void r
  } catch {
    // 拦截器已提示
  }
  (evt.target as HTMLInputElement).value = ''
}

function fmtTime(s: string | null) {
  return s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : ''
}
</script>

<template>
  <div v-loading="loading" class="profile">
    <!-- 用户信息头 -->
    <div class="cx-card head-card">
      <div class="head">
        <div class="avatar-wrap" :class="{ self: isSelf }">
          <el-avatar :size="72" :src="info?.avatar || undefined" class="avatar">
            {{ info?.nickname?.slice(0, 1) }}
          </el-avatar>
          <label v-if="isSelf" class="avatar-edit" title="更换头像">
            <el-icon><Camera /></el-icon>
            <input type="file" accept="image/jpeg,image/png,image/webp" hidden @change="uploadAvatar" />
          </label>
        </div>
        <div class="info">
          <div class="name-row">
            <h2>{{ info?.nickname }}</h2>
            <el-button v-if="isSelf" size="small" round @click="openEdit">编辑资料</el-button>
          </div>
          <p class="sub">
            <span v-if="info?.school">{{ info.school }}</span>
            <span v-if="info?.major">{{ info.major }}</span>
            <span v-if="!info?.school && !info?.major" class="muted">这位同学还没有填写学校与专业</span>
            <span v-if="isSelf && info?.phone" class="muted">{{ info.phone }}</span>
          </p>
        </div>
        <div class="stats">
          <div class="stat">
            <b>{{ info?.gratitude?.week ?? 0 }}</b>
            <span>本周感谢值</span>
          </div>
          <div class="stat">
            <b>{{ info?.gratitude?.month ?? 0 }}</b>
            <span>本月感谢值</span>
          </div>
          <div class="stat">
            <b>{{ info?.gratitude?.total ?? 0 }}</b>
            <span>累计感谢值</span>
          </div>
          <div v-if="isSelf" class="stat credit">
            <b>{{ info?.credit_balance ?? 0 }}</b>
            <span>积分余额</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 本人 Tabs -->
    <div v-if="isSelf" class="cx-card tabs-card">
      <el-tabs v-model="tab">
        <el-tab-pane label="我的帖子" name="posts" />
        <el-tab-pane label="我的收藏" name="favorites" />
        <el-tab-pane label="积分明细" name="credits" />
      </el-tabs>

      <!-- 我的帖子 -->
      <template v-if="tab === 'posts'">
        <el-radio-group v-model="statusFilter" size="small" class="filter">
          <el-radio-button :value="null">全部</el-radio-button>
          <el-radio-button :value="0">待解决</el-radio-button>
          <el-radio-button :value="1">已解决</el-radio-button>
        </el-radio-group>
        <div v-loading="listLoading" class="list">
          <PostCardItem v-for="p in items" :key="p.id" :post="p" />
          <el-empty v-if="!listLoading && !items.length" description="还没有发布过提问" />
        </div>
      </template>

      <!-- 收藏 -->
      <template v-else-if="tab === 'favorites'">
        <el-radio-group v-model="favType" size="small" class="filter">
          <el-radio-button :value="1">帖子</el-radio-button>
          <el-radio-button :value="2">回答</el-radio-button>
        </el-radio-group>
        <div v-loading="listLoading" class="list">
          <template v-if="favType === 1">
            <PostCardItem v-for="p in items" :key="p.id" :post="p" />
          </template>
          <template v-else>
            <div
              v-for="f in favAnswerItems"
              :key="f.answer_id"
              class="cx-card fav-answer"
              @click="router.push(`/posts/${f.post_id}`)"
            >
              <div class="fav-title">{{ f.post_title }}</div>
              <p class="fav-content">{{ f.content }}</p>
              <span class="fav-meta">{{ f.author_nickname }} · {{ fmtTime(f.created_at) }}</span>
            </div>
          </template>
          <el-empty v-if="!listLoading && ((favType === 1 && !items.length) || (favType === 2 && !favAnswerItems.length))" description="还没有收藏内容" />
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
            <div class="right">
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

    <!-- 他人视角提示 -->
    <div v-else class="cx-card other-tip">
      <p>TA 的公开内容可在广场与搜索中查看</p>
    </div>

    <!-- 资料编辑 -->
    <el-dialog v-model="editVisible" title="编辑资料" width="420px">
      <el-form label-position="top">
        <el-form-item label="昵称（1-20 字）" required>
          <el-input v-model="editForm.nickname" maxlength="20" show-word-limit />
        </el-form-item>
        <el-form-item label="学校">
          <el-input v-model="editForm.school" maxlength="50" />
        </el-form-item>
        <el-form-item label="专业">
          <el-input v-model="editForm.major" maxlength="50" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.head-card {
  padding: 24px;
  margin-bottom: 16px;
}

.head {
  display: flex;
  gap: 20px;
  align-items: center;
  flex-wrap: wrap;
}

.avatar-wrap {
  position: relative;
}

.avatar-edit {
  position: absolute;
  right: -4px;
  bottom: -4px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 13px;
}

.info {
  flex: 1;
  min-width: 200px;
}

.name-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.name-row h2 {
  margin: 0;
  font-size: 22px;
}

.sub {
  display: flex;
  gap: 12px;
  color: #777;
  font-size: 14px;
  margin: 8px 0 0;
  flex-wrap: wrap;
}

.muted {
  color: #aaa;
}

.stats {
  display: flex;
  gap: 24px;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat b {
  font-size: 20px;
}

.stat span {
  color: #999;
  font-size: 12px;
  margin-top: 4px;
}

.stat.credit b {
  color: var(--el-color-warning);
}

.tabs-card {
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

.fav-answer {
  cursor: pointer;
  padding: 14px 16px;
}

.fav-title {
  font-weight: 600;
  font-size: 15px;
}

.fav-content {
  color: #666;
  margin: 6px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.fav-meta {
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

.right {
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

.other-tip {
  padding: 40px;
  text-align: center;
  color: #999;
}

.pager {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
