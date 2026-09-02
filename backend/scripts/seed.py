"""种子数据脚本：12 个一级学科标签（PRD §7.3.3 初始化标签集）。

用法：python -m scripts.seed [--drop]
幂等：存在同名标签则跳过。
"""

import sys

from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.models import Tag

# 12 个一级学科标签（参考教育部学科门类 + 热门学习话题）
SEED_TAGS = [
    "计算机",
    "数学",
    "物理学",
    "化学",
    "生物学",
    "经济学",
    "法学",
    "外语",
    "文学",
    "医学",
    "工学",
    "考研",
]


def run() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        existing = {name for (name,) in db.execute(select(Tag.name))}
        added = 0
        for i, name in enumerate(SEED_TAGS):
            if name in existing:
                continue
            db.add(Tag(name=name, sort=i, enabled=1))
            added += 1
        db.commit()
    print(f"seed 完成：新增 {added} 个标签，已存在 {len(SEED_TAGS) - added} 个")


if __name__ == "__main__":
    # --drop 参数：清空 tag 表后重新插入（开发调试用）
    if "--drop" in sys.argv:
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            for t in db.execute(select(Tag)).scalars():
                db.delete(t)
            db.commit()
        print("tag 表已清空")
    run()
