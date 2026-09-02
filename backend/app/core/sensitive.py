"""敏感词 DFA 过滤器（技术细节文档 §7.3）。

词库文件：app/core/sensitive_words.txt（每行一词，# 注释）。
匹配规则：忽略首尾空白与全角/半角差异不做转换（MVP 简化，全词精确匹配按字符流）。
首次调用时构建 DFA 并缓存。
"""

from pathlib import Path

_WORD_FILE = Path(__file__).parent / "sensitive_words.txt"
_END = "\x00"  # 词尾哨兵

_trie: dict | None = None


def _build_trie() -> dict:
    trie: dict = {}
    if not _WORD_FILE.exists():
        return trie
    for line in _WORD_FILE.read_text(encoding="utf-8").splitlines():
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        node = trie
        for ch in word:
            node = node.setdefault(ch, {})
        node[_END] = True
    return trie


def _get_trie() -> dict:
    global _trie
    if _trie is None:
        _trie = _build_trie()
    return _trie


def contains_sensitive(text: str) -> bool:
    """检测文本是否含敏感词（任意位置命中即 True）。空文本恒 False。"""
    if not text:
        return False
    trie = _get_trie()
    if not trie:
        return False
    for i, ch in enumerate(text):
        node = trie.get(ch)
        if node is None:
            continue
        # 沿当前起点逐字符推进
        cursor = node
        j = i + 1
        while cursor is not None:
            if _END in cursor:
                return True
            if j >= len(text):
                break
            cursor = cursor.get(text[j])
            j += 1
    return False


def find_sensitive(text: str) -> str | None:
    """返回首个命中的敏感词（测试与提示用），未命中返回 None。"""
    if not text:
        return None
    trie = _get_trie()
    for i, ch in enumerate(text):
        if ch not in trie:
            continue
        cursor = trie[ch]
        j = i + 1
        while cursor is not None:
            if _END in cursor:
                return text[i:j]
            if j >= len(text):
                break
            cursor = cursor.get(text[j])
            j += 1
    return None


def reload_words() -> int:
    """强制重建 DFA（词库文件热更新后调用），返回词数。"""
    global _trie
    _trie = None
    trie = _get_trie()

    def count(node: dict) -> int:
        n = 1 if _END in node else 0
        for v in node.values():
            if isinstance(v, dict):
                n += count(v)
        return n

    return count(trie)
