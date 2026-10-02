"""系统账号自动运营（V1.13，P1）。

设计（用户已确认的 4 项决策）：
- 固定池 12 个左右运营账号（人设各异：技术方向/学校/语气/活跃度），复用 seed_demo 前 8 个
- 内容 LLM 全生成（op_question/op_answer/op_comment 三场景），降级时跳过该动作或仅执行免 LLM 动作
- 积分正常循环 + 定期补贴（余额低于阈值补到目标值，走 TASK 流水受日封顶约束）
- 手动触发一轮 = 随机 1-3 个动作（不受配额/时段限制，供管理员演示与冷启动补充）

运营账号与真人地位等同：真实落库、可上排行榜、任何 API 不暴露 is_op、内容不标注。
"""

import random
from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import BizError, ErrCode
from app.core.security import hash_password
from app.gateway.client import LLMDegradedError, gateway
from app.models import Answer, Comment, LikeRecord, OperationLog, Post, Tag, User
from app.modules.accept import service as accept_service
from app.modules.credit import service as credit_service
from app.modules.credit.sources import CreditSource
from app.modules.post import answers as answer_service
from app.modules.post import service as post_service
from app.modules.post import comments as comment_service
from app.modules.post import likes as like_service

# operation_log.action 枚举
ACT_QUESTION, ACT_ANSWER, ACT_COMMENT, ACT_REPLY = 1, 2, 3, 4
ACT_ADOPT, ACT_LIKE, ACT_SUBSIDY, ACT_CREATE = 5, 6, 7, 8

ACTION_TEXT = {
    1: "提问", 2: "回答", 3: "评论", 4: "回复",
    5: "采纳", 6: "点赞", 7: "积分补贴", 8: "建号",
}
_INTERACTION_ACTIONS = (ACT_ANSWER, ACT_COMMENT, ACT_REPLY, ACT_ADOPT, ACT_LIKE)

OP_PASSWORD = "demo123456"  # 与 seed_demo 演示账号一致（运营账号与真人地位等同，可正常登录）

# 12 个运营人设：前 8 个与 seed_demo 演示用户同号（手机号 13800000101-108），后 4 个新增
PERSONAS = [
    {"phone": "13800000101", "nickname": "码农阿伟", "school": "华中科技大学", "major": "计算机科学与技术",
     "focus": "Python 后端与工程实践", "style": "务实简洁，爱给工程建议", "weight": 1.4},
    {"phone": "13800000102", "nickname": "LeetCode苦手", "school": "武汉大学", "major": "软件工程",
     "focus": "算法刷题与面试准备", "style": "爱举刷题实例，偶尔自嘲", "weight": 1.2},
    {"phone": "13800000103", "nickname": "操作系统迷", "school": "哈尔滨工业大学", "major": "计算机科学与技术",
     "focus": "操作系统与计算机底层", "style": "严谨考据，喜欢引原理", "weight": 1.0},
    {"phone": "13800000104", "nickname": "前端小旋风", "school": "中山大学", "major": "软件工程",
     "focus": "前端开发 Vue/JavaScript", "style": "活泼，爱用表情和短句", "weight": 1.3},
    {"phone": "13800000105", "nickname": "算法做题家", "school": "电子科技大学", "major": "人工智能",
     "focus": "机器学习与数学基础", "style": "推导细致，爱讲思路", "weight": 1.0},
    {"phone": "13800000106", "nickname": "数据库咸鱼", "school": "东南大学", "major": "数据科学",
     "focus": "数据库与 SQL 优化", "style": "佛系但靠谱，爱给性能数字", "weight": 0.9},
    {"phone": "13800000107", "nickname": "网络包侦探", "school": "西安电子科技大学", "major": "网络工程",
     "focus": "计算机网络与抓包分析", "style": "爱画时序，讲抓包案例", "weight": 0.9},
    {"phone": "13800000108", "nickname": "编译原理幸存者", "school": "北京邮电大学", "major": "计算机科学与技术",
     "focus": "编译原理与编程语言", "style": "学霸口吻，爱较真术语", "weight": 0.8},
    {"phone": "13800000109", "nickname": "考研上岸锦鲤", "school": "四川大学", "major": "软件工程",
     "focus": "408 考研全科复习", "style": "励志语气，爱分享时间规划", "weight": 1.1},
    {"phone": "13800000110", "nickname": "炼丹师小张", "school": "浙江大学", "major": "人工智能",
     "focus": "深度学习框架与调参", "style": "爱聊实验踩坑，术语多", "weight": 1.0},
    {"phone": "13800000111", "nickname": "安卓练习生", "school": "华中科技大学", "major": "软件工程",
     "focus": "安卓移动端开发", "style": "新手视角，爱问细节", "weight": 0.9},
    {"phone": "13800000112", "nickname": "网安小白鸽", "school": "武汉大学", "major": "网络空间安全",
     "focus": "Web 安全与渗透入门", "style": "好奇宝宝，爱追问为什么", "weight": 0.8},
]


def _persona_desc(p: dict) -> str:
    return f"{p['nickname']}，{p['school']}{p['major']}学生，专注{p['focus']}，语气{p['style']}"


def _llm_ready() -> bool:
    return bool(settings.LLM_ENABLED and settings.LLM_API_KEY)


def _log(db: Session, action: int, ok: bool, detail: str,
         user_id: int | None = None, target_type: int | None = None, target_id: int | None = None) -> None:
    db.add(OperationLog(
        user_id=user_id, action=action, ok=1 if ok else 0,
        target_type=target_type, target_id=target_id, detail=detail[:200],
    ))
    db.commit()


# ---- 账号池 ----


def ensure_accounts(db: Session) -> list[User]:
    """幂等确保 12 个运营账号存在（老演示用户补 is_op 标记与资料），返回 User 列表。"""
    users: list[User] = []
    created = False
    for p in PERSONAS:
        u = db.execute(select(User).where(User.phone == p["phone"])).scalar_one_or_none()
        if u is None:
            u = User(
                phone=p["phone"], password_hash=hash_password(OP_PASSWORD),
                nickname=p["nickname"], school=p["school"], major=p["major"], is_op=1,
            )
            db.add(u)
            db.flush()
            credit_service.grant(
                db, u.id, CreditSource.REGISTER, settings.CREDIT_REGISTER,
                note="注册赠送（系统运营账号）",
            )
            _log(db, ACT_CREATE, True, f"创建运营账号「{p['nickname']}」（{p['focus']}）", user_id=u.id)
            created = True
        else:
            changed = False
            if not u.is_op:
                u.is_op = 1
                changed = True
            if not u.school and p["school"]:
                u.school, u.major = p["school"], p["major"]
                changed = True
            if changed:
                db.commit()
        users.append(u)
    if created:
        db.commit()
    return users


def _pick_persona(accounts: list[User]) -> tuple[User, dict]:
    """按活跃度权重随机挑一个运营账号。"""
    weights = [p["weight"] for p in PERSONAS]
    idx = random.choices(range(len(PERSONAS)), weights=weights, k=1)[0]
    return accounts[idx], PERSONAS[idx]


def _touch(db: Session, user: User) -> None:
    """更新 last_login_at 让 DAU 统计真实反映运营活跃（服务层 commit 时一并落库）。"""
    user.last_login_at = datetime.now()


# ---- 当日进度 ----


def _today_start() -> datetime:
    return datetime.combine(datetime.now().date(), time.min)


def today_progress(db: Session) -> dict:
    """当日配额进度（仅统计成功动作）。"""
    rows = db.execute(
        select(OperationLog.action).where(
            OperationLog.ok == 1, OperationLog.created_at >= _today_start(),
            OperationLog.action.in_([ACT_QUESTION, *_INTERACTION_ACTIONS]),
        )
    ).scalars().all()
    questions = rows.count(ACT_QUESTION)
    interactions = sum(1 for a in rows if a != ACT_QUESTION)
    return {"questions": questions, "interactions": interactions}


# ---- 动作实现（每个动作独立 try/except，失败仅记日志不影响其他动作）----


def _act_question(db: Session, accounts: list[User]) -> dict:
    user, persona = _pick_persona(accounts)
    tags = db.execute(select(Tag).where(Tag.enabled == 1).order_by(Tag.sort, Tag.id)).scalars().all()
    if not tags:
        return {"action": ACT_QUESTION, "ok": False, "detail": "无可用标签，跳过"}
    recent = (
        db.execute(select(Post.title).where(Post.deleted_at.is_(None)).order_by(Post.id.desc()).limit(30))
        .scalars().all()
    )
    out = gateway.invoke("op_question", {
        "persona": _persona_desc(persona),
        "tag_names": [t.name for t in tags],
        "recent_titles": list(recent),
    })
    # 标签名 → id（LLM 给出的名字不在池内时回退第一个标签）
    name_to_id = {t.name: t.id for t in tags}
    tag_ids = list({name_to_id.get(n, tags[0].id) for n in out["tags"]})[: settings.TAG_MAX_PER_POST]
    reward = random.choice([0, 0, 0, 10, 20])  # 少数悬赏帖，拟真
    _touch(db, user)
    try:
        data = post_service.create_post(db, user, out["title"], out["content"], [], tag_ids, reward)
    except BizError as e:
        if e.code == ErrCode.CREDIT_INSUFFICIENT and reward > 0:  # 余额不足 → 降级为零悬赏重试
            reward = 0
            data = post_service.create_post(db, user, out["title"], out["content"], [], tag_ids, 0)
        else:
            raise
    post_service.generate_ai_summary_task(data["id"])  # 同步补 AI 摘要（独立会话）
    _log(db, ACT_QUESTION, True, f"发布提问「{out['title']}」{'（悬赏 %d）' % reward if reward else ''}",
         user_id=user.id, target_type=1, target_id=data["id"])
    return {"action": ACT_QUESTION, "ok": True, "detail": out["title"], "post_id": data["id"]}


def _act_answer(db: Session, accounts: list[User]) -> dict:
    posts = (
        db.execute(
            select(Post).where(Post.deleted_at.is_(None)).order_by(Post.id.desc()).limit(50)
        ).scalars().all()
    )
    # 优先无人回答且发布超过 10 分钟的待解决帖（避免秒答自家新帖），其次任意近期帖
    pending = [p for p in posts if p.answer_count == 0 and p.status == 0
               and (datetime.now() - p.created_at).total_seconds() > 600]
    pool = pending or [p for p in posts if p.status == 0]
    random.shuffle(pool)
    for post in pool:
        answered = set(
            db.execute(
                select(Answer.author_id).where(
                    Answer.post_id == post.id, Answer.deleted_at.is_(None)
                )
            ).scalars().all()
        )
        candidates = [(u, p) for (u, p) in zip(accounts, PERSONAS)
                      if u.id != post.author_id and u.id not in answered]
        if not candidates:
            continue
        user, persona = random.choices(candidates, weights=[p["weight"] for _, p in candidates], k=1)[0]
        out = gateway.invoke("op_answer", {
            "persona": _persona_desc(persona),
            "post_title": post.title,
            "post_content": (post.content or "")[:2000],
            "tag_names": [t.name for t in post_service._tags_of(db, post.id)],
        })
        _touch(db, user)
        data = answer_service.create_answer(db, user, post.id, out["content"])  # 含质量检测（40913 拦截）
        answer_service.generate_reliability_task(data["id"])  # 同步补 AI 可靠性评分
        _log(db, ACT_ANSWER, True, f"回答「{post.title}」",
             user_id=user.id, target_type=2, target_id=data["id"])
        return {"action": ACT_ANSWER, "ok": True, "detail": post.title, "answer_id": data["id"]}
    return {"action": ACT_ANSWER, "ok": False, "detail": "暂无可回答的帖子，跳过"}


def _act_comment(db: Session, accounts: list[User]) -> dict:
    user, persona = _pick_persona(accounts)
    # 60% 评论帖子，40% 评论回答
    if random.random() < 0.6:
        target_type = 1
        rows = (db.execute(
            select(Post).where(Post.deleted_at.is_(None), Post.author_id != user.id)
            .order_by(Post.id.desc()).limit(30)
        ).scalars().all())
        if not rows:
            return {"action": ACT_COMMENT, "ok": False, "detail": "无可评论帖子，跳过"}
        target = random.choice(rows)
        post_title, excerpt = target.title, (target.content or "")[:200]
        target_id = target.id
    else:
        target_type = 2
        rows = (db.execute(
            select(Answer).join(Post, Post.id == Answer.post_id)
            .where(Answer.deleted_at.is_(None), Post.deleted_at.is_(None), Answer.author_id != user.id)
            .order_by(Answer.id.desc()).limit(30)
        ).scalars().all())
        if not rows:
            return {"action": ACT_COMMENT, "ok": False, "detail": "无可评论回答，跳过"}
        target = random.choice(rows)
        post = db.get(Post, target.post_id)
        post_title, excerpt = post.title, (target.content or "")[:200]
        target_id = target.id
    out = gateway.invoke("op_comment", {
        "persona": _persona_desc(persona), "post_title": post_title,
        "target_excerpt": excerpt, "is_reply": False,
    })
    _touch(db, user)
    comment_service.create_comment(db, user, target_type, target_id, out["content"], None, None)
    _log(db, ACT_COMMENT, True, f"评论「{post_title}」",
         user_id=user.id, target_type=target_type, target_id=target_id)
    return {"action": ACT_COMMENT, "ok": True, "detail": post_title}


def _reply_target_alive(db: Session, root: Comment) -> bool:
    """回复目标存活校验：删帖后评论残留（target_type=1）或回答被删（=2）时不可回复。"""
    if root.target_type == 1:
        p = db.get(Post, root.target_id)
        return p is not None and p.deleted_at is None
    a = db.get(Answer, root.target_id)
    if a is None or a.deleted_at is not None:
        return False
    p = db.get(Post, a.post_id)
    return p is not None and p.deleted_at is None


def _act_reply(db: Session, accounts: list[User]) -> dict:
    user, persona = _pick_persona(accounts)
    roots = (db.execute(
        select(Comment).where(
            Comment.deleted_at.is_(None), Comment.parent_id.is_(None), Comment.author_id != user.id
        ).order_by(Comment.id.desc()).limit(30)
    ).scalars().all())
    roots = [r for r in roots if _reply_target_alive(db, r)]  # 过滤目标已删的残留评论
    if not roots:
        return {"action": ACT_REPLY, "ok": False, "detail": "无可回复评论，跳过"}
    root = random.choice(roots)
    if root.target_type == 1:
        post = db.get(Post, root.target_id)
        post_title = post.title if post else ""
    else:
        a = db.get(Answer, root.target_id)
        post = db.get(Post, a.post_id) if a else None
        post_title = post.title if post else ""
    out = gateway.invoke("op_comment", {
        "persona": _persona_desc(persona), "post_title": post_title,
        "target_excerpt": (root.content or "")[:200], "is_reply": True,
        "reply_to": (db.get(User, root.author_id).nickname if db.get(User, root.author_id) else ""),
    })
    _touch(db, user)
    comment_service.create_comment(
        db, user, root.target_type, root.target_id, out["content"], root.id, root.author_id
    )
    _log(db, ACT_REPLY, True, f"回复评论「{(root.content or '')[:30]}」",
         user_id=user.id, target_type=3, target_id=root.id)
    return {"action": ACT_REPLY, "ok": True, "detail": post_title}


def _act_adopt(db: Session, accounts: list[User]) -> dict:
    """运营账号以提问者身份采纳自己帖子的回答（优先发布超过 2 小时的待解决帖，拟真『提问者回来采纳』）。"""
    op_ids = [u.id for u in accounts]
    posts = (db.execute(
        select(Post).where(
            Post.deleted_at.is_(None), Post.status == 0, Post.answer_count > 0,
            Post.author_id.in_(op_ids),
        ).order_by(Post.id.desc()).limit(30)
    ).scalars().all())
    aged = [p for p in posts if (datetime.now() - (p.last_answer_at or p.created_at)).total_seconds() > 7200]
    pool = aged or posts
    random.shuffle(pool)
    for post in pool:
        user = next(u for u in accounts if u.id == post.author_id)
        answers = (db.execute(
            select(Answer).where(
                Answer.post_id == post.id, Answer.deleted_at.is_(None),
                Answer.is_accepted == 0, Answer.author_id != post.author_id,
            )
        ).scalars().all())
        if not answers:
            continue
        # 拟真选择：优先可靠性评分高/获赞多的回答，带随机性
        answers.sort(key=lambda a: (-a.like_count, -(a.ai_rel_score or 0), random.random()))
        target = answers[0]
        _touch(db, user)
        accept_service.accept(db, user, target.id)
        _log(db, ACT_ADOPT, True, f"采纳回答（帖子「{post.title}」）",
             user_id=user.id, target_type=2, target_id=target.id)
        return {"action": ACT_ADOPT, "ok": True, "detail": post.title, "answer_id": target.id}
    return {"action": ACT_ADOPT, "ok": False, "detail": "暂无可采纳的回答，跳过"}


def _act_like(db: Session, accounts: list[User]) -> dict:
    user, _ = _pick_persona(accounts)
    if random.random() < 0.6:
        rows = (db.execute(
            select(Post).where(Post.deleted_at.is_(None), Post.author_id != user.id)
            .order_by(Post.id.desc()).limit(30)
        ).scalars().all())
        liked_ids = set(db.execute(
            select(LikeRecord.target_id).where(
                LikeRecord.user_id == user.id, LikeRecord.target_type == 1
            )
        ).scalars().all())
        rows = [p for p in rows if p.id not in liked_ids]
        if not rows:
            return {"action": ACT_LIKE, "ok": False, "detail": "无新可点赞内容，跳过"}
        target = random.choice(rows)
        _touch(db, user)
        like_service.toggle_like(db, user, 1, target.id)
        _log(db, ACT_LIKE, True, f"点赞帖子「{target.title}」", user_id=user.id, target_type=1, target_id=target.id)
        return {"action": ACT_LIKE, "ok": True, "detail": target.title}
    rows = (db.execute(
        select(Answer).join(Post, Post.id == Answer.post_id)
        .where(Answer.deleted_at.is_(None), Post.deleted_at.is_(None), Answer.author_id != user.id)
        .order_by(Answer.id.desc()).limit(30)
    ).scalars().all())
    liked_ids = set(db.execute(
        select(LikeRecord.target_id).where(
            LikeRecord.user_id == user.id, LikeRecord.target_type == 2
        )
    ).scalars().all())
    rows = [a for a in rows if a.id not in liked_ids]
    if not rows:
        return {"action": ACT_LIKE, "ok": False, "detail": "无新可点赞内容，跳过"}
    target = random.choice(rows)
    _touch(db, user)
    like_service.toggle_like(db, user, 2, target.id)
    _log(db, ACT_LIKE, True, "点赞回答", user_id=user.id, target_type=2, target_id=target.id)
    return {"action": ACT_LIKE, "ok": True, "detail": "点赞了一条回答"}


# 免 LLM 动作（降级时仍可执行，保证基础生态运转）
_NO_LLM_ACTIONS = (ACT_ADOPT, ACT_LIKE)
# 全量动作及权重
_ACTION_WEIGHTS = [
    (ACT_QUESTION, 20), (ACT_ANSWER, 30), (ACT_COMMENT, 15),
    (ACT_REPLY, 10), (ACT_ADOPT, 10), (ACT_LIKE, 15),
]


def _do_one_action(db: Session, accounts: list[User], manual: bool) -> dict:
    progress = today_progress(db)
    llm = _llm_ready()

    # 可选动作池：配额过滤 + LLM 可用性过滤
    pool = []
    for action, weight in _ACTION_WEIGHTS:
        if action == ACT_QUESTION and not manual and progress["questions"] >= settings.OP_DAILY_QUESTIONS:
            continue
        if action in _INTERACTION_ACTIONS and not manual and progress["interactions"] >= settings.OP_DAILY_INTERACTIONS:
            continue
        if action not in _NO_LLM_ACTIONS and not llm:
            continue
        pool.append((action, weight))
    if not pool:
        return {"action": 0, "ok": False, "detail": "今日配额已满或无可用动作"}

    action = random.choices([a for a, _ in pool], weights=[w for _, w in pool], k=1)[0]
    fn = {
        ACT_QUESTION: _act_question, ACT_ANSWER: _act_answer, ACT_COMMENT: _act_comment,
        ACT_REPLY: _act_reply, ACT_ADOPT: _act_adopt, ACT_LIKE: _act_like,
    }[action]
    try:
        return fn(db, accounts)
    except LLMDegradedError as e:
        db.rollback()
        _log(db, action, False, f"LLM 不可用，动作跳过（{e}）")
        return {"action": action, "ok": False, "detail": "LLM 不可用，跳过"}
    except BizError as e:
        db.rollback()
        _log(db, action, False, f"动作被业务规则拦截（{e.code} {e.msg}）")
        return {"action": action, "ok": False, "detail": f"被规则拦截：{e.msg}"}
    except Exception as e:
        db.rollback()
        _log(db, action, False, f"动作异常（{type(e).__name__}: {e}）")
        return {"action": action, "ok": False, "detail": f"异常：{e}"}


def _subsidize(db: Session, accounts: list[User]) -> list[dict]:
    """定期补贴：余额低于阈值的运营账号补到目标值。

    走 TASK 流水但不受日封顶约束（补贴是运营注资而非产出收益，
    否则 100/日封顶会让 300 目标永远达不到，账号池会被饿死）。
    """
    granted = []
    for u in accounts:
        balance = credit_service.get_balance(db, u.id)
        if balance >= settings.OP_SUBSIDY_THRESHOLD:
            continue
        amount = settings.OP_SUBSIDY_TARGET - balance
        actual = credit_service.grant(
            db, u.id, CreditSource.TASK, amount, note="系统运营补贴",
            apply_daily_cap=False,
        )
        _log(db, ACT_SUBSIDY, True,
             f"补贴 +{actual}（余额 {balance}→{credit_service.get_balance(db, u.id)}）", user_id=u.id)
        granted.append({"user_id": u.id, "granted": actual})
    return granted


def run_round(db: Session, manual: bool = False) -> dict:
    """执行一轮运营：补贴检查 + 随机 1-3 个动作；手动触发不受配额/时段限制。"""
    accounts = ensure_accounts(db)
    subsidies = _subsidize(db, accounts)
    n = random.randint(1, 3)
    executed = [_do_one_action(db, accounts, manual) for _ in range(n)]
    return {"executed": executed, "subsidies": subsidies, "progress": today_progress(db)}


# ---- 管理后台状态 ----


def status(db: Session) -> dict:
    accounts = ensure_accounts(db)
    account_items = []
    for u, p in zip(accounts, PERSONAS):
        balance = credit_service.get_balance(db, u.id)
        posts = len(db.execute(
            select(Post.id).where(Post.author_id == u.id, Post.deleted_at.is_(None)
        )).scalars().all())
        answers = len(db.execute(
            select(Answer.id).where(Answer.author_id == u.id, Answer.deleted_at.is_(None)
        )).scalars().all())
        account_items.append({
            "id": u.id, "nickname": u.nickname, "school": u.school, "major": u.major,
            "focus": p["focus"], "balance": balance,
            "post_count": posts, "answer_count": answers,
        })
    logs = (db.execute(select(OperationLog).order_by(OperationLog.id.desc()).limit(20))
            .scalars().all())
    recent = [{
        "id": l.id, "action": l.action, "action_text": ACTION_TEXT.get(l.action, str(l.action)),
        "ok": bool(l.ok), "detail": l.detail,
        "nickname": (db.get(User, l.user_id).nickname if l.user_id and db.get(User, l.user_id) else None),
        "created_at": l.created_at,
    } for l in logs]
    return {
        "enabled": settings.OP_ENABLED,
        "llm_ready": _llm_ready(),
        "schedule": {
            "tick_minutes": settings.OP_TICK_MINUTES,
            "hours": f"{settings.OP_HOUR_START}:00-{settings.OP_HOUR_END}:00",
            "probability": settings.OP_ACT_PROBABILITY,
        },
        "quota": {"questions": settings.OP_DAILY_QUESTIONS, "interactions": settings.OP_DAILY_INTERACTIONS},
        "today": today_progress(db),
        "accounts": account_items,
        "recent": recent,
    }


def run_scheduled_tick() -> None:
    """调度入口（app/jobs/operation.py 调用）：工作时段 + 概率闸门 + 配额由动作内部把关。"""
    now = datetime.now()
    if not (settings.OP_HOUR_START <= now.hour < settings.OP_HOUR_END):
        return
    if random.random() > settings.OP_ACT_PROBABILITY:
        return
    with SessionLocal() as db:
        run_round(db, manual=False)
