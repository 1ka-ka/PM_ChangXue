# ARCH.md —《畅学》学习问答社区技术架构设计文档

> **文档性质**：草案（V1.0），随开发持续迭代。每次架构变更须更新本文档并在文末"迭代记录"中注明原因。
> **上游依据**：PRD 总册 V1.0、功能需求详述（附录）、MVP 交付清单、技术方案对比文档（已选型：方案 A）。

| 项目 | 内容 |
| --- | --- |
| 创建日期 | 2026-09-01 |
| 版本号 | V1.0（草案） |
| 技术栈 | Vue3 + TypeScript / FastAPI + SQLAlchemy 2.0 / SQLite（开发）→ MySQL（生产） |
| 架构风格 | B/S · 单体分层 · 模块化单体（Modular Monolith） |

---

## 1. 总体架构

### 1.1 架构图

```mermaid
flowchart TB
    subgraph Client[浏览器]
        W1[Web 前端 SPA<br/>Vue3 + TS + Element Plus]
        W2[管理后台 SPA<br/>复用同一前端项目 /admin 路由]
    end

    subgraph Server[服务端 单体 FastAPI]
        NG[Nginx 反向代理<br/>静态资源 + API 转发]

        subgraph App[应用层 Uvicorn]
            API[API 层 routers<br/>REST JSON]
            SVC[服务层 services<br/>业务逻辑 编排]
            REPO[数据访问层 repositories<br/>SQLAlchemy]
            GW[LLM 网关模块 gateway<br/>P0 仅契约 P1 接模型]
            JOB[定时任务 scheduler<br/>榜单结算/日志清理]
            EVT[埋点采集 events<br/>异步落库]
        end

        AUTH[认证中间件<br/>JWT + 手机号+密码]
    end

    subgraph Storage[存储]
        DB[(数据库<br/>SQLite 开发 / MySQL 生产)]
        FS[图片存储<br/>本地磁盘 生产可换 OSS)]
    end

    subgraph External[P1 外部依赖]
        LLM1[GLM-4.5-Flash 生成类]
        LLM2[DeepSeek-V3 推理类]
        SMS[短信服务 P1]
    end

    W1 --> NG
    W2 --> NG
    NG --> API
    API --> AUTH
    API --> SVC
    SVC --> REPO
    SVC --> GW
    SVC --> EVT
    REPO --> DB
    SVC --> FS
    GW -.P1.-> LLM1
    GW -.P1.-> LLM2
    SVC -.P1.-> SMS
    JOB --> REPO
```

### 1.2 架构原则

| # | 原则 | 说明 |
| --- | --- | --- |
| 1 | 模块化单体 | 单进程部署，目录按业务域分模块；模块间只经 service 接口调用，禁止跨模块直连他人 repository——为未来拆分保接缝 |
| 2 | 服务端权威 | 积分、感谢值、状态机、排序等一切数值与状态判定全部在服务端，前端只展示 |
| 3 | 配置外置 | 积分数值、封顶、衰减阈值、AI 延迟时长等全部进配置，不硬编码 |
| 4 | LLM 可插拔 | 网关独立模块 + 场景路由 + 契约先行，P0 零调用，P1 热替换模型 |
| 5 | 降级优先 | AI/搜索增强失败不阻塞主流程，全部有非 AI 兜底路径 |
| 6 | 演进不推倒 | 表结构按 PRD 依赖链预留（通知、消息、商城枚举），避免 P1/P2 迁移 |

## 2. 目录结构

```
changxue/
├── backend/                        # FastAPI 服务端
│   ├── app/
│   │   ├── main.py                 # 应用入口、中间件、路由注册
│   │   ├── core/                   # 横切基础设施
│   │   │   ├── config.py           # 配置（env 驱动，含积分/阈值全部参数）
│   │   │   ├── security.py         # JWT 签发校验、密码哈希
│   │   │   ├── database.py         # SQLAlchemy engine/session 工厂
│   │   │   ├── deps.py             # 依赖注入（当前用户、DB 会话、权限）
│   │   │   └── exceptions.py       # 统一业务异常 → 错误码约定
│   │   ├── modules/                # ★ 业务模块（按 PRD 模块划分）
│   │   │   ├── account/            # M1 注册登录/资料/个人主页
│   │   │   ├── post/               # M2 发帖/回答/评论/点赞收藏
│   │   │   ├── accept/             # M2 采纳与状态机（独立模块：事务核心）
│   │   │   ├── feed/               # M3 广场/推荐/悬赏加权
│   │   │   ├── search/             # M4 搜索/知识库消费/降级
│   │   │   ├── credit/             # M5 积分账户/流水/封顶/追回
│   │   │   ├── rank/               # M5 感谢值/助人榜/定时结算
│   │   │   ├── notify/             # M6 站内通知
│   │   │   ├── moderation/         # M7 举报/管理员处置/操作日志
│   │   │   ├── admin/              # M7 管理后台 API（标签管理/封禁）
│   │   │   └── tracking/           # 埋点事件接收与落库
│   │   ├── gateway/                # ★ LLM 统一网关（P0 仅契约）
│   │   │   ├── contracts.py        # 5 类场景输入输出 Pydantic 契约
│   │   │   ├── router.py           # 场景→模型路由（配置驱动）
│   │   │   └── client.py           # P1 实现：调用/重试/降级/日志
│   │   ├── jobs/                   # 定时任务（榜单结算/推荐衰减/流水对账）
│   │   ├── models/                 # SQLAlchemy 表模型（全模块共享）
│   │   ├── schemas/                # Pydantic 请求/响应模型
│   │   └── api/                    # 路由聚合（薄层，只做参数校验和调 service）
│   ├── alembic/                    # 数据库迁移（生产 MySQL 必须）
│   ├── tests/                      # pytest：核心闭环+积分账务自动化回归
│   └── pyproject.toml
├── frontend/                       # Vue3 SPA
│   ├── src/
│   │   ├── api/                    # 按模块划分的 API 封装（由后端 OpenAPI 生成类型）
│   │   ├── views/
│   │   │   ├── plaza/              # 广场（Tab：推荐/最新/待解决）
│   │   │   ├── post/               # 发帖页/帖子详情页
│   │   │   ├── search/             # 搜索结果页
│   │   │   ├── rank/               # 助人榜
│   │   │   ├── profile/            # 个人主页/资料编辑/积分明细
│   │   │   ├── notify/             # 通知中心
│   │   │   ├── auth/               # 注册/登录
│   │   │   └── admin/              # 管理后台页面（举报队列/处置）
│   │   ├── components/             # 帖子卡片/评论树/状态标签等
│   │   ├── stores/                 # Pinia（用户态/通知计数）
│   │   └── router/
│   └── package.json
├── deploy/                         # 部署配置（nginx.conf、systemd、docker 可选）
└── docs/                           # PRD/详述/交付清单/ARCH（本项目文档）
```

**模块内部约定**（每模块统一结构）：

```
modules/post/
├── service.py      # 业务逻辑（对外唯一入口）
├── repository.py   # 数据访问（仅本模块与 credit/accept 等被显式允许者可引）
└── (可选) helper.py
```

## 3. 核心模块与职责

| 模块 | 职责 | 服务端关键逻辑 |
| --- | --- | --- |
| account | 注册（+50 积分事务内发放）、登录、JWT、资料、个人主页聚合 | 密码哈希（bcrypt）；注册与积分开户在同一 DB 事务 |
| post | 帖子/回答/双层评论/点赞收藏的 CRUD 与计数 | 敏感词前置过滤；点赞幂等（唯一约束 user_id+object）；评论二层封顶归并；删除级联 |
| **accept** | 采纳状态机（本系统事务核心） | 首次采纳单事务内完成：状态置已解决→知识库收录→+30 积分→+30 感谢值→通知；上限 3 校验；更换最佳零账务变动 |
| feed | 广场三 Tab 排序 | 推荐分 = 热度(浏览/回答/点赞) + 悬赏加权 − 时间衰减（14 天无采纳）；全部参数配置化 |
| search | 标签筛选+标题模糊；知识库优先→降级广场 | 降级触发写 `search_degrade` 埋点；SQLite 用 LIKE，MySQL 兼容（P0 不引入全文索引） |
| **credit** | 积分账户/流水/日封顶/余额校验 | 账务唯一入口：所有分值变动经 `CreditService.grant/deduct()`，行锁防并发透支；日封顶查询当日累计产出后决定是否发放 |
| rank | 感谢值累计、周/月榜、结算任务 | 结算快照表（防历史数据变动影响已公布榜单）；周一/月初 0 点定时任务 + 失败重试告警 |
| notify | 五类互动通知 | 生成/已读/聚合；内容删除时通知保留但标记失效 |
| moderation | 举报队列、管理员处置、操作日志 | 删除=软删（统一 deleted_at），广场/搜索/知识库查询全局过滤；处置写操作日志表 |
| tracking | 埋点接收 | 批量异步写入事件表，不阻塞业务响应 |
| gateway (LLM) | P0：契约定义；P1：场景路由/调用/降级/成本日志 | 5 类场景契约见第 6 章 |

## 4. 服务端/前端逻辑边界

**必须且仅在服务端**（前端传入一律不信任）：

1. 积分与感谢值的一切计算与发放（含日封顶判定）
2. 采纳权限（仅提问者）、采纳上限、状态机流转、知识库收录触发
3. 排序与推荐分计算（悬赏加权、衰减）
4. 搜索匹配与降级决策
5. 权限判定（管理员接口、本人资源）
6. 敏感词过滤、举报去重
7. 帖子状态标识（待解决/已解决/X 天未回答——时间计算在服务端）

**前端负责**：表单必填校验与即时反馈、Tab 状态与浏览位置、图片压缩预览、未读计数展示、发帖正文本地缓存（草稿）。

## 5. 数据模型概要

| 表 | 关键字段要点 |
| --- | --- |
| user | id、phone（唯一，主账号）、password_hash、nickname、avatar、school、major、role(user/admin)、status(正常/封禁+到期时间)、created_at |
| post | id、author_id、title、content、images(JSON)、status(待解决/已解决)、reward（悬赏档位，0=无）、last_answer_at、accepted_at、deleted_at |
| post_tag / tag | tag(id、name、enabled)；post_tag(post_id、tag_id) |
| answer | id、post_id、author_id、content、is_accepted、is_best（唯一约束：post 内 is_best 至多 1）、like_count、deleted_at |
| comment | id、target_type(post/answer)、target_id、author_id、parent_id（二层封顶：parent 必须为根评论）、reply_to_user_id、like_count、deleted_at |
| like / favorite | (user_id、target_type、target_id) 唯一约束保证幂等 |
| knowledge_item | post_id 唯一（首次采纳创建，内容随帖实时联查，不冗余存储） |
| credit_account | user_id 唯一、balance（≥0 约束） |
| credit_log | id、user_id、change(±)、balance_after、source 枚举(注册/登录/任务/采纳/悬赏/追回/商城)、ref(关联对象)、created_at、日封顶备注字段 |
| gratitude_stat | user_id、period_type(周/月)、period_key(如 2026-W36)、value（结算快照） |
| rank_snapshot | period_type、period_key、rank、user_id、value（榜单公布依据） |
| notification | id、user_id、type(5 类)、actor_id、target_type/target_id、is_read、invalid(内容删除标记) |
| report | id、reporter_id、target_type/target_id、reason 类型、detail、status(待处理/已处置/驳回)、handled_by、created_at |
| admin_action_log | id、admin_id、action(删/封/追分/恢复/驳回)、target、reason、created_at |
| tracking_event | id、user_id、event_name、props(JSON)、created_at（索引：event_name+created_at） |
| app_config | key、value(JSON)——积分分值/阈值/标签开关等运行时配置 |

**预留扩展**（P0 建表或仅设计评审确认）：message 私聊表（P2）、shop_goods/exchange_order（P1 契约）、ai_summary/ai_answer 字段挂 post/answer（P1 启用）。

## 6. LLM 网关契约（P0 交付物定义）

| 场景 | 输入 | 输出 | P1 默认模型 |
| --- | --- | --- | --- |
| summary 摘要 | title、content、images OCR 文本 | summary(≤100 字)、need_review | GLM-4.5-Flash |
| ref_answer 参考回答 | post 全量 | answer_text、confidence | GLM-4.5-Flash |
| reliability 可靠性 | post + answer | score(0-100)、level(高/中/存疑) | DeepSeek-V3 |
| quality 质量检测 | answer + 用户历史回答样本 | is_low_quality、reason | DeepSeek-V3 |
| moderation 违规分级 | content | level(极高/高/低)、violation_type | 安全模型+词库前置 |

统一约定：全部走 `GatewayClient.invoke(scene, payload)`；超时默认 10s；失败按场景降级（总册 §10.4）；每次调用写调用日志（场景/tokens/耗时/结果）。契约以 `gateway/contracts.py` 的 Pydantic 模型为准，直接作为 MVP 交付清单第 3.1 项的评审物。

## 7. 关键机制设计

### 7.1 积分账务（一致性核心）

```
CreditService.grant(user, source, ref, amount):
  DB 事务 {
    1. 锁定 credit_account 行（SELECT ... FOR UPDATE / SQLite 串行化）
    2. 若 source ∈ 产出类: 查询当日 credit_log 产出合计，超日封顶 → 记录封顶备注，return 不发放（感谢值不受影响，由 accept 模块独立处理）
    3. balance += amount；写 credit_log（含 balance_after）
  }
deduct(): 同事务，余额不足抛业务异常 → 对应操作（如悬赏发布）整体回滚
```

- 积分发放与业务动作（采纳/注册/悬赏）**同库同事务**，不引入消息队列；跨模块调用经 service 接口显式事务边界管理。

### 7.2 采纳状态机（事务编排）

```
AcceptService.accept(post, answer, user):
  校验(user==提问者, 帖子采纳数<3, answer 未删) →
  单事务 {
    answer.is_accepted=True
    若帖子首次采纳: post.status=已解决; 创建 knowledge_item
    credit.grant(+30)（同事务调用）
    gratitude.累计(+30)
    notify(被采纳通知)
  }
set_best(): 校验目标 is_accepted → 事务内调整 is_best 标记；无任何账务变动
```

### 7.3 定时任务

| 任务 | 频率 | 说明 |
| --- | --- | --- |
| 榜单结算 | 每周一/每月 1 日 0 点 | 统计感谢值写 rank_snapshot；失败重试 3 次+告警，成功前榜单沿用上期并标注"结算更新中" |
| 推荐衰减刷新 | 每日 | 按发布时间与采纳状态批量更新衰减权重缓存 |
| 流水对账 | 每日 | credit_log 的 balance_after 连续性校验（自动测试同款逻辑线上化） |

### 7.4 埋点管道

前端调用 `POST /api/events/batch`（页面卸载前 sendBeacon）；服务端异步批量写入 tracking_event，失败丢弃不影响业务（埋点不承诺 100%）。

## 8. 部署架构

| 环境 | 形态 |
| --- | --- |
| 本地开发 | `uvicorn` + SQLite + Vite dev server；一键脚本启动前后端 |
| 生产 | Nginx（前端静态 + /api 反代 + HTTPS/证书）→ Uvicorn（单进程多 worker 起步）→ MySQL；图片存本地磁盘（Nginx 直出 /uploads，P2 可平滑换 OSS）；部署脚本与 systemd 单元放 deploy/ |

不引入：Docker/K8s/Redis/Celery/消息队列（当前规模不需要；若 P1 AI 检测量增大，评估 APScheduler → Celery 的升级点，见迭代记录约定）。

## 9. 测试策略

| 层 | 范围 |
| --- | --- |
| 单元测试 | credit 账务（封顶/透支/流水连续）、accept 状态机、feed 排序分——对应 MVP 清单 §6.5 自动化回归用例 |
| 集成测试 | 核心闭环 API 链路（注册→发帖→回答→采纳→搜索命中），跑 SQLite 内存库 |
| 契约测试 | LLM 网关 5 场景 Schema 校验（P0 无模型调用） |

---

## 迭代记录

| 日期 | 版本 | 变更内容 | 迭代原因 |
| --- | --- | --- | --- |
| 2026-09-01 | V1.0 草案 | 全文创建：选型方案 A、分层架构、模块划分、数据模型、LLM 契约、关键机制 | MVP 开发启动前定稿 |
