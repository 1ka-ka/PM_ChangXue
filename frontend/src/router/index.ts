/**
 * 路由（history 模式）：占位页由后续子增量填充。
 * meta.requiresAuth → 未登录跳 /login；meta.admin → 非管理员回广场。
 */
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { guest: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        { path: '', redirect: '/feed' },
        { path: 'feed', name: 'feed', component: () => import('@/views/FeedView.vue') },
        { path: 'ranks', name: 'ranks', component: () => import('@/views/RankView.vue') },
        { path: 'mall', name: 'mall', component: () => import('@/views/MallView.vue') },
        { path: 'search', name: 'search', component: () => import('@/views/SearchView.vue') },
        {
          path: 'posts/create',
          name: 'post-create',
          component: () => import('@/views/PostCreateView.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'posts/:id',
          name: 'post-detail',
          component: () => import('@/views/PostDetailView.vue'),
        },
        {
          path: 'notifications',
          name: 'notifications',
          component: () => import('@/views/NotificationsView.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'messages',
          name: 'messages',
          component: () => import('@/views/MessagesView.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'u/:id',
          name: 'profile',
          component: () => import('@/views/ProfileView.vue'),
        },
        {
          path: 'admin',
          name: 'admin',
          component: () => import('@/views/admin/AdminView.vue'),
          meta: { requiresAuth: true, admin: true },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/feed' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.token && to.meta.requiresAuth) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (auth.token && !auth.user) {
    await auth.fetchMe()
  }
  if (to.meta.admin && !auth.user?.is_admin) {
    return { path: '/feed' }
  }
  if (to.meta.guest && auth.token) {
    return { path: '/feed' }
  }
})

export default router
