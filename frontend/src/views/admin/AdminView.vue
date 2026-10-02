<script setup lang="ts">
/**
 * 管理后台（接口 31-38）：看板 / 举报队列（处置四动作）/ 标签管理 / 操作日志。
 * 仅 admin 路由守卫可达（router meta.admin）。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { get, post, put } from '@/api/http'
import type { Page } from '@/api/types'

type Brief = { id: number; nickname: string; avatar: string | null }

interface ReportItem {
  id: number
  reporter: Brief | null
  target_type: 1 | 2 | 3
  target_id: number
  content: { kind: string; deleted: boolean; title?: string; excerpt?: string; post_id?: number }
  author: Brief | null
  reason: number
  detail: string | null
  status: 0 | 1 | 2
  ai_level?: string | null // AI 违规分级 极高/高/低（V1.3，异步生成）
  ai_violation_type?: string | null
  report_count: number
  created_at: string
}

interface TagRow {
  id: number
  name: string
  sort: number
  enabled: boolean
}

interface LogItem {
  id: number
  admin_id: number
  admin_nickname: string | null
  action: number
  target_type: number | null
  target_id: number | null
  reason: string
  created_at: string
}

const REASON_TEXT: Record<number, string> = { 1: '垃圾广告', 2: '人身攻击', 3: '色情低俗', 4: '违法违规', 5: '其他' }
const TARGET_TEXT: Record<number, string> = { 1: '帖子', 2: '回答', 3: '评论' }
const STATUS_TEXT: Record<number, { label: string; type: 'warning' | 'success' | 'info' }> = {
  0: { label: '待处理', type: 'warning' },
  1: { label: '已处置', type: 'success' },
  2: { label: '驳回', type: 'info' },
}
const ACTION_TEXT: Record<number, string> = {
  1: '删帖', 2: '删回答', 3: '删评论', 4: '封号', 5: '解封', 6: '追回积分', 7: '驳回举报', 8: '恢复',
}

const tab = ref('stats')

// ---- 看板 ----
const stats = ref<{ pending_reports: number; dau: number; daily_posts: number; daily_accepts: number } | null>(null)

// ---- 举报队列 ----
const statusFilter = ref<number | null>(null)
const reports = ref<ReportItem[]>([])
const reportsLoading = ref(false)

// 处置对话框
const actDialog = reactive({
  visible: false,
  report: null as ReportItem | null,
  action: 'delete' as 'delete' | 'ban' | 'recall_credit' | 'dismiss',
  reason: '',
  banDays: 1,
  amount: 10,
  submitting: false,
})

// ---- 标签管理 ----
const tags = ref<TagRow[]>([])
const tagsLoading = ref(false)
const tagDialog = reactive({
  visible: false,
  isEdit: false,
  id: 0,
  name: '',
  sort: 0,
})

// ---- 操作日志 ----
const logs = ref<LogItem[]>([])
const logsLoading = ref(false)

// ---- 系统运营（V1.13）----
interface OpAccount {
  id: number
  nickname: string
  school: string
  major: string
  focus: string
  balance: number
  post_count: number
  answer_count: number
}

interface OpLog {
  id: number
  action: number
  action_text: string
  ok: boolean
  detail: string
  nickname: string | null
  created_at: string
}

interface OpStatus {
  enabled: boolean
  llm_ready: boolean
  schedule: { tick_minutes: number; hours: string; probability: number }
  quota: { questions: number; interactions: number }
  today: { questions: number; interactions: number }
  accounts: OpAccount[]
  recent: OpLog[]
}

const opStatus = ref<OpStatus | null>(null)
const opLoading = ref(false)
const opRunning = ref(false)
const opLastRun = ref<{ action_text?: string; ok: boolean; detail: string }[] | null>(null)

async function loadOperation() {
  opLoading.value = true
  try {
    opStatus.value = await get<OpStatus>('/admin/operation/status')
  } finally {
    opLoading.value = false
  }
}

async function runOperation() {
  opRunning.value = true
  opLastRun.value = null
  try {
    const r = await post<{ executed: { action: number; ok: boolean; detail: string }[] }>('/admin/operation/run')
    const textMap: Record<number, string> = { 1: '提问', 2: '回答', 3: '评论', 4: '回复', 5: '采纳', 6: '点赞' }
    opLastRun.value = r.executed.map((e) => ({
      action_text: e.action ? textMap[e.action] || `动作${e.action}` : '未执行',
      ok: e.ok,
      detail: e.detail,
    }))
    ElMessage.success(`本轮执行 ${r.executed.length} 个动作`)
    await loadOperation()
  } catch {
    // 拦截器已提示
  } finally {
    opRunning.value = false
  }
}

function fmtTime(s: string) {
  return (s || '').slice(0, 16).replace('T', ' ')
}

async function loadStats() {
  stats.value = await get('/admin/stats')
}

async function loadReports() {
  reportsLoading.value = true
  try {
    const r = await get<Page<ReportItem>>('/admin/reports', {
      ...(statusFilter.value !== null ? { status: statusFilter.value } : {}),
      page: 1,
      page_size: 50,
    })
    reports.value = r.items
  } finally {
    reportsLoading.value = false
  }
}

async function loadTags() {
  tagsLoading.value = true
  try {
    tags.value = await get<TagRow[]>('/admin/tags')
  } finally {
    tagsLoading.value = false
  }
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const r = await get<Page<LogItem>>('/admin/logs', { page: 1, page_size: 50 })
    logs.value = r.items
  } finally {
    logsLoading.value = false
  }
}

function openAct(r: ReportItem) {
  actDialog.report = r
  actDialog.action = 'delete'
  actDialog.reason = ''
  actDialog.banDays = 1
  actDialog.amount = 10
  actDialog.visible = true
}

async function submitAct() {
  if (!actDialog.report) return
  if (!actDialog.reason.trim()) {
    ElMessage.warning('请填写处置理由')
    return
  }
  actDialog.submitting = true
  try {
    await post(`/admin/reports/${actDialog.report.id}/action`, {
      action: actDialog.action,
      reason: actDialog.reason.trim(),
      ...(actDialog.action === 'ban' ? { ban_days: actDialog.banDays } : {}),
      ...(actDialog.action === 'recall_credit' ? { amount: actDialog.amount } : {}),
    })
    ElMessage.success('处置完成')
    actDialog.visible = false
    await Promise.all([loadReports(), loadStats()])
  } catch {
    // 拦截器已提示（40911 已处理等）
  } finally {
    actDialog.submitting = false
  }
}

function openTagCreate() {
  tagDialog.isEdit = false
  tagDialog.id = 0
  tagDialog.name = ''
  tagDialog.sort = (tags.value.at(-1)?.sort ?? 0) + 1
  tagDialog.visible = true
}

function openTagEdit(t: TagRow) {
  tagDialog.isEdit = true
  tagDialog.id = t.id
  tagDialog.name = t.name
  tagDialog.sort = t.sort
  tagDialog.visible = true
}

async function submitTag() {
  const name = tagDialog.name.trim()
  if (!name) {
    ElMessage.warning('请填写标签名')
    return
  }
  try {
    if (tagDialog.isEdit) {
      await put(`/admin/tags/${tagDialog.id}`, { name, sort: tagDialog.sort })
    } else {
      await post('/admin/tags', { name, sort: tagDialog.sort })
    }
    ElMessage.success('已保存')
    tagDialog.visible = false
    await loadTags()
  } catch {
    // 拦截器已提示（重名 40001 等）
  }
}

async function toggleTag(t: TagRow) {
  try {
    await put(`/admin/tags/${t.id}`, { enabled: t.enabled ? 0 : 1 })
    await loadTags()
  } catch {
    // 拦截器已提示
  }
}

function onTab(name: string) {
  if (name === 'stats') loadStats()
  else if (name === 'reports') loadReports()
  else if (name === 'tags') loadTags()
  else if (name === 'operation') loadOperation()
  else loadLogs()
}

onMounted(() => {
  loadStats()
  loadReports()
})
</script>

<template>
  <div class="admin">
    <el-tabs v-model="tab" @tab-change="onTab">
      <!-- 数据看板 -->
      <el-tab-pane label="数据看板" name="stats">
        <div class="stat-grid">
          <div class="cx-card stat">
            <span class="num">{{ stats?.pending_reports ?? '-' }}</span>
            <span class="label">待处理举报</span>
          </div>
          <div class="cx-card stat">
            <span class="num">{{ stats?.dau ?? '-' }}</span>
            <span class="label">今日活跃用户</span>
          </div>
          <div class="cx-card stat">
            <span class="num">{{ stats?.daily_posts ?? '-' }}</span>
            <span class="label">今日新帖</span>
          </div>
          <div class="cx-card stat">
            <span class="num">{{ stats?.daily_accepts ?? '-' }}</span>
            <span class="label">今日采纳</span>
          </div>
        </div>
      </el-tab-pane>

      <!-- 举报队列 -->
      <el-tab-pane label="举报队列" name="reports">
        <div class="toolbar">
          <el-radio-group v-model="statusFilter" size="small" @change="loadReports">
            <el-radio-button :value="null">全部</el-radio-button>
            <el-radio-button :value="0">待处理</el-radio-button>
            <el-radio-button :value="1">已处置</el-radio-button>
            <el-radio-button :value="2">驳回</el-radio-button>
          </el-radio-group>
        </div>

        <div v-loading="reportsLoading" class="report-list">
          <div v-for="r in reports" :key="r.id" class="cx-card report">
            <div class="report-head">
              <el-tag size="small" effect="plain">{{ TARGET_TEXT[r.target_type] }} #{{ r.target_id }}</el-tag>
              <span class="reason">{{ REASON_TEXT[r.reason] || '其他' }}</span>
              <span v-if="r.detail" class="detail">"{{ r.detail }}"</span>
              <!-- AI 违规分级（V1.3）：辅助分诊，不代表最终认定 -->
              <el-tag
                v-if="r.ai_level"
                size="small"
                effect="dark"
                :type="r.ai_level === '极高' ? 'danger' : r.ai_level === '高' ? 'danger' : 'info'"
              >
                AI:{{ r.ai_level }}{{ r.ai_violation_type ? `·${r.ai_violation_type}` : '' }}
              </el-tag>
              <el-tag size="small" :type="STATUS_TEXT[r.status].type">
                {{ STATUS_TEXT[r.status].label }}
              </el-tag>
              <el-tag v-if="r.report_count > 1" size="small" type="danger" effect="plain">
                被举报 {{ r.report_count }} 次
              </el-tag>
              <span class="time">{{ fmtTime(r.created_at) }}</span>
            </div>

            <div class="report-body">
              <div class="content">
                <span v-if="r.content.deleted" class="deleted-tag">内容已删除</span>
                <b v-if="r.content.title">{{ r.content.title }}</b>
                <span class="excerpt">{{ r.content.excerpt || '（无内容快照）' }}</span>
              </div>
              <div class="people">
                <span>举报人：{{ r.reporter?.nickname || '已注销' }}</span>
                <span v-if="r.author">作者：{{ r.author.nickname }}</span>
              </div>
            </div>

            <div v-if="r.status === 0" class="report-ops">
              <el-button size="small" type="primary" @click="openAct(r)">处置</el-button>
            </div>
          </div>
          <el-empty v-if="!reportsLoading && !reports.length" description="暂无举报" />
        </div>
      </el-tab-pane>

      <!-- 标签管理 -->
      <el-tab-pane label="标签管理" name="tags">
        <div class="toolbar">
          <el-button type="primary" size="small" @click="openTagCreate">新增标签</el-button>
        </div>
        <el-table v-loading="tagsLoading" :data="tags" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="sort" label="排序" width="90" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                {{ row.enabled ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="openTagEdit(row)">编辑</el-button>
              <el-button size="small" text :type="row.enabled ? 'danger' : 'success'" @click="toggleTag(row)">
                {{ row.enabled ? '停用' : '启用' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 系统运营（V1.13） -->
      <el-tab-pane label="系统运营" name="operation">
        <div v-loading="opLoading" class="op-panel">
          <div class="toolbar">
            <div class="op-meta">
              <el-tag :type="opStatus?.enabled ? 'success' : 'info'" size="small">自动调度{{ opStatus?.enabled ? '已开启' : '已关闭' }}</el-tag>
              <el-tag :type="opStatus?.llm_ready ? 'success' : 'danger'" size="small">
                LLM{{ opStatus?.llm_ready ? '在线' : '不可用（仅执行采纳/点赞）' }}
              </el-tag>
              <span v-if="opStatus" class="op-hint">
                每 {{ opStatus.schedule.tick_minutes }} 分钟一轮（{{ opStatus.schedule.hours }}，{{ Math.round(opStatus.schedule.probability * 100) }}% 概率执行）
              </span>
            </div>
            <div>
              <el-button size="small" @click="loadOperation">刷新</el-button>
              <el-button type="primary" size="small" :loading="opRunning" @click="runOperation">
                立即执行一轮（1-3 个动作）
              </el-button>
            </div>
          </div>

          <!-- 当日进度 -->
          <div class="stat-grid op-progress">
            <div class="cx-card stat">
              <span class="num">{{ opStatus?.today.questions ?? '-' }}/{{ opStatus?.quota.questions ?? '-' }}</span>
              <span class="label">今日新提问</span>
              <el-progress
                v-if="opStatus"
                :percentage="Math.min(100, Math.round((opStatus.today.questions / opStatus.quota.questions) * 100))"
                :stroke-width="6"
                :show-text="false"
              />
            </div>
            <div class="cx-card stat">
              <span class="num">{{ opStatus?.today.interactions ?? '-' }}/{{ opStatus?.quota.interactions ?? '-' }}</span>
              <span class="label">今日互动（答/评/采纳/赞）</span>
              <el-progress
                v-if="opStatus"
                :percentage="Math.min(100, Math.round((opStatus.today.interactions / opStatus.quota.interactions) * 100))"
                :stroke-width="6"
                :show-text="false"
              />
            </div>
          </div>

          <!-- 上一轮结果 -->
          <div v-if="opLastRun" class="cx-card op-lastrun">
            <b>上一轮执行结果：</b>
            <span v-for="(item, i) in opLastRun" :key="i" class="lastrun-item">
              <el-tag size="small" :type="item.ok ? 'success' : 'info'">{{ item.action_text }}</el-tag>
              <span class="detail">{{ item.detail }}</span>
            </span>
          </div>

          <!-- 运营账号池 -->
          <el-table :data="opStatus?.accounts ?? []" size="small">
            <el-table-column prop="nickname" label="账号" width="140" />
            <el-table-column prop="school" label="学校" width="150" />
            <el-table-column prop="focus" label="人设方向" />
            <el-table-column prop="balance" label="积分" width="90" />
            <el-table-column prop="post_count" label="提问" width="80" />
            <el-table-column prop="answer_count" label="回答" width="80" />
          </el-table>

          <!-- 最近动作日志 -->
          <h4 class="op-section-title">最近动作</h4>
          <el-table :data="opStatus?.recent ?? []" size="small">
            <el-table-column label="时间" width="150">
              <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="账号" width="140">
              <template #default="{ row }">{{ row.nickname || '-' }}</template>
            </el-table-column>
            <el-table-column label="动作" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.ok ? 'success' : 'info'" effect="plain">{{ row.action_text }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="详情" show-overflow-tooltip />
          </el-table>
          <el-empty v-if="!opLoading && !opStatus?.recent?.length" description="暂无运营动作（等待调度或点击上方按钮触发）" />
        </div>
      </el-tab-pane>

      <!-- 操作日志 -->
      <el-tab-pane label="操作日志" name="logs">
        <el-table v-loading="logsLoading" :data="logs" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column label="动作" width="110">
            <template #default="{ row }">
              <el-tag :type="row.action === 7 ? 'info' : 'danger'" size="small" effect="plain">
                {{ ACTION_TEXT[row.action] || `动作${row.action}` }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="目标" width="130">
            <template #default="{ row }">
              {{ row.target_type ? `${TARGET_TEXT[row.target_type]} #${row.target_id}` : '用户' }}
            </template>
          </el-table-column>
          <el-table-column prop="admin_nickname" label="操作人" width="110" />
          <el-table-column prop="reason" label="理由" show-overflow-tooltip />
          <el-table-column label="时间" width="150">
            <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!logsLoading && !logs.length" description="暂无操作记录" />
      </el-tab-pane>
    </el-tabs>

    <!-- 处置对话框 -->
    <el-dialog v-model="actDialog.visible" title="处置举报" width="440px">
      <template v-if="actDialog.report">
        <p class="act-target">
          {{ TARGET_TEXT[actDialog.report.target_type] }} #{{ actDialog.report.target_id }}
          <template v-if="actDialog.report.content.title">（{{ actDialog.report.content.title }}）</template>
        </p>
        <el-form label-position="top">
          <el-form-item label="处置动作" required>
            <el-radio-group v-model="actDialog.action">
              <el-radio value="delete">删除内容</el-radio>
              <el-radio value="ban">封禁作者</el-radio>
              <el-radio value="recall_credit">追回积分</el-radio>
              <el-radio value="dismiss">驳回</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="actDialog.action === 'ban'" label="封禁时长" required>
            <el-radio-group v-model="actDialog.banDays">
              <el-radio :value="1">1 天</el-radio>
              <el-radio :value="7">7 天</el-radio>
              <el-radio :value="0">永久</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="actDialog.action === 'recall_credit'" label="追回积分（钳制至余额 0）" required>
            <el-input-number v-model="actDialog.amount" :min="1" :max="10000" />
          </el-form-item>
          <el-form-item label="处置理由（必填，写入操作日志）" required>
            <el-input v-model="actDialog.reason" type="textarea" :rows="2" maxlength="200" show-word-limit />
          </el-form-item>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="actDialog.visible = false">取消</el-button>
        <el-button
          type="danger"
          :loading="actDialog.submitting"
          :disabled="actDialog.action === 'dismiss'"
          @click="submitAct"
        >
          执行处置
        </el-button>
        <el-button
          v-if="actDialog.action === 'dismiss'"
          type="info"
          :loading="actDialog.submitting"
          @click="submitAct"
        >
          驳回举报
        </el-button>
      </template>
    </el-dialog>

    <!-- 标签对话框 -->
    <el-dialog v-model="tagDialog.visible" :title="tagDialog.isEdit ? '编辑标签' : '新增标签'" width="380px">
      <el-form label-position="top">
        <el-form-item label="标签名（≤20 字）" required>
          <el-input v-model="tagDialog.name" maxlength="20" show-word-limit />
        </el-form-item>
        <el-form-item label="排序值（小的在前）">
          <el-input-number v-model="tagDialog.sort" :min="0" :max="999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tagDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="submitTag">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin {
  padding: 0 4px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 22px 0;
}

.stat .num {
  font-size: 28px;
  font-weight: 600;
  color: var(--el-color-primary);
}

.stat .label {
  margin-top: 6px;
  color: #999;
  font-size: 13px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}

.report {
  margin-bottom: 10px;
}

.report-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
}

.reason {
  font-weight: 600;
  color: var(--el-color-danger);
}

.detail {
  color: #999;
}

.time {
  margin-left: auto;
  color: #bbb;
  font-size: 12px;
}

.report-body {
  margin-top: 8px;
}

.content {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.content b {
  font-size: 14px;
}

.excerpt {
  color: #666;
  font-size: 13px;
}

.deleted-tag {
  color: #ccc;
  font-size: 12px;
}

.people {
  display: flex;
  gap: 16px;
  margin-top: 6px;
  color: #999;
  font-size: 12px;
}

.report-ops {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

.act-target {
  margin: 0 0 10px;
  color: #666;
  font-size: 13px;
}

/* 系统运营面板 */
.op-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.op-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.op-hint {
  color: #999;
  font-size: 12px;
}

.op-progress :deep(.el-progress) {
  width: 70%;
  margin-top: 8px;
}

.op-lastrun {
  padding: 12px 16px;
  font-size: 13px;
}

.lastrun-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-right: 16px;
}

.lastrun-item .detail {
  color: #666;
}

.op-section-title {
  margin: 4px 0 0;
  color: #666;
}
</style>
