/**
 * 私信 store（V1.7）：顶栏未读角标共享（拉取失败静默）。
 */
import { defineStore } from 'pinia'
import { get } from '@/api/http'
import { useAuthStore } from './auth'

export const useMessageStore = defineStore('message', {
  state: () => ({
    unreadCount: 0,
  }),
  actions: {
    async fetchUnread() {
      const auth = useAuthStore()
      if (!auth.token) return
      try {
        const r = await get<{ count: number }>('/messages/unread-count')
        this.unreadCount = r.count
      } catch {
        // 静默：角标失败不影响主界面
      }
    },
    reset() {
      this.unreadCount = 0
    },
  },
})
