<script setup lang="ts">
/**
 * V1.12 个人主页（/u/:id）：基本信息 + 统计（提问/回答/获赞/感谢值）+ 公开内容（TA 的提问/回答）。
 * V1.15 个性化装扮：头像框/头衔/特效/佩戴展示 + 本人「个性装扮」管理（背包佩戴/卸下）。
 * 本人个性化管理（收藏/评论/点赞/积分等）已移至个人中心 /me。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { get, put } from '@/api/http'
import type { MyAnswerItem, Page, PostCard } from '@/api/types'
import PostCardItem from '@/components/PostCardItem.vue'
import DecorAvatar from '@/components/DecorAvatar.vue'
import UserDecor from '@/components/UserDecor.vue'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore, type ThemeConfig } from '@/stores/theme'

interface Gratitude {
  week: number
  month: number
  total: number
}

interface EquipSlot {
  product_id: number
  name: string
  payload: string
}

type Equipped = Record<string, EquipSlot | undefined>

interface ProfileInfo {
  id: number
  nickname: string
  avatar: string | null
  school: string
  major: string
  gratitude: Gratitude
  is_self: boolean
  equipped?: Equipped | null
  phone?: string
  credit_balance?: number
  created_at?: string
  post_count?: number
  answer_count?: number
  like_received?: number
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const themeStore = useThemeStore()

const info = ref<ProfileInfo | null>(null)
const loading = ref(false)
const tab = ref('posts')
const page = ref(1)
const total = ref(0)
const posts = ref<PostCard[]>([])
const answers = ref<MyAnswerItem[]>([])
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
  listLoading.value = true
  try {
    if (tab.value === 'posts') {
      const r = await get<Page<PostCard>>(`/account/users/${route.params.id}/posts`, {
        page: page.value,
      })
      posts.value = r.items
      total.value = r.total
    } else {
      const r = await get<Page<MyAnswerItem>>(`/account/users/${route.params.id}/answers`, {
        page: page.value,
      })
      answers.value = r.items
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
  posts.value = []
  answers.value = []
  fetchList()
}

onMounted(() => {
  fetchInfo()
  fetchList()
})
watch(() => route.params.id, () => {
  fetchInfo()
  resetAndFetch()
})
watch(tab, resetAndFetch)
watch(page, fetchList)

function joinDays() {
  if (!info.value?.created_at) return ''
  const days = Math.max(1, Math.ceil((Date.now() - new Date(info.value.created_at).getTime()) / 86400000))
  return `加入 ${days} 天`
}

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

// ---- 主题装扮（V1.6）：本人设置背景色/背景图/主题色，保存后即时生效 ----

const themeVisible = ref(false)
const themeForm = ref<ThemeConfig>({})
const themeSaving = ref(false)

function openTheme() {
  themeForm.value = { ...(themeStore.theme || {}) }
  themeVisible.value = true
}

async function uploadBg(evt: Event) {
  const file = (evt.target as HTMLInputElement).files?.[0]
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  try {
    const { http } = await import('@/api/http')
    const r = (await http.post('/uploads/image', fd)) as { url: string }
    themeForm.value.bg_image = r.url
  } catch {
    // 拦截器已提示
  }
  (evt.target as HTMLInputElement).value = ''
}

async function saveTheme() {
  themeSaving.value = true
  try {
    await themeStore.save(themeForm.value)
    ElMessage.success('装扮已更新')
    themeVisible.value = false
  } catch {
    // 拦截器已提示
  } finally {
    themeSaving.value = false
  }
}

async function resetTheme() {
  themeSaving.value = true
  try {
    await themeStore.save({})
    themeForm.value = {}
    ElMessage.success('已恢复默认装扮')
  } catch {
    // 拦截器已提示
  } finally {
    themeSaving.value = false
  }
}

function fmtTime(s: string | null) {
  return s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : ''
}

// ---- V1.15 个性装扮：背包佩戴/卸下/搭配 ----

const SLOT_NAMES: Record<string, string> = {
  title: '头衔',
  badge: '徽章',
  frame: '头像框',
  bubble: '气泡',
  effect: '特效',
  font: '字体',
  skin: '皮肤',
  pet: '宠物',
}

interface ItemRow {
  id: number
  product_id: number
  name: string
  category: number
  payload: string
  slot: string | null
  created_at: string
  equipped: boolean
}

const decorVisible = ref(false)
const items = ref<ItemRow[]>([])
const itemsLoading = ref(false)

// 昵称特效 class（如 name-effect-glow）
const effectClass = computed(() => {
  const p = info.value?.equipped?.effect?.payload
  return p ? `name-effect-${p}` : ''
})

function openDecor() {
  decorVisible.value = true
  fetchItems()
}

async function fetchItems() {
  itemsLoading.value = true
  try {
    const r = await get<{ items: ItemRow[] }>('/account/items')
    items.value = r.items
  } catch {
    // 拦截器已提示
  } finally {
    itemsLoading.value = false
  }
}

/** 佩戴/卸下切换：equipped → 卸下（null）；未佩戴 → 佩戴 */
async function toggleEquip(row: ItemRow) {
  if (!row.slot) return
  try {
    await put('/account/equip', {
      equips: { [row.slot]: row.equipped ? null : row.product_id },
    })
    ElMessage.success(row.equipped ? '已卸下' : '已佩戴')
    await fetchItems()
    await fetchInfo()
    await auth.fetchMe()
  } catch {
    // 拦截器已提示
  }
}

// 背包按槽位分组（保持 SLOT_NAMES 顺序）
const itemsBySlot = computed(() => {
  const groups: { slot: string; label: string; rows: ItemRow[] }[] = []
  for (const [slot, label] of Object.entries(SLOT_NAMES)) {
    const rows = items.value.filter((i) => i.slot === slot)
    if (rows.length) groups.push({ slot, label, rows })
  }
  return groups
})

// 未上架槽位背包为空时的空态文案
const decorEmpty = computed(
  () => !itemsLoading.value && !items.value.length && '背包空空如也，去商城逛逛吧',
)
</script>

<template>
  <div v-loading="loading" class="profile">
    <!-- 用户信息头 -->
    <div class="cx-card head-card">
      <div class="head">
        <div class="avatar-wrap" :class="{ self: isSelf }">
          <DecorAvatar :size="72" :src="info?.avatar" :name="info?.nickname" :equipped="info?.equipped" />
          <label v-if="isSelf" class="avatar-edit" title="更换头像">
            <el-icon><Camera /></el-icon>
            <input type="file" accept="image/jpeg,image/png,image/webp" hidden @change="uploadAvatar" />
          </label>
        </div>
        <div class="info">
          <div class="name-row">
            <h2 :class="effectClass">{{ info?.nickname }}</h2>
            <UserDecor :equipped="info?.equipped" />
            <template v-if="isSelf">
              <el-button size="small" round @click="openEdit">编辑资料</el-button>
              <el-button size="small" round @click="openTheme">装扮</el-button>
              <el-button size="small" round type="primary" @click="openDecor">个性装扮</el-button>
            </template>
            <el-button
              v-else-if="auth.isLogged"
              size="small"
              round
              type="primary"
              @click="router.push(`/messages?to=${info?.id}&name=${encodeURIComponent(info?.nickname || '')}`)"
            >
              发私信
            </el-button>
          </div>
          <p class="sub">
            <span v-if="info?.school">{{ info.school }}</span>
            <span v-if="info?.major">{{ info.major }}</span>
            <span v-if="!info?.school && !info?.major" class="muted">这位同学还没有填写学校与专业</span>
            <span class="muted">{{ joinDays() }}</span>
            <span v-if="isSelf && info?.phone" class="muted">{{ info.phone }}</span>
          </p>
          <!-- V1.15 佩戴展示：头衔/徽章/头像框/气泡/特效 -->
          <div v-if="info?.equipped && Object.keys(info.equipped).length" class="equipped-chips">
            <template v-for="(slot, key) in SLOT_NAMES" :key="key">
              <span v-if="info.equipped?.[key]" class="chip" :title="info.equipped[key]!.name">
                <i v-if="key === 'badge'" class="chip-emoji">{{ info.equipped[key]!.payload }}</i>
                <i v-else-if="key === 'pet'" class="chip-emoji">{{ info.equipped[key]!.payload }}</i>
                <i v-else-if="key === 'title'" class="chip-title">{{ info.equipped[key]!.payload || info.equipped[key]!.name }}</i>
                <template v-else>{{ slot }}</template>
              </span>
            </template>
          </div>
        </div>
        <div class="stats">
          <div class="stat">
            <b>{{ info?.post_count ?? 0 }}</b>
            <span>提问</span>
          </div>
          <div class="stat">
            <b>{{ info?.answer_count ?? 0 }}</b>
            <span>回答</span>
          </div>
          <div class="stat">
            <b>{{ info?.like_received ?? 0 }}</b>
            <span>获赞</span>
          </div>
          <div class="stat">
            <b>{{ info?.gratitude?.total ?? 0 }}</b>
            <span>感谢值</span>
          </div>
          <div v-if="isSelf" class="stat credit">
            <b>{{ info?.credit_balance ?? 0 }}</b>
            <span>积分余额</span>
          </div>
        </div>
      </div>
      <!-- V1.17 宠物挂件：主页右下角，所有访问者可见 -->
      <div v-if="info?.equipped?.pet" class="pet-corner" :title="info.equipped.pet.name">
        <span class="pet-widget">{{ info.equipped.pet.payload }}</span>
      </div>
    </div>

    <!-- 公开内容（任何人可看）：TA 的提问 / 回答 -->
    <div class="cx-card tabs-card">
      <el-tabs v-model="tab">
        <el-tab-pane label="TA 的提问" name="posts" />
        <el-tab-pane label="TA 的回答" name="answers" />
      </el-tabs>

      <div v-loading="listLoading" class="list">
        <template v-if="tab === 'posts'">
          <PostCardItem v-for="p in posts" :key="p.id" :post="p" />
          <el-empty v-if="!listLoading && !posts.length" description="还没有发布过提问" />
        </template>
        <template v-else>
          <div
            v-for="a in answers"
            :key="a.id"
            class="cx-card fav-answer"
            @click="a.post_id && router.push(`/posts/${a.post_id}`)"
          >
            <div class="fav-title">
              {{ a.post_title || '原提问已删除' }}
              <el-tag v-if="a.is_best" type="success" effect="dark" size="small">最佳</el-tag>
              <el-tag v-else-if="a.is_accepted" type="success" effect="plain" size="small">已采纳</el-tag>
            </div>
            <p class="fav-content">{{ a.content }}</p>
            <span class="fav-meta">获赞 {{ a.like_count }} · {{ fmtTime(a.created_at) }}</span>
          </div>
          <el-empty v-if="!listLoading && !answers.length" description="还没有回答过问题" />
        </template>
      </div>

      <div v-if="total > 20" class="pager">
        <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="prev, pager, next" background />
      </div>
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

    <!-- 主题装扮（本人） -->
    <el-dialog v-model="themeVisible" title="主题装扮" width="440px">
      <el-form label-width="90px" label-position="left">
        <el-form-item label="主题色">
          <el-color-picker v-model="themeForm.theme_color" />
          <span class="theme-tip">作用于按钮、链接等元素</span>
        </el-form-item>
        <el-form-item label="背景颜色">
          <el-color-picker v-model="themeForm.bg_color" />
          <span class="theme-tip">设置背景图后作为底色</span>
        </el-form-item>
        <el-form-item label="背景图片">
          <div class="bg-row">
            <label class="bg-upload" title="上传背景图">
              <el-icon><Plus /></el-icon>
              <input type="file" accept="image/jpeg,image/png,image/webp" hidden @change="uploadBg" />
            </label>
            <img v-if="themeForm.bg_image" :src="themeForm.bg_image" class="bg-preview" alt="背景预览" />
            <el-button
              v-if="themeForm.bg_image"
              text
              type="danger"
              size="small"
              @click="themeForm.bg_image = ''"
            >
              移除
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="themeVisible = false">取消</el-button>
        <el-button :loading="themeSaving" @click="resetTheme">恢复默认</el-button>
        <el-button type="primary" :loading="themeSaving" @click="saveTheme">保存</el-button>
      </template>
    </el-dialog>

    <!-- V1.15 个性装扮（本人）：背包按槽位分区，佩戴/卸下即时生效 -->
    <el-dialog v-model="decorVisible" title="个性装扮" width="560px">
      <div v-loading="itemsLoading" class="decor-body">
        <template v-if="itemsBySlot.length">
          <div v-for="g in itemsBySlot" :key="g.slot" class="slot-group">
            <h4>{{ g.label }}</h4>
            <div class="item-grid">
              <div
                v-for="row in g.rows"
                :key="row.id"
                class="item-card"
                :class="{ on: row.equipped }"
              >
                <!-- payload 预览：头衔=文本 / 徽章=emoji / 头像框=DecorAvatar / 气泡·特效=样式示例 -->
                <div v-if="g.slot === 'title'" class="payload payload-title">
                  {{ row.payload || row.name }}
                </div>
                <div v-else-if="g.slot === 'badge'" class="payload payload-badge">{{ row.payload }}</div>
                <DecorAvatar
                  v-else-if="g.slot === 'frame'"
                  :size="44"
                  name="框"
                  :equipped="{ frame: { product_id: row.product_id, name: row.name, payload: row.payload } }"
                />
                <div v-else-if="g.slot === 'bubble'" class="payload payload-bubble" :class="`bubble-${row.payload}`">
                  消息预览
                </div>
                <div v-else-if="g.slot === 'font'" class="payload" :class="`user-font-${row.payload}`">
                  字体预览 Aa
                </div>
                <div v-else-if="g.slot === 'skin'" class="payload payload-skin" :class="`skin-${row.payload}`">
                  主题预览
                </div>
                <div v-else-if="g.slot === 'pet'" class="payload">
                  <span class="pet-widget">{{ row.payload }}</span>
                </div>
                <div v-else class="payload payload-effect" :class="`name-effect-${row.payload}`">昵称</div>
                <div class="item-name" :title="row.name">{{ row.name }}</div>
                <el-button
                  size="small"
                  :type="row.equipped ? 'info' : 'primary'"
                  plain
                  @click="toggleEquip(row)"
                >
                  {{ row.equipped ? '卸下' : '佩戴' }}
                </el-button>
              </div>
            </div>
          </div>
        </template>
        <el-empty v-else-if="decorEmpty" :description="decorEmpty" :image-size="70" />
      </div>
      <template #footer>
        <el-button @click="decorVisible = false">完成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.head-card {
  position: relative;
  padding: 24px;
  margin-bottom: 16px;
}

/* V1.17 宠物挂件：主页信息卡右下角 */
.pet-corner {
  position: absolute;
  right: 20px;
  bottom: 8px;
  pointer-events: none;
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

/* 主题装扮对话框 */
.theme-tip {
  margin-left: 12px;
  color: #999;
  font-size: 12px;
}

.bg-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bg-upload {
  width: 64px;
  height: 40px;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #999;
}

.bg-upload:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.bg-preview {
  width: 96px;
  height: 40px;
  object-fit: cover;
  border-radius: 6px;
}

.pager {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

/* V1.15 佩戴展示 chips */
.equipped-chips {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.equipped-chips .chip {
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  border-radius: 4px;
  background: #f4f0ff;
  border: 1px solid #e3daff;
  color: #8e6df0;
  font-size: 12px;
  line-height: 20px;
  font-style: normal;
}

.equipped-chips .chip-emoji {
  font-size: 14px;
  font-style: normal;
}

.equipped-chips .chip-title {
  font-weight: 600;
  font-style: normal;
}

/* V1.15 个性装扮对话框 */
.decor-body {
  min-height: 120px;
  max-height: 60vh;
  overflow-y: auto;
}

.slot-group h4 {
  margin: 0 0 10px;
  font-size: 14px;
  color: #333;
}

.slot-group + .slot-group {
  margin-top: 18px;
}

.item-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}

.item-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.item-card.on {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-7);
}

.item-card .payload {
  min-height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.payload-title {
  padding: 2px 8px;
  border-radius: 4px;
  background: linear-gradient(135deg, #8e6df0, #b8a5ff);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.payload-badge {
  font-size: 26px;
}

.payload-bubble {
  padding: 4px 10px;
  border-radius: 10px;
  font-size: 12px;
  color: #333;
}

.payload-effect {
  font-size: 16px;
  font-weight: 700;
  color: #333;
}

/* V1.16 皮肤预览：皮肤 class 提供主题变量，色块直观展示 */
.payload-skin {
  padding: 4px 12px;
  border-radius: 10px;
  background: var(--cx-theme-bg);
  color: var(--cx-theme-primary);
  font-size: 12px;
  font-weight: 600;
  border: 1px solid var(--cx-theme-primary);
}

.item-name {
  font-size: 12px;
  color: #666;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
