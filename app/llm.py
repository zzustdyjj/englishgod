"""模型适配层：通过 LiteLLM 统一调用各家模型；LLM_MODEL=mock 时返回假数据，方便演示和测试。"""

import base64
import json
import mimetypes
import re
from pathlib import Path

from . import config


class LLMError(RuntimeError):
    pass


def is_mock() -> bool:
    return config.LLM_MODEL == "mock"


def image_part(path: Path) -> dict:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


def complete(messages: list[dict]) -> str:
    """messages 使用 OpenAI 格式；返回模型回复的文本。"""
    if is_mock():
        return _mock_complete(messages)

    import litellm

    kwargs = {"model": config.LLM_MODEL, "messages": messages, "timeout": 120}
    if config.LLM_API_KEY:
        kwargs["api_key"] = config.LLM_API_KEY
    if config.LLM_API_BASE:
        kwargs["api_base"] = config.LLM_API_BASE
    try:
        resp = litellm.completion(**kwargs)
    except Exception as e:  # 各厂商异常类型不同，统一包装
        raise LLMError(f"模型调用失败：{e}") from e
    return resp.choices[0].message.content or ""


def parse_json(text: str) -> dict:
    """容忍模型在 JSON 外包裹 ```json 代码块或多余文字。"""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"模型没有返回 JSON：{text[:200]}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"模型返回的 JSON 无法解析：{e}") from e


# ---------- 演示模式 ----------

def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text", "") for p in content if p.get("type") == "text")


def _mock_complete(messages: list[dict]) -> str:
    system = _text_of(messages[0]["content"]) if messages[0]["role"] == "system" else ""
    last_user = _text_of(messages[-1]["content"])

    if "提炼" in system:
        # 取对话里用户说的第一个英文片段作为锚点
        user_lines = [l for l in last_user.splitlines() if l.startswith("用户：")]
        words = re.findall(r"[A-Za-z][A-Za-z' ]*[A-Za-z]", " ".join(user_lines))
        anchor = words[0].strip() if words else "demo"
        has_image = "[图片1]" in last_user
        return json.dumps(
            {
                "gaps": [
                    {
                        "existing_gap_id": None,
                        "anchor_text": anchor,
                        "kind": "单词",
                        "skills": ["读"],
                        "core_note": f"（演示数据）{anchor} 在当前语境中的含义。",
                        "occurrence": {
                            "scene": "（演示数据）用户发来的截图",
                            "question": "这里是什么意思？",
                            "user_attempt": None,
                            "error": None,
                            "clarified": "（演示数据）配置真实模型后这里会是 AI 的提炼结果。",
                            "evidence": "已解释",
                            "image_ref": 1 if has_image else None,
                        },
                    }
                ]
            },
            ensure_ascii=False,
        )

    return (
        "（演示模式：还没有配置模型，这是一条假回复。）\n"
        f"我收到了你的问题：{last_user or '[图片]'}\n"
        "在 .env 中设置 LLM_MODEL 和 LLM_API_KEY 后重启，即可得到真实讲解。"
    )
