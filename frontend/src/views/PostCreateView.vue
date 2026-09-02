<script setup lang="ts">
/**
 * S11c 发帖页（功能需求详述 M3-F07）：
 * 标题/正文/配图上传（≤9）/标签选择（1-3）/悬赏档位/AI 摘要占位/草稿本地缓存。
 * 悬赏不足 40902 → 弹窗"调整悬赏 / 普通发布"（详述 §M3-F07 异常场景）。
 */
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile, UploadRequestOptions } from 'element-plus'
import { ApiError, get, http, post } from '@/api/http'
import type { PostCard, TagItem } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

type SimilarItem = PostCard & { similar_score: number }

const DRAFT_KEY = 'cx_post_draft'
const REWARD_TIERS = [0, 10, 20, 50, 100]

const router = useRouter()
const auth = useAuthStore()

const tags = ref<TagItem[]>([])
const images = ref<string[]>([])
const fileList = ref<UploadFile[]>([]) // el-upload 展示列表（与 images 同步）
const uploading = ref(0) // 上传中数量（发布按钮禁用依据）
const submitting = ref(false)
const restored = ref(false)

function syncFileList() {
  fileList.value = images.value.map((url) => ({ name: url, url, status: 'success' }) as UploadFile)
}

const form = reactive({
  title: '',
  content: '',
  tag_ids: [] as number[],
  reward: 0,
})

onMounted(async () => {
  // 草稿恢复（标题/正文/标签/悬赏/已传图片 URL）
  try {
    const draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null')
    if (draft && (draft.title || draft.content || draft.tag_ids?.length || draft.images?.length)) {
      Object.assign(form, {
        title: draft.title || '',
        content: draft.content || '',
        tag_ids: draft.tag_ids || [],
        reward: REWARD_TIERS.includes(draft.reward) ? draft.reward : 0,
      })
      images.value = draft.images || []
      syncFileList()
      restored.value = true
    }
  } catch {
    // 草稿损坏则忽略
  }
  // 标签选项
  try {
    const r = await get<{ items: TagItem[] }>('/tags')
    tags.value = r.items
  } catch {
    ElMessage.error('标签加载失败，请刷新重试')
  }
})

// 草稿自动缓存：任何编辑都落 localStorage，异常退出不丢失
watch(
  [() => form.title, () => form.content, () => form.tag_ids, () => form.reward, images],
  () => {
    if (restored.value) restored.value = false
    localStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({ ...form, images: images.value }),
    )
  },
  { deep: true },
)

// 配图上传：手动请求 /uploads/image，成功收集 URL（失败不阻塞其他图片）
async function uploadImage(opt: UploadRequestOptions) {
  const fd = new FormData()
  fd.append('file', opt.file)
  uploading.value++
  try {
    const r = (await http.post('/uploads/image', fd)) as { url: string }
    images.value.push(r.url)
    opt.onSuccess(r as never)
  } catch (e) {
    opt.onError(e as never)
    ElMessage.error('图片上传失败，可重新选择该图片')
  } finally {
    uploading.value--
  }
}

function removeImage(file: UploadFile) {
  const url = file.url ?? (file.response as { url: string } | undefined)?.url ?? ''
  const idx = images.value.indexOf(url)
  if (idx >= 0) {
    images.value.splice(idx, 1)
    syncFileList()
  }
}

function validate(): string | null {
  if (!form.title.trim()) return '请填写标题'
  if (form.title.length > 50) return '标题不能超过 50 字'
  if (!form.tag_ids.length) return '请选择 1-3 个标签'
  if (form.tag_ids.length > 3) return '标签最多 3 个'
  if (!form.content.trim() && !images.value.length) return '正文与图片至少填写一项'
  return null
}

async function submit() {
  const err = validate()
  if (err) {
    ElMessage.warning(err)
    return
  }
  if (uploading.value > 0) {
    ElMessage.warning('图片上传中，请稍候')
    return
  }
  submitting.value = true
  try {
    await doSubmit(form.reward)
  } finally {
    submitting.value = false
  }
}

async function doSubmit(reward: number) {
  try {
    const r = await post<{ id: number }>('/posts', {
      title: form.title.trim(),
      content: form.content.trim(),
      images: images.value,
      tag_ids: form.tag_ids,
      reward,
    })
    localStorage.removeItem(DRAFT_KEY) // 发布成功清草稿
    ElMessage.success('发布成功')
    router.replace(`/posts/${r.id}`)
  } catch (e) {
    if (e instanceof ApiError && e.code === 40902) {
      // 积分不足：调整悬赏 / 普通发布（详述 M3-F07）
      try {
        await ElMessageBox.confirm(`${e.message}。可调整悬赏档位，或改为发布普通帖。`, '积分不足', {
          confirmButtonText: '普通发布',
          cancelButtonText: '调整悬赏',
          type: 'warning',
        })
        form.reward = 0
        await doSubmit(0)
      } catch {
        // 用户选择回去调整悬赏
      }
      return
    }
    if (e instanceof ApiError) ElMessage.error(e.message)
  }
}

// 悬赏不可用判断：余额不足的档位禁用（发布时后端仍强校验）
function tierDisabled(tier: number) {
  return tier > 0 && tier > (auth.user?.credit_balance ?? 0)
}

// ---- 相似问答推荐（V1.1 防重复提问）：标题防抖 600ms 实时提示 ----
const similarItems = ref<SimilarItem[]>([])
let similarTimer: ReturnType<typeof setTimeout> | null = null

watch([() => form.title, () => form.tag_ids], () => {
  if (similarTimer) clearTimeout(similarTimer)
  const q = form.title.trim()
  if (q.length < 2) {
    similarItems.value = []
    return
  }
  similarTimer = setTimeout(async () => {
    try {
      const params: Record<string, string> = { q }
      if (form.tag_ids.length) params.tag_ids = form.tag_ids.join(',')
      const r = await get<{ items: SimilarItem[] }>('/posts/similar', params)
      similarItems.value = r.items
    } catch {
      // 推荐失败静默（不阻塞发帖主流程）
    }
  }, 600)
})
</script>

<template>
  <div class="cx-card create">
    <h2 class="page-title">发布提问</h2>

    <el-alert
      v-if="restored"
      title="已恢复上次未发布的草稿"
      type="info"
      :closable="true"
      class="restored"
    />

    <el-form label-position="top" @submit.prevent="submit">
      <el-form-item label="标题" required>
        <el-input
          v-model="form.title"
          placeholder="一句话说清你的问题（1-50 字）"
          maxlength="50"
          show-word-limit
          size="large"
        />
        <!-- 相似问答提示：发布前先看看有没有人问过（V1.1 防重复提问） -->
        <div v-if="similarItems.length" class="similar-box">
          <div class="similar-head">
            <el-icon><Search /></el-icon>
            <span>已有相似问题，发布前不妨先看看：</span>
          </div>
          <div
            v-for="s in similarItems"
            :key="s.id"
            class="similar-item"
            @click="router.push(`/posts/${s.id}`)"
          >
            <el-tag size="small" :type="s.status === 1 ? 'success' : 'warning'" effect="plain">
              {{ s.status === 1 ? '已解决' : '待解决' }}
            </el-tag>
            <span class="s-title">{{ s.title }}</span>
            <span class="s-meta">{{ s.answer_count }} 回答</span>
          </div>
        </div>
      </el-form-item>

      <el-form-item label="正文">
        <el-input
          v-model="form.content"
          type="textarea"
          :rows="6"
          placeholder="补充背景、尝试过的方法…（可留空，但需至少上传一张图片）"
          maxlength="5000"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="图片（最多 9 张，支持 jpg/png/webp，单张 ≤ 5MB）">
        <el-upload
          v-model:file-list="fileList"
          list-type="picture-card"
          :http-request="uploadImage"
          :on-remove="removeImage"
          :limit="9"
          accept="image/jpeg,image/png,image/webp"
          multiple
        >
          <el-icon size="20"><Plus /></el-icon>
        </el-upload>
      </el-form-item>

      <el-form-item label="标签（1-3 个）" required>
        <el-select v-model="form.tag_ids" multiple placeholder="选择学科标签" style="width: 100%">
          <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
      </el-form-item>

      <el-form-item label="悬赏（发布时一次性扣除，用于推荐加权，不退回）">
        <div class="reward-row">
          <el-radio-group v-model="form.reward">
            <el-radio-button v-for="t in REWARD_TIERS" :key="t" :value="t" :disabled="tierDisabled(t)">
              {{ t === 0 ? '不悬赏' : t }}
            </el-radio-button>
          </el-radio-group>
          <span class="balance" v-if="auth.user">当前积分：{{ auth.user.credit_balance }}</span>
        </div>
      </el-form-item>

      <!-- AI 摘要（V1.2 已上线）：发布后自动异步生成 -->
      <div class="ai-placeholder">
        <el-icon><MagicStick /></el-icon>
        <span>发布后将自动生成 AI 摘要，展示在帖子详情页与列表卡片</span>
      </div>

      <div class="actions">
        <span class="draft-tip">内容已自动缓存为草稿，异常退出不丢失</span>
        <el-button
          type="primary"
          size="large"
          round
          :loading="submitting"
          :disabled="uploading > 0"
          @click="submit"
        >
          发布
        </el-button>
      </div>
    </el-form>
  </div>
</template>

<style scoped>
.create {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px;
}

.page-title {
  margin: 0 0 16px;
  font-size: 20px;
}

.restored {
  margin-bottom: 16px;
}

.reward-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.balance {
  color: #999;
  font-size: 13px;
}

.ai-placeholder {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 16px;
  border: 1px dashed var(--el-color-info-light-5);
  border-radius: 8px;
  color: #999;
  font-size: 13px;
  background: var(--el-fill-color-light);
}

.actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.draft-tip {
  color: #bbb;
  font-size: 12px;
}

.similar-box {
  width: 100%;
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px solid var(--el-color-primary-light-8);
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
}

.similar-head {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #666;
  font-size: 13px;
  margin-bottom: 6px;
}

.similar-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.similar-item:hover {
  background: var(--el-fill-color);
}

.s-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.s-meta {
  color: #999;
  font-size: 12px;
  flex-shrink: 0;
}
</style>
