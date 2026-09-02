<script setup lang="ts">
/**
 * 举报对话框（M7-F28）：理由五选一 + 补充说明；40903 重复举报由拦截器提示。
 * 用法：const r = ref<InstanceType<typeof ReportDialog>>(); r.value.open(1, postId)
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { post } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useRouter, useRoute } from 'vue-router'

const REASONS = [
  { value: 1, label: '垃圾广告' },
  { value: 2, label: '人身攻击' },
  { value: 3, label: '色情低俗' },
  { value: 4, label: '违法违规' },
  { value: 5, label: '其他' },
]

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const visible = ref(false)
const targetType = ref(1)
const targetId = ref(0)
const reason = ref<number | null>(null)
const detail = ref('')
const submitting = ref(false)

function open(t: 1 | 2 | 3, id: number) {
  if (!auth.isLogged) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  targetType.value = t
  targetId.value = id
  reason.value = null
  detail.value = ''
  visible.value = true
}

async function submit() {
  if (!reason.value) {
    ElMessage.warning('请选择举报理由')
    return
  }
  submitting.value = true
  try {
    await post('/reports', {
      target_type: targetType.value,
      target_id: targetId.value,
      reason: reason.value,
      detail: detail.value.trim(),
    })
    ElMessage.success('举报已提交，管理员会尽快处理')
    visible.value = false
  } catch {
    // 拦截器已提示（40903 重复举报等）
  } finally {
    submitting.value = false
  }
}

defineExpose({ open })
</script>

<template>
  <el-dialog v-model="visible" title="举报" width="420px">
    <el-form label-position="top">
      <el-form-item label="举报理由" required>
        <el-radio-group v-model="reason">
          <el-radio v-for="r in REASONS" :key="r.value" :value="r.value">{{ r.label }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="补充说明（可选）">
        <el-input v-model="detail" type="textarea" :rows="2" maxlength="200" show-word-limit />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="danger" :loading="submitting" @click="submit">提交举报</el-button>
    </template>
  </el-dialog>
</template>
