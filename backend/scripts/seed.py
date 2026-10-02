"""种子数据脚本：12 个一级学科标签（PRD §7.3.3）+ 商城示例商品（V1.8）。
V1.15 个性化资源：头衔/徽章/头像框/气泡/特效 首批上架（category 1-5）。

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

# 商城商品：(name, desc, price, stock, image_url, type, category, payload)
# category：0无分类 1头衔 2徽章 3头像框 4气泡 5特效（6字体 7皮肤 8宠物 V1.16/17 上架）
SEED_PRODUCTS = [
    # 原示例（存量兼容）
    ("学霸头衔·7天", "全站昵称旁展示「学霸」专属头衔", 50, -1, None, 1, 1, "学霸"),
    ("限定徽章·问答之星", "全站昵称旁展示「问答之星」限定徽章", 120, -1, None, 1, 2, "⭐"),
    ("畅学贴纸包", "畅学社区卡通形象贴纸一包（约 20 枚）", 200, 100, None, 2, 0, ""),
    ("畅学笔记本", "A5 精装笔记本，封面社区吉祥物印花", 500, 50, None, 2, 0, ""),
    # V1.15 头衔×4
    ("头衔·问答新星", "全站昵称旁展示「问答新星」头衔", 80, -1, None, 1, 1, "问答新星"),
    ("头衔·热心大佬", "全站昵称旁展示「热心大佬」头衔", 200, -1, None, 1, 1, "热心大佬"),
    ("头衔·扫地僧", "全站昵称旁展示「扫地僧」头衔", 350, -1, None, 1, 1, "扫地僧"),
    ("头衔·卷王", "全站昵称旁展示「卷王」头衔", 500, -1, None, 1, 1, "卷王"),
    # V1.15 徽章×5
    ("徽章·采纳高手", "全站昵称旁展示「🎯」徽章", 150, -1, None, 1, 2, "🎯"),
    ("徽章·连续答主", "全站昵称旁展示「🔥」徽章", 180, -1, None, 1, 2, "🔥"),
    ("徽章·学识渊博", "全站昵称旁展示「💎」徽章", 220, -1, None, 1, 2, "💎"),
    ("徽章·速答达人", "全站昵称旁展示「🚀」徽章", 160, -1, None, 1, 2, "🚀"),
    ("徽章·年度榜样", "全站昵称旁展示「🏆」徽章", 300, -1, None, 1, 2, "🏆"),
    # V1.15 头像框×4
    ("头像框·金色光辉", "金色渐变头像框", 150, -1, None, 1, 3, "gold"),
    ("头像框·银色月华", "银色渐变头像框", 100, -1, None, 1, 3, "silver"),
    ("头像框·蔚蓝深海", "蓝色渐变头像框", 100, -1, None, 1, 3, "blue"),
    ("头像框·玫瑰星云", "玫红渐变头像框", 120, -1, None, 1, 3, "rose"),
    # V1.15 气泡×4（私信聊天）
    ("气泡·薄荷清风", "私信绿色系气泡", 80, -1, None, 1, 4, "mint"),
    ("气泡·蜜桃乌龙", "私信粉橘系气泡", 80, -1, None, 1, 4, "peach"),
    ("气泡·星夜紫", "私信紫色系气泡", 100, -1, None, 1, 4, "star"),
    ("气泡·像素霓虹", "私信蓝紫渐变气泡", 150, -1, None, 1, 4, "neo"),
    # V1.15 特效×3（昵称特效）
    ("特效·柔光", "昵称柔光晕染特效", 200, -1, None, 1, 5, "glow"),
    ("特效·闪耀", "昵称星光闪耀特效", 350, -1, None, 1, 5, "shine"),
    ("特效·烈焰", "昵称烈焰燃烧特效", 500, -1, None, 1, 5, "flame"),
    # V1.16 字体×4（帖子正文/回答/私信正文以该字体展示）
    ("字体·楷体风骨", "佩戴后你的帖子与私信内容以楷体展示", 120, -1, None, 1, 6, "kai"),
    ("字体·仿宋雅韵", "佩戴后你的帖子与私信内容以仿宋展示", 120, -1, None, 1, 6, "fang"),
    ("字体·黑体力量", "佩戴后你的帖子与私信内容以黑体展示", 150, -1, None, 1, 6, "hei"),
    ("字体·宋体古风", "佩戴后你的帖子与私信内容以宋体展示", 100, -1, None, 1, 6, "song"),
    # V1.16 皮肤×3（页面主题包，仅本人可见）
    ("皮肤·樱花粉", "全站主题换装：樱花粉色调（仅本人可见）", 200, -1, None, 1, 7, "sakura"),
    ("皮肤·薄荷绿", "全站主题换装：薄荷青色调（仅本人可见）", 200, -1, None, 1, 7, "mint"),
    ("皮肤·落日橙", "全站主题换装：落日暖橙色调（仅本人可见）", 250, -1, None, 1, 7, "sunset"),
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
        for name, desc, price, stock, image, ptype, category, payload in SEED_PRODUCTS:
            if name in existing_p:
                continue
            db.add(
                MallProduct(
                    name=name, description=desc, price=price, stock=stock,
                    image_url=image, type=ptype, category=category, payload=payload, enabled=1,
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
