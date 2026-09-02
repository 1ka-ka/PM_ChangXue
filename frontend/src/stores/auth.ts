/**
 * 登录态 store：token + 当前用户信息 + 未读计数（顶栏角标共享）。
 */
import { defineStore } from 'pinia'
import { get, post, TOKEN_KEY } from '@/api/http'

export interface CurrentUser {
  id: number
  phone: string
  nickname: string
  avatar: string | null
  bio: string | null
  credit_balance: number
  is_admin: boolean
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY),
    user: null as CurrentUser | null,
    unreadCount: 0,
  }),
  getters: {
    isLogged: (s) => !!s.token,
  },
  actions: {
    setToken(token: string) {
      this.token = token
      localStorage.setItem(TOKEN_KEY, token)
    },
    async fetchMe() {
      if (!this.token) return
      try {
        this.user = await get<CurrentUser>('/auth/me')
      } catch {
        this.user = null
      }
    },
    async fetchUnread() {
      if (!this.token) return
      try {
        const r = await get<{ count: number }>('/notifications/unread-count')
        this.unreadCount = r.count
      } catch {
        // 静默：角标失败不影响主界面
      }
    },
    async login(phone: string, password: string) {
      const r = await post<{ token: string }>('/auth/login', { phone, password })
      this.setToken(r.token)
      await this.fetchMe()
    },
    async register(phone: string, password: string, nickname: string) {
      const r = await post<{ token: string }>('/auth/register', {
        phone,
        password,
        nickname,
      })
      this.setToken(r.token)
      await this.fetchMe()
    },
    logout() {
      this.token = null
      this.user = null
      this.unreadCount = 0
      localStorage.removeItem(TOKEN_KEY)
    },
  },
})
