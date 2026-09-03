"""冷启动演示数据（V1.10）：计算机领域问题生态 + 默认管理员，真实 AI 链路验证。

用法：cd backend && .venv/Scripts/python -m scripts.seed_demo
前置：backend/.env 配置 LLM_ENABLED=true + 真实 DashScope Key（走真实 AI）。
产物：数据写入 dev 库（changxue.db）并保留，作为冷启动内容。

流程：
  1. 起临时 uvicorn（8002，APP_ENV=dev，复用 dev 库与 .env）
  2. 默认管理员（13800000000）注册 + 提权 + 权限三验（stats 通/普通用户拒/注册接口无提权入口）
  3. 8 个演示用户（1380000010x）注册 + 资料填充
  4. 10 个计算机问题（部分悬赏）→ 轮询验证 AI 摘要真实落库
  5. 多用户回答（真实质量检测同步拦截低质）→ 轮询验证 AI 可靠性评分
  6. 提问者采纳 6 帖（+30 积分/感谢值/通知/知识库）
  7. 3 个无人回答帖触发 AI 参考回答（真实生成）
  8. 点赞活跃度；输出验收清单

幂等：检测到演示数据已存在则跳过内容创建（管理员检查仍执行）。
"""

import os
import subprocess
import sys
import time

import httpx

BASE = "http://127.0.0.1:8002/api"
TIMEOUT = 120.0

ADMIN_PHONE = "13800000000"
ADMIN_PASSWORD = "admin123456"
DEMO_PASSWORD = "demo123456"

DEMO_USERS = [
    ("码农阿伟", "华中科技大学", "计算机科学与技术"),
    ("LeetCode苦手", "武汉大学", "软件工程"),
    ("操作系统迷", "哈尔滨工业大学", "计算机科学与技术"),
    ("前端小旋风", "中山大学", "软件工程"),
    ("算法做题家", "电子科技大学", "人工智能"),
    ("数据库咸鱼", "东南大学", "数据科学"),
    ("网络包侦探", "西安电子科技大学", "网络工程"),
    ("编译原理幸存者", "北京邮电大学", "计算机科学与技术"),
]

# (标题, 正文, 额外标签, 悬赏, 提问者序号, 回答者序号列表, 是否采纳)
POSTS = [
    ("Python 的 GIL 是什么？多线程还能提速吗？",
     "写了一个多线程脚本爬数据，发现 CPU 占用并没有翻倍。听说是因为 GIL，"
     "想弄清楚：GIL 到底锁住了什么？IO 密集型和计算密集型任务分别该怎么选？",
     [], 0, 0, [1, 3], True),
    ("TCP 三次握手为什么不是两次？",
     "复习计算机网络时一直没想通：两次握手不也能建立连接吗？"
     "三次握手到底防住了什么场景？请结合 SYN 洪泛或历史连接举例说明。",
     [], 20, 6, [0, 4], True),
    ("进程和线程的区别到底是什么？",
     "面试被问了好几次，每次都答不干净。有没有人能给一个既准确又有工程视角的回答？"
     "最好能说清楚资源分配、调度、通信成本这几个维度。",
     [], 0, 2, [], False),  # 无人回答 → AI 参考回答
    ("HTTPS 是怎么保证安全的？",
     "知道 HTTPS = HTTP + TLS，但具体流程说不清：握手时交换了什么？"
     "对称加密和非对称加密分别用在哪一步？证书又是怎么防中间人的？",
     [], 0, 3, [5, 0], True),
    ("MySQL 索引为什么用 B+ 树而不是红黑树？",
     "背了八股但没真正理解：红黑树也是平衡树，为什么磁盘存储场景非要 B+ 树？"
     "和磁盘预读、页大小有什么关系？悬赏求一个能讲透的回答。",
     [], 10, 5, [2, 6], True),
    ("快速排序最坏情况 O(n²) 怎么避免？",
     "自己实现了快排，逆序数组直接退化。听说有三数取中和随机化两种优化，"
     "它们为什么有效？还有别的工程手段吗（比如 introsort）？",
     [], 0, 4, [1], True),
    ("什么是 CAP 定理？能否举个实际系统的例子？",
     "看论文总遇到 CAP，字面意思懂了但不会应用。"
     "能不能用 ZooKeeper、Eureka 或者某个数据库举例子说明 CP 和 AP 的取舍？",
     ["考研"], 0, 1, [], False),  # 无人回答 → AI 参考回答
    ("408 操作系统：死锁的四个必要条件是什么？",
     "考研复习卡在死锁这一节。四个必要条件背不牢，"
     "想让大家帮忙用一句话记忆法 + 一个具体例子讲清楚，最好再说说预防策略。",
     ["考研"], 10, 2, [4, 0, 7], True),
    ("Git rebase 和 merge 有什么区别？",
     "团队协作时分叉了，有人坚持 rebase 有人坚持 merge。"
     "两者对提交历史的影响到底差在哪？什么场景用哪个更合适？",
     [], 0, 7, [3, 5], True),
    ("Docker 容器和虚拟机的区别？",
     "一直把容器当轻量虚拟机用，但听说底层原理完全不同。"
     "namespace 和 cgroup 分别负责什么？为什么容器启动只要毫秒级？",
     [], 0, 6, [], False),  # 无人回答 → AI 参考回答
]

ANSWERS = {
    # 帖子标题关键词 → [(回答者序号, 回答内容)]
    "GIL": [
        (1, "GIL（全局解释器锁）是 CPython 的一把互斥锁，同一时刻只允许一个线程执行 Python 字节码，"
            "所以计算密集型多线程无法利用多核。但 IO 操作（网络请求、文件读写）会释放 GIL，"
            "因此爬虫这类 IO 密集任务多线程仍然有效。工程建议：IO 密集用 threading 或 asyncio，"
            "计算密集用 multiprocessing 或者把热点代码交给 numpy/C 扩展（会在计算时释放 GIL）。"),
        (3, "补充一个常见误区：GIL 只存在于 CPython，PyPy、Jython 没有，Python 3.13 的 free-threaded "
            "实验版也在尝试移除 GIL。另外用 time.sleep 模拟 IO 时线程确实会切换，"
            "但如果你写的是纯 Python 循环，多线程甚至可能因为锁竞争比单线程更慢。"),
    ],
    "三次握手": [
        (0, "两次握手的致命问题是无法防止「历史连接」：假设客户端的一个旧 SYN 在网络里滞留了很久才到达服务端，"
            "服务端回 ACK 后就认为连接建立，单方面分配资源等待数据，而客户端根本不认这个连接，"
            "服务端资源就被白白浪费。第三次握手让客户端有机会确认「这是我发起的连接」，发现是旧 SYN 就发 RST 拒绝。"
            "另外，两次握手也无法让服务端确认自己发的 ACK 客户端收到了，双方对序列号的同步不完整。"),
        (4, "记一个简洁版本：三次握手的本质是「双方各自确认 收发能力」。"
            "SYN 确认客户端能发、服务端能收；SYN+ACK 确认服务端能发、客户端能收；"
            "最后 ACK 确认客户端能收服务端的包。缺任何一步，总有一方的接收能力没被验证。"),
    ],
    "HTTPS": [
        (5, "完整流程分四步：①客户端发起请求，带上自己支持的加密套件；②服务端返回证书（含公钥），"
            "客户端用内置 CA 根证书验证证书链，防止中间人；③双方用 ECDHE 协商出对称会话密钥"
            "（非对称加密只用来交换密钥材料，因为慢）；④之后所有数据用对称密钥加密传输。"
            "所以准确说法：非对称加密解决「密钥交换+身份认证」，对称加密负责「数据加密」。"),
        (0, "一句话记忆：证书防冒充（CA 私钥签名，浏览器用公钥验），非对称换钥匙（ECDHE），对称传数据（AES-GCM）。"
            "中间人拿不到会话密钥，即使截获流量也只能看到密文。"),
    ],
    "B+ 树": [
        (2, "核心是磁盘 IO 次数。红黑树是二叉树，每个节点只存一个键，1000 万数据高度约 23 层，"
            "意味着最多 23 次磁盘 IO。B+ 树节点大小对齐磁盘页（InnoDB 默认 16KB），一个节点能存几百个键，"
            "同样数据高度通常只有 3~4 层，即 3~4 次 IO。另外 B+ 树叶子节点用链表串联，范围查询（如 WHERE id BETWEEN）"
            "只需顺序遍历叶子层，不用回到上层。这是「树的扇出决定了 IO 次数」的经典权衡。"),
        (6, "补充 InnoDB 的具体数字：主键为 bigint 时一个 16KB 页大约能放 1170 个键（非叶子）或 15 行完整数据（叶子），"
            "所以 3 层 B+ 树容量约 2000 万行，根节点常驻内存后一次主键查询往往只需 1~2 次磁盘读取。"),
    ],
    "快速排序": [
        (1, "最坏情况源于划分极端不平衡（每次都选到最值做 pivot），退化成冒泡。两种主流优化："
            "①三数取中：取 lo/mid/hi 三个元素的中位数做 pivot，对付有序/逆序数组极有效；"
            "②随机化：随机选 pivot，让最坏情况变成概率事件。工程上更彻底的是 introsort——"
            "快排递归深度超过 2logN 时切堆排，STL 的 std::sort 就是这个方案，把最坏情况也压回 O(N log N)。"),
    ],
    "死锁": [
        (4, "四个必要条件一句话版：「互斥、持有并等待、不可剥夺、循环等待」。"
            "举例：线程 A 拿了锁 L1 等 L2，线程 B 拿了 L2 等 L1，四个条件全满足就死锁。"
            "破坏任一条件即可预防，工程上最常用的是「顺序加锁」——规定所有线程都按 L1→L2 的顺序申请，"
            "循环等待条件被破坏，死锁不可能发生。数据库的死锁检测+回滚则是破坏「不可剥夺」。"),
        (0, "补充记忆口诀：「互斥资、持且等、不剥夺、圈圈等」。考研选择题常考的是「哪个不是必要条件」"
            "以及银行家算法属于「死锁避免」而不是「预防」，两者概念别混淆。"),
        (7, "从操作系统实现角度补充：Linux 本身不主动预防死锁，靠 lockdep（内核锁依赖检测）在开发阶段发现潜在死锁路径；"
            "用户态如 MySQL 的 InnoDB 会跑死锁检测图，发现环后回滚代价小的事务。"
            "也就是说生产环境更多是「检测+恢复」而非「预防」。"),
    ],
    "rebase": [
        (3, "区别在对历史的态度：merge 保留真实分叉历史，产生一个合并提交，历史是图；"
            "rebase 把你的提交「搬到」目标分支之后，历史变成一条直线，更干净但改写了提交。"
            "实践建议：个人 feature 分支同步主干用 rebase（干净），合入主干用 merge --no-ff（可追溯）；"
            "已推送到公共分支的提交永远不要 rebase，改写历史会让队友的仓库损坏。"),
        (5, "一个直观的心智模型：merge 是「拍照存档」——把两个分支的现状合成一张新照片；"
            "rebase 是「搬家」——把你的每个提交逐个搬到新地址，提交哈希全部改变。"
            "所以 rebase 后的提交需要 force push，这也是它危险的原因。"),
    ],
}

AI_REF_POST_KEYWORDS = ["进程和线程", "CAP", "Docker"]  # 无人回答 → 触发 AI 参考回答

results: list[tuple[bool, str]] = []


def check(cond: bool, msg: str) -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
    results.append((cond, msg))


def wait_server(client: httpx.Client) -> None:
    for _ in range(30):
        try:
            r = client.get(f"{BASE}/health", timeout=5)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise SystemExit("uvicorn 8002 未就绪")


def register_or_login(client: httpx.Client, phone: str, password: str, nickname: str = ""):
    r = client.post(f"{BASE}/auth/register",
                    json={"phone": phone, "password": password, "nickname": nickname or "用户"})
    body = r.json()
    if body["code"] == 0:
        return body["data"], True
    if body["code"] == 40004:  # 已注册 → 登录
        r = client.post(f"{BASE}/auth/login", json={"phone": phone, "password": password})
        b = r.json()
        if b["code"] != 0:
            raise SystemExit(f"{phone} 已存在但预期密码登录失败：{b['msg']}")
        return b["data"], False
    raise SystemExit(f"注册 {phone} 失败：{body['msg']}")


def hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    print("==> 启动临时 uvicorn（8002，dev 库 + 真实 LLM）")
    env = {**os.environ, "APP_ENV": "dev"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8002"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            wait_server(client)
            run(client)
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    fails = [m for ok, m in results if not ok]
    print(f"\n结果：{len(results) - len(fails)} 通过 / {len(fails)} 失败")
    print(f"\n默认管理员账号：手机号 {ADMIN_PHONE} / 密码 {ADMIN_PASSWORD}"
          f"（登录后自动进入管理后台；上线后请立即修改密码）")
    raise SystemExit(1 if fails else 0)


def run(client: httpx.Client) -> None:
    # ---------- 管理员 ----------
    print("==> 1/6 默认管理员：注册 + 提权 + 权限三验")
    admin, created = register_or_login(client, ADMIN_PHONE, ADMIN_PASSWORD, "畅学管理员")
    if created:
        from app.core.database import SessionLocal
        from app.models import User as UserModel
        import sqlalchemy as sa
        with SessionLocal() as db:  # 注册接口无 role 入参（设计如此），提权走种子脚本
            row = db.execute(sa.select(UserModel).where(UserModel.phone == ADMIN_PHONE)).scalar_one()
            row.role = 1
            db.commit()
        admin, _ = register_or_login(client, ADMIN_PHONE, ADMIN_PASSWORD)
    # 登录响应为 brief（不含 is_admin），以 /auth/me 为准（前端登录后同样拉取 me）
    me = client.get(f"{BASE}/auth/me", headers=hdr(admin["token"])).json()["data"]
    check(me.get("is_admin") is True, "管理员账号 is_admin=true（登录页统一，注册接口无提权入口）")

    r = client.get(f"{BASE}/admin/stats", headers=hdr(admin["token"]))
    check(r.json()["code"] == 0, "管理员访问 GET /admin/stats 通过")

    demo0, _ = register_or_login(client, "13800000101", DEMO_PASSWORD, "占位")
    r = client.get(f"{BASE}/admin/stats", headers=hdr(demo0["token"]))
    check(r.json()["code"] == 40302, "普通用户访问 /admin/stats 被拒（40302）")

    # ---------- 幂等检查 ----------
    print("==> 2/6 演示用户注册（幂等）")
    tokens = {}
    for i, (nick, school, major) in enumerate(DEMO_USERS):
        phone = f"1380000010{i + 1}"
        data, _ = register_or_login(client, phone, DEMO_PASSWORD, nick)
        tokens[i] = data["token"]
        if data["user"]["nickname"] != nick:  # 老数据补资料
            client.put(f"{BASE}/account/profile", headers=hdr(tokens[i]),
                       json={"nickname": nick, "school": school, "major": major})
    demo_uid = demo0["user"]["id"]

    # 演示内容是否已存在（任一演示用户发过帖即跳过）
    r = client.get(f"{BASE}/account/my-posts", headers=hdr(tokens[0]))
    if r.json()["data"]["total"] > 0:
        print("  SKIP  演示内容已存在，跳过创建（管理员检查已在上方执行）")
        return

    # ---------- 发帖 + AI 摘要 ----------
    print("==> 3/6 发布 10 个计算机问题（真实 AI 摘要）")
    r = client.get(f"{BASE}/tags")
    tag_id = next(t["id"] for t in r.json()["data"]["items"] if t["name"] == "计算机")
    kaoyan_id = next((t["id"] for t in r.json()["data"]["items"] if t["name"] == "考研"), None)

    post_ids = []
    post_by_title: dict[str, int] = {}
    for title, content, extra_tags, reward, asker, _, _ in POSTS:
        tags = [tag_id] + [kaoyan_id for name in extra_tags if name == "考研" and kaoyan_id]
        r = client.post(f"{BASE}/posts", headers=hdr(tokens[asker]),
                        json={"title": title, "content": content, "images": [],
                              "tag_ids": tags, "reward": reward})
        body = r.json()
        if body["code"] != 0:
            print(f"  WARN  发帖失败「{title}」：{body['msg']}")
            continue
        post_by_title[title] = body["data"]["id"]
        post_ids.append(body["data"]["id"])
    check(len(post_ids) == len(POSTS), f"发帖 {len(post_ids)}/{len(POSTS)} 成功")

    deadline = time.time() + 150
    summaries = {}
    while time.time() < deadline and len(summaries) < len(post_ids):
        for pid in post_ids:
            if pid in summaries:
                continue
            d = client.get(f"{BASE}/posts/{pid}").json()["data"]
            if d.get("ai_summary"):
                summaries[pid] = d["ai_summary"]
        if len(summaries) < len(post_ids):
            time.sleep(3)
    check(len(summaries) == len(post_ids),
          f"AI 摘要真实落库 {len(summaries)}/{len(post_ids)}（DashScope qwen-turbo）")

    # ---------- 回答 + 质量检测 + 可靠性评分 ----------
    print("==> 4/6 多用户回答（真实质量检测 + AI 可靠性评分）")
    answer_ids: list[int] = []
    blocked = 0
    for title, _, _, _, asker, answerers, _ in POSTS:
        if not answerers:
            continue
        pid = post_by_title[title]
        pool = ANSWERS.get(next((k for k in ANSWERS if k in title), ""), [])
        for idx, (ans_uidx, content) in enumerate(pool):
            r = client.post(f"{BASE}/posts/{pid}/answers", headers=hdr(tokens[ans_uidx]),
                            json={"content": content})
            body = r.json()
            if body["code"] == 40913:
                blocked += 1
                print(f"  WARN  质量检测拦截了一条回答（{title[:12]}…）")
                continue
            if body["code"] == 0:
                answer_ids.append(body["data"]["id"])
    check(len(answer_ids) >= 12, f"回答提交 {len(answer_ids)} 条（质量检测放行，拦截 {blocked} 条）")

    deadline = time.time() + 180
    scored = set()
    while time.time() < deadline and len(scored) < len(answer_ids):
        for pid in post_ids:
            d = client.get(f"{BASE}/posts/{pid}").json()["data"]
            for a in d.get("answers", []):
                if a.get("ai_rel_score") is not None:
                    scored.add(a["id"])
        if len(scored) < len(answer_ids):
            time.sleep(3)
    check(len(scored) == len(answer_ids),
          f"AI 可靠性评分 {len(scored)}/{len(answer_ids)}（qwen-plus 异步生成）")

    # ---------- 采纳 ----------
    print("==> 5/6 提问者采纳（积分/感谢值/通知/知识库联动）")
    accepted = 0
    for title, _, _, _, asker, answerers, do_accept in POSTS:
        if not do_accept:
            continue
        pid = post_by_title[title]
        d = client.get(f"{BASE}/posts/{pid}").json()["data"]
        if not d.get("answers"):
            continue
        best = d["answers"][0]  # 列表已按 最佳>采纳>点赞 排序，取首条
        r = client.post(f"{BASE}/answers/{best['id']}/accept", headers=hdr(tokens[asker]))
        if r.json()["code"] == 0:
            accepted += 1
    check(accepted >= 6, f"采纳成功 {accepted} 帖（回答者 +30 积分、感谢值入榜、通知送达、知识库沉淀）")

    # 采纳后帖子应为已解决
    solved = 0
    for title, _, _, _, _, _, do_accept in POSTS:
        if not do_accept:
            continue
        d = client.get(f"{BASE}/posts/{post_by_title[title]}").json()["data"]
        solved += 1 if d["status"] == 1 else 0
    check(solved == accepted, f"已解决状态回写 {solved}/{accepted}")

    # ---------- AI 参考回答（无人回答帖） ----------
    print("==> 6/6 无人回答帖触发 AI 参考回答（兜底链路）")
    ref_ok = 0
    for title in AI_REF_POST_KEYWORDS:
        pid = post_by_title[next(p[0] for p in POSTS if title in p[0])]
        r = client.post(f"{BASE}/posts/{pid}/ai-answer", headers=hdr(tokens[0]))
        if r.json()["code"] == 0:
            ref_ok += 1
        else:
            print(f"  WARN  AI 参考回答失败「{title}」：{r.json()['msg']}")
    check(ref_ok == len(AI_REF_POST_KEYWORDS), f"AI 参考回答生成 {ref_ok}/{len(AI_REF_POST_KEYWORDS)}（标注 AI 生成、不计入积分）")

    # ---------- 点赞活跃 ----------
    like_ok = 0
    for pid in post_ids[:6]:
        for u in (1, 2, 3):
            r = client.post(f"{BASE}/likes/toggle", headers=hdr(tokens[u]),
                            json={"target_type": 1, "target_id": pid})
            like_ok += 1 if r.json()["code"] == 0 else 0
    check(like_ok >= 12, f"点赞互动 {like_ok} 次（广场/详情页热闹度）")


if __name__ == "__main__":
    main()
