"""LLM 网关客户端（V1.2：五场景统一调用入口，首发接入 summary）。

设计（ARCH §6 / contracts.py 注释）：
- invoke(scene, payload)：契约输入校验 → 组装 prompt → chat/completions → 解析 JSON → 契约输出校验
- 超时 LLM_TIMEOUT_SECONDS、失败重试 LLM_MAX_RETRIES 次；最终失败抛 LLMDegradedError，
  调用方必须捕获并降级（如摘要回退正文截断），绝不拖垮主流程
- LLM_ENABLED=False 时直接降级（测试环境/未配置 Key）
- 所有场景要求模型仅输出一个 JSON 对象；解析时剥离 markdown 代码围栏与前后杂文本
"""

import json
import logging
import re

import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.gateway.contracts import SCENE_CONTRACTS, SCENE_MODEL_MAP

logger = logging.getLogger("app.gateway")


class LLMDegradedError(Exception):
    """LLM 不可用/未启用/输出不合格式：调用方降级处理，不影响主流程。"""


# ---- 各场景 system prompt（要求仅输出 JSON）----

_SCENE_PROMPTS: dict[str, str] = {
    "summary": (
        "你是大学生问答社区的摘要助手。为用户提问生成不超过 100 字的中文摘要，"
        "概括核心问题与关键背景（学科、目标、已知条件）。"
        '仅输出 JSON：{"summary": "摘要文本", "need_review": false}。'
        "当提问信息量过低不足以生成可靠摘要时 need_review 置 true。"
    ),
    "ref_answer": (
        "你是大学生问答社区的助教。基于问题给出结构清晰的参考回答（思路、步骤、结论）。"
        '仅输出 JSON：{"answer_text": "回答全文", "confidence": 0.0-1.0}。'
        "confidence 为你对回答正确性的把握；无把握的问题如实说明并降低 confidence。"
    ),
    "reliability": (
        "你是大学生问答社区的答案审核员。判断该回答对给定问题的可靠程度。"
        '仅输出 JSON：{"score": 0-100, "level": "高"|"中"|"存疑"}。'
        "存在事实错误、逻辑漏洞或与问题无关时给低分并标存疑。"
    ),
    "quality": (
        "你是大学生问答社区的低质回答检测器。判断回答是否为灌水/复制粘贴/无意义内容"
        "（如纯表情、只有『不知道』、与问题完全无关的凑字）。"
        '仅输出 JSON：{"is_low_quality": true|false, "reason": "判定原因，无则空串"}。'
    ),
    "moderation": (
        "你是大学生问答社区的内容安全审核员。对内容做违规分级。"
        '仅输出 JSON：{"level": "极高"|"高"|"低", "violation_type": "违规类型或 null"}。'
        "极高=涉政有害/色情/暴恐/赌博毒品；高=辱骂攻击/广告引流/泄露隐私；低=正常内容。"
    ),
}


def _extract_json(text: str) -> dict:
    """从模型输出提取首个 JSON 对象（剥离 ```json 围栏与前后杂文本）。"""
    cleaned = re.sub(r"```(?:json)?|```", "", text or "").strip()
    start = cleaned.find("{")
    if start < 0:
        raise LLMDegradedError("模型输出中未找到 JSON 对象")
    # 从最后一个 } 截断，容忍尾随杂文本
    end = cleaned.rfind("}")
    if end <= start:
        raise LLMDegradedError("模型输出 JSON 不完整")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMDegradedError(f"模型输出 JSON 解析失败: {e}") from e


class GatewayClient:
    """五场景统一客户端。模块级单例见文件尾 `gateway`。"""

    # 场景级超时（秒）：生成长文本的场景放宽（V1.3 实测 qwen-plus 生成参考回答可超 10s）
    _SCENE_TIMEOUTS = {"ref_answer": 60}

    def invoke(self, scene: str, payload: dict) -> dict:
        """调用 LLM 场景，返回契约输出字段 dict；任何失败抛 LLMDegradedError。"""
        if not settings.LLM_ENABLED or not settings.LLM_API_KEY:
            raise LLMDegradedError(f"LLM 未启用（scene={scene}）")
        if scene not in SCENE_CONTRACTS:
            raise LLMDegradedError(f"未知场景: {scene}")

        in_model, out_model = SCENE_CONTRACTS[scene]
        try:
            payload = in_model(**payload).model_dump()
        except ValidationError as e:
            raise LLMDegradedError(f"场景 {scene} 输入不合契约: {e}") from e

        # 用户侧输入拼进 user 消息（title/content 等，由契约保证长度）
        user_text = json.dumps(payload, ensure_ascii=False)
        body = {
            "model": SCENE_MODEL_MAP[scene],
            "messages": [
                {"role": "system", "content": _SCENE_PROMPTS[scene]},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.3,
        }
        content = self._chat(body, scene)
        try:
            return out_model(**_extract_json(content)).model_dump()
        except ValidationError as e:
            raise LLMDegradedError(f"场景 {scene} 输出不合契约: {e}") from e

    def _chat(self, body: dict, scene: str) -> str:
        """chat/completions 调用：超时+重试；网络/非 200/空回复均抛降级。"""
        url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}
        timeout = self._SCENE_TIMEOUTS.get(scene, settings.LLM_TIMEOUT_SECONDS)
        last_err: Exception | None = None
        for attempt in range(settings.LLM_MAX_RETRIES + 1):
            try:
                resp = httpx.post(
                    url, json=body, headers=headers, timeout=timeout
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    if content and content.strip():
                        return content
                    raise LLMDegradedError("模型返回空内容")
                # 4xx（除 429）多为参数/鉴权问题，重试无意义
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    raise LLMDegradedError(
                        f"LLM HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                last_err = LLMDegradedError(f"LLM HTTP {resp.status_code}")
            except LLMDegradedError:
                raise
            except Exception as e:  # 网络错误/超时 → 重试
                last_err = e
            logger.warning("LLM 调用失败 scene=%s 第%d次: %s", scene, attempt + 1, last_err)
        raise LLMDegradedError(f"LLM 调用最终失败（已重试）: {last_err}")


gateway = GatewayClient()
