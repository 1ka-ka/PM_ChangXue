"""S1 测试：敏感词 DFA 过滤器。"""

from app.core import sensitive


def test_clean_text_passes():
    assert not sensitive.contains_sensitive("这是一段正常的学习讨论内容")
    assert sensitive.find_sensitive("高数极限怎么求") is None


def test_sensitive_hit():
    assert sensitive.contains_sensitive("前面正常 测试敏感词 后面正常")
    assert sensitive.find_sensitive("含测试敏感词的文本") == "测试敏感词"


def test_prefix_not_false_positive():
    """词库有“测试敏感词”，仅含前缀“测试敏”不应命中。"""
    assert not sensitive.contains_sensitive("测试敏 感 词 分开的")


def test_empty_and_none():
    assert not sensitive.contains_sensitive("")
    assert sensitive.find_sensitive("") is None


def test_multiple_hits_returns_first():
    assert sensitive.find_sensitive("违规占位词和测试敏感词") == "违规占位词"


def test_word_count():
    n = sensitive.reload_words()
    assert n == 2  # 占位词库 2 词
