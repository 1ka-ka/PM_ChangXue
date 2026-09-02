/**
 * Axios 单实例封装（技术细节文档 §1.2 统一要求）
 * - 自动附带 JWT
 * - 401 统一跳登录（清 token 后带 redirect 回跳）
 * - 响应信封拆包：{ code, msg, data } → data（非 0 抛 ApiError）
 * - 204（埋点等）直接返回 null
 */
import axios, { AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

export const TOKEN_KEY = 'cx_token'

/** 业务错误：携带后端 code/msg（信封 code 非 0） */
export class ApiError extends Error {
  code: number
  constructor(code: number, msg: string) {
    super(msg)
    this.code = code
  }
}

export const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

// 请求拦截：附带 JWT
http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：拆信封 / 401 跳登录
http.interceptors.response.use(
  (resp) => {
    if (resp.status === 204) return null
    const body = resp.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) return body.data
      // 业务错误（含 401xx 由 HTTP 401 分支处理前不会到这，防御性处理）
      if (body.code >= 40100 && body.code < 40200) {
        logoutAndRedirect()
      }
      return Promise.reject(new ApiError(body.code, body.msg || '请求失败'))
    }
    return body
  },
  (error: AxiosError<{ code?: number; msg?: string }>) => {
    const status = error.response?.status
    const body = error.response?.data
    if (status === 401) {
      logoutAndRedirect()
      return Promise.reject(new ApiError(40102, '登录已失效，请重新登录'))
    }
    if (status === 429) {
      return Promise.reject(new ApiError(40006, body?.msg || '请求过于频繁'))
    }
    const msg = body?.msg || (error.message === 'Network Error' ? '网络异常，请检查后端服务' : '请求失败')
    if (body?.code) {
      return Promise.reject(new ApiError(body.code, msg))
    }
    ElMessage.error(msg)
    return Promise.reject(new ApiError(50001, msg))
  },
)

function logoutAndRedirect() {
  localStorage.removeItem(TOKEN_KEY)
  const { pathname } = window.location
  if (!pathname.startsWith('/login')) {
    window.location.href = `/login?redirect=${encodeURIComponent(pathname)}`
  }
}

/** 便捷方法（保留泛型推断，调用侧用 as 断言生成的 API 类型） */
export const get = <T = unknown>(url: string, params?: object) =>
  http.get(url, { params }) as Promise<T>
export const post = <T = unknown>(url: string, data?: object) => http.post(url, data) as Promise<T>
export const put = <T = unknown>(url: string, data?: object) => http.put(url, data) as Promise<T>
export const del = <T = unknown>(url: string) => http.delete(url) as Promise<T>
