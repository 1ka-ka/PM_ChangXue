"""S12 TC-loop 端到端自动化回归（交付文档 §3.S12 任务①）。

真实链路：uvicorn 子进程 + SQLite 文件库 + httpx，走通 MVP 核心闭环：
注册 → 每日登录 → 发帖（悬赏扣分）→ 广场/详情 → 回答 → 评论 → 点赞收藏
→ 采纳（+30 积分+感谢值+通知）→ 通知已读 → 榜单结算 → 搜索（知识库）
→ 个人主页/收藏列表/积分明细 → 举报 → 管理后台处置（级联软删）→ 看板/日志。

用法（backend 目录）：.venv\\Scripts\\python.exe scripts\\smoke_e2e.py
使用独立 smoke_e2e.db，不影响开发库 changxue.db；结束自动清理。
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
DB_FILE = BASE_DIR / "smoke_e2e.db"
PORT = 8312
BASE = f"http://127.0.0.1:{PORT}/api"

# 独立文件库（必须在导入 app 前设置，供榜单结算直调使用）
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"

_phone = iter(range(6_000_000, 7_000_000))
_passed: list[str] = []
_failed: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        _passed.append(name)
        print(f"  PASS  {name}")
    else:
        _failed.append(f"{name} {detail}")
        print(f"  FAIL  {name}  {detail}")


def register(client: httpx.Client, nickname: str) -> dict:
    r = client.post(
        "/auth/register",
        json={"phone": f"139{next(_phone):08d}", "password": "password123", "nickname": nickname},
    )
    body = r.json()
    assert body["code"] == 0, body
    return {"Authorization": f"Bearer {body['data']['token']}"}


def main() -> int:
    if DB_FILE.exists():
        DB_FILE.unlink()

    env = {**os.environ, "DATABASE_URL": f"sqlite:///{DB_FILE}"}
    server = subprocess.Popen(
        [str(BASE_DIR / ".venv" / "Scripts" / "python.exe"), "-m", "uvicorn",
         "app.main:app", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(BASE_DIR), env=env,
    )
    try:
        with httpx.Client(base_url=BASE, timeout=10) as c:
            # 等服务就绪
            for _ in range(50):
                try:
                    if c.get("/health").json()["code"] == 0:
                        break
                except Exception:
                    time.sleep(0.2)
            else:
                print("服务启动失败")
                return 1
            check("健康检查", True)

            # ---- 账号 ----
            h_q = register(c, "提问者")   # 后期提升为管理员
            h_a = register(c, "回答者")
            h_r = register(c, "路人甲")

            me = c.get("/auth/me", headers=h_a).json()["data"]
            check("注册开户赠 50 积分", me["credit_balance"] == 50, f"balance={me['credit_balance']}")

            r = c.post("/credit/daily-login", headers=h_a).json()
            check("每日登录 +5", r["code"] == 0 and r["data"]["granted"] == 5, f"resp={r}")

            tags = c.get("/tags").json()["data"]["items"]
            check("标签列表（seed 12）", len(tags) >= 12, f"n={len(tags)}")
            tag_id = tags[0]["id"]

            # ---- 发帖（悬赏 10）----
            r = c.post("/posts", headers=h_q, json={
                "title": "FastAPI 依赖注入最佳实践？",
                "content": "Depends 与 yield 生命周期管理，采纳送分。",
                "tag_ids": [tag_id], "reward": 10,
            }).json()
            check("发帖成功", r["code"] == 0)
            pid = r["data"]["id"]
            bal = c.get("/credit/balance", headers=h_q).json()["data"]["balance"]
            check("悬赏同事务扣 10（50-10=40）", bal == 40, f"balance={bal}")

            r = c.get("/feed", params={"tab": "latest"}).json()
            check("广场 latest 含新帖", any(p["id"] == pid for p in r["data"]["items"]))

            detail = c.get(f"/posts/{pid}", headers=h_r).json()["data"]
            check("帖子详情（view 递增）", detail["view_count"] >= 1)

            # ---- 回答 / 评论 / 点赞 / 收藏 ----
            r = c.post(f"/posts/{pid}/answers", headers=h_a,
                       json={"content": "yield 依赖管理生命周期，退出时清理……"}).json()
            check("回答成功", r["code"] == 0)
            aid = r["data"]["id"]

            r = c.post("/comments", headers=h_r, json={
                "target_type": 2, "target_id": aid, "content": "学到了，感谢！"}).json()
            check("回答评论", r["code"] == 0)

            r = c.post("/likes/toggle", headers=h_r,
                       json={"target_type": 2, "target_id": aid}).json()["data"]
            check("点赞回答", r["liked"] is True and r["like_count"] == 1)

            r = c.post("/favorites/toggle", headers=h_r,
                       json={"target_type": 1, "target_id": pid}).json()["data"]
            check("收藏帖子", r["favorited"] is True)

            # ---- 采纳（积分+感谢值+通知+知识库）----
            r = c.post(f"/answers/{aid}/accept", headers=h_q).json()
            check("采纳成功", r["code"] == 0)
            r = c.post(f"/answers/{aid}/set-best", headers=h_q).json()
            check("设为最佳", r["code"] == 0)

            detail = c.get(f"/posts/{pid}", headers=h_q).json()["data"]
            ans = next(a for a in detail["answers"] if a["id"] == aid)
            check("帖子置已解决+最佳标记", detail["status"] == 1 and ans["is_best"] is True)

            bal = c.get("/credit/balance", headers=h_a).json()["data"]["balance"]
            check("回答者 +30（50+5+30=85）", bal == 85, f"balance={bal}")

            # ---- 通知 ----
            r = c.get("/notifications", headers=h_a).json()["data"]
            types = [n["type"] for n in r["items"]]
            check("被采纳通知（含 post_id 直达）",
                  4 in types and any(n["post_id"] == pid for n in r["items"]))
            r = c.get("/notifications/unread-count", headers=h_a).json()["data"]
            check("未读计数 ≥1", r["count"] >= 1)
            c.post("/notifications/read-all", headers=h_a)
            r = c.get("/notifications/unread-count", headers=h_a).json()["data"]
            check("全部已读", r["count"] == 0)

            # ---- 榜单（直调结算模拟周一 job，验证快照链路）----
            from app.core.database import SessionLocal
            from app.modules.rank import service as rank_service
            with SessionLocal() as db:
                rank_service.settle(db, 1, rank_service.week_key(__import__("datetime").datetime.now()))
            r = c.get("/ranks", params={"period": "week"}).json()["data"]
            check("周榜含回答者（感谢值 30）",
                  any(it["user"]["id"] == me["id"] and it["value"] == 30 for it in r["items"]))

            # ---- 搜索（采纳后入知识库）----
            r = c.get("/search", params={"q": "依赖注入"}).json()["data"]
            check("搜索命中知识库", r["source"] == "kb" and any(p["id"] == pid for p in r["items"]),
                  f"source={r['source']}")

            # ---- 个人主页 / 收藏 / 明细 ----
            r = c.get(f"/account/users/{me['id']}", headers=h_a).json()["data"]
            check("个人主页（本人余额可见）", r["credit_balance"] == 85)
            r = c.get("/favorites", headers=h_r).json()["data"]
            check("收藏列表（软删前 1 条）", r["total"] == 1)
            r = c.get("/credit/logs", headers=h_a).json()["data"]
            texts = [l["source_text"] for l in r["items"]]
            check("积分明细（含采纳/登录）",
                  any("采纳" in t for t in texts) and any("登录" in t for t in texts), f"texts={texts}")

            # ---- 举报 → 管理后台处置 ----
            r = c.post("/reports", headers=h_r, json={
                "target_type": 2, "target_id": aid, "reason": 1, "detail": "测试举报"}).json()
            check("举报提交", r["code"] == 0)

            # 提问者提升为管理员（DB 直改 role，get_current_user 每请求读库即时生效）
            from sqlalchemy import update
            from app.models import User
            with SessionLocal() as db:
                db.execute(update(User).where(User.nickname == "提问者").values(role=1))
                db.commit()

            r = c.get("/admin/reports", params={"status": 0}, headers=h_q).json()["data"]
            check("举报队列（待处理 1）", r["total"] == 1)
            rid = r["items"][0]["id"]

            r = c.post(f"/admin/reports/{rid}/action", headers=h_q,
                       json={"action": "delete", "reason": "违规内容，删除"}).json()
            check("处置：删除内容", r["code"] == 0)

            detail = c.get(f"/posts/{pid}", headers=h_r).json()["data"]
            check("级联软删后回答不可见", all(a["id"] != aid for a in detail["answers"]))

            r = c.get("/admin/stats", headers=h_q).json()["data"]
            check("看板（待处理举报归零）", r["pending_reports"] == 0)
            r = c.get("/admin/logs", headers=h_q).json()["data"]
            check("操作日志留痕", r["total"] >= 1)

            r = c.post("/admin/tags", headers=h_q, json={"name": "冒烟测试标签", "sort": 99}).json()
            check("后台新增标签", r["code"] == 0)
            r = c.put(f"/admin/tags/{r['data']['id']}", headers=h_q, json={"enabled": 0}).json()
            check("后台停用标签", r["code"] == 0 and r["data"]["enabled"] is False)

            # ---- 埋点（P0 事件上报）----
            r = c.post("/events/batch", headers=h_r, json={
                "events": [{"name": "search_degrade", "props": {"q": "冒烟", "plaza_total": 0}}]})
            check("埋点批量上报 204", r.status_code == 204, f"status={r.status_code}")

    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        # Windows：先释放本进程引擎连接，再带重试删除文件
        try:
            from app.core.database import engine
            engine.dispose()
        except Exception:
            pass
        for _ in range(10):
            try:
                if DB_FILE.exists():
                    DB_FILE.unlink()
                break
            except PermissionError:
                time.sleep(0.5)

    print(f"\n结果：{len(_passed)} 通过 / {len(_failed)} 失败")
    if _failed:
        for f in _failed:
            print(f"  FAIL  {f}")
        return 1
    print("TC-loop 端到端回归全部通过（MVP 验收）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
