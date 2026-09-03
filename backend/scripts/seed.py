"""种子数据脚本：12 个一级学科标签（PRD §7.3.3）+ 商城示例商品（V1.8）。

用法：python -m scripts.seed [--drop]
幂等：存在同名标签/商品则跳过。
"""

import sys

from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.models import MallProduct, Tag

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

# 商城示例商品：虚拟权益（type=1，不限量）+ 实物文创（type=2，限量）
SEED_PRODUCTS = [
    ("学霸头衔·7天", "个人主页展示「学霸」专属头衔 7 天", 50, -1, None, 1),
    ("限定徽章·问答之星", "个人主页永久展示「问答之星」限定徽章", 120, -1, None, 1),
    ("畅学贴纸包", "畅学社区卡通形象贴纸一包（约 20 枚）", 200, 100, None, 2),
    ("畅学笔记本", "A5 精装笔记本，封面社区吉祥物印花", 500, 50, None, 2),
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

        existing_p = {name for (name,) in db.execute(select(MallProduct.name))}
        added_p = 0
        for name, desc, price, stock, image, ptype in SEED_PRODUCTS:
            if name in existing_p:
                continue
            db.add(
                MallProduct(
                    name=name, description=desc, price=price, stock=stock,
                    image_url=image, type=ptype, enabled=1,
                )
            )
            added_p += 1
        db.commit()
    print(f"seed 完成：新增标签 {added} 个（已存在 {len(SEED_TAGS) - added}），"
          f"新增商品 {added_p} 个（已存在 {len(SEED_PRODUCTS) - added_p}）")


if __name__ == "__main__":
    # --drop 参数：清空 tag 表后重新插入（开发调试用；不动商城表）
    if "--drop" in sys.argv:
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            for t in db.execute(select(Tag)).scalars():
                db.delete(t)
            db.commit()
        print("tag 表已清空")
    run()
