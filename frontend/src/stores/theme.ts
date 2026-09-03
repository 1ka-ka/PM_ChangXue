/**
 * 主题装扮 store（V1.6）：登录后拉取本人 theme_config，注入 :root CSS 变量全局生效；
 * 退出登录恢复默认。装扮拉取/应用失败静默，不影响主界面。
 */
import { defineStore } from 'pinia'
import { get, put } from '@/api/http'
import { useAuthStore } from './auth'

export interface ThemeConfig {
  bg_color?: string | null
  bg_image?: string | null
  theme_color?: string | null
}

export const useThemeStore = defineStore('theme', {
  state: () => ({
    theme: null as ThemeConfig | null,
  }),
  actions: {
    /** 将配置写入 :root CSS 变量；null/空恢复默认 */
    apply(theme: ThemeConfig | null) {
      this.theme = theme && Object.keys(theme).length ? theme : null
      const root = document.documentElement.style
      if (this.theme?.bg_color) root.setProperty('--cx-theme-bg', this.theme.bg_color)
      else root.removeProperty('--cx-theme-bg')
      if (this.theme?.bg_image) root.setProperty('--cx-theme-bg-image', `url("${this.theme.bg_image}")`)
      else root.removeProperty('--cx-theme-bg-image')
      if (this.theme?.theme_color) root.setProperty('--cx-theme-primary', this.theme.theme_color)
      else root.removeProperty('--cx-theme-primary')
    },
    /** 登录后拉取本人装扮并应用 */
    async fetchAndApply() {
      const auth = useAuthStore()
      if (!auth.token) return
      try {
        const r = await get<{ theme: ThemeConfig | null }>('/account/theme')
        this.apply(r.theme)
      } catch {
        // 静默：装扮失败不影响主界面
      }
    },
    /** 保存本人装扮（整替语义，空项清除）并即时生效 */
    async save(theme: ThemeConfig) {
      const r = await put<{ theme: ThemeConfig }>('/account/theme', {
        bg_color: theme.bg_color || '',
        bg_image: theme.bg_image || '',
        theme_color: theme.theme_color || '',
      })
      this.apply(r.theme || null)
    },
  },
})
