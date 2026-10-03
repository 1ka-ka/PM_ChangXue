"""存量帖子语义向量回填（V1.19）：分批调用网关 embeddings 接口，逐批落库。

幂等：只处理 embedding 为 NULL 的未删帖；单批失败跳过（下次运行重试）。
用法：python -m scripts.backfill_embeddings
"""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.gateway.client import LLMDegradedError, gateway
from app.models import Post
from app.modules.post.service import embed_text

BATCH = 10  # DashScope text-embedding-v3 单批上限 10 条


def run() -> None:
    with SessionLocal() as db:
        posts = (
            db.execute(
                select(Post).where(Post.deleted_at.is_(None), Post.embedding.is_(None))
            )
            .scalars()
            .all()
        )
        total = len(posts)
        done = failed = 0
        print(f"待回填 {total} 帖")
        for i in range(0, total, BATCH):
            batch = posts[i : i + BATCH]
            try:
                vecs = gateway.embed([embed_text(p.title, p.content) for p in batch])
            except LLMDegradedError as e:
                failed += len(batch)
                print(f"批次 {i // BATCH + 1} 失败（跳过 {len(batch)} 帖）: {e}")
                continue
            for p, v in zip(batch, vecs):
                p.embedding = v
                done += 1
            db.commit()
            print(f"进度 {min(i + BATCH, total)}/{total}")
        print(f"回填完成：成功 {done}，失败 {failed}（失败帖下次运行重试）")


if __name__ == "__main__":
    run()
