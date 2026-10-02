/** 核心业务类型（字段与后端 PostCard/PostDetail/Answer/Comment 对齐，技术细节文档 §4.2） */

export interface TagItem {
  id: number
  name: string
}

export interface PostCard {
  id: number
  title: string
  summary: string
  author_id: number
  author_nickname: string
  status: 0 | 1 // 0 待解决 1 已解决
  reward: number
  answer_count: number
  like_count: number
  view_count: number
  tags: TagItem[]
  is_rewarded: boolean
  no_answer_days: number | null
  is_ai_summary?: boolean // summary 为 AI 生成摘要（V1.2），否则为正文截断
  created_at: string
}

export interface PostDetail extends PostCard {
  content: string
  images: string[]
  edited: boolean
  is_liked: boolean
  is_favorite: boolean
  ai_summary?: string | null // AI 摘要全文（生成中/降级时为 null）
  ai_answer?: string | null // AI 参考回答（V1.3，未生成时 null）
  answers: AnswerItem[]
  comments: CommentItem[]
}

export interface AnswerItem {
  id: number
  post_id: number
  author_id: number
  author_nickname: string
  content: string
  is_accepted: boolean
  is_best: boolean
  like_count: number
  ai_rel_score?: number | null // AI 可靠性评分 0-100（V1.3，异步生成中为 null）
  ai_rel_level?: string | null // 高 / 中 / 存疑
  is_liked: boolean
  created_at: string
}

export interface CommentItem {
  id: number
  target_type: number
  target_id: number
  author_id: number
  author_nickname: string
  parent_id: number | null
  reply_to_user_id: number | null
  reply_to_nickname: string | null
  content: string
  like_count: number
  is_liked: boolean
  created_at: string
  replies: CommentItem[]
}

// ---- 个人中心（V1.12）----

export interface MyAnswerItem {
  id: number
  post_id: number
  post_title: string | null // 所属帖已删时 null
  post_status: number | null
  content: string
  is_accepted: boolean
  is_best: boolean
  like_count: number
  created_at: string
}

export interface MyCommentItem {
  id: number
  target_type: number // 1帖子 2回答
  target_id: number
  post_id: number | null
  post_title: string | null
  content: string
  created_at: string
}

export interface MyLikeItem {
  target_type: number // 1帖 2答 3评论
  target_id: number
  post_id: number | null
  post_title: string | null
  content: string
  author_nickname: string | null
  created_at: string
}

export interface Page<T> {
  total: number
  items: T[]
}
