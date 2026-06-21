"""LLM 客户端封装（统一 OpenAI 格式）。

本模块是全后端调用 LLM 的**唯一入口**与可复用原语，集中承载：
- ``chat``：纯文本补全（自动剥离 ``<think>`` 思考段）；
- ``chat_json``：JSON 模式 + 健壮解析（markdown 去栅栏、截断闭合、控制字符清洗）；
- ``chat_structured``：在 ``chat_json`` 之上用 **pydantic 模型校验**，失败按温度衰减重试。

历史上「截断修复 / JSON 修复 / 温度衰减重试」散落在 simulation_config_generator 等
服务里各写一份；此处统一上提，服务层不再各自手写解析。
"""

import json
import re
from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from ..core.settings import settings

T = TypeVar("T", bound=BaseModel)


# ───────────────────────── 健壮 JSON 解析（模块级，可独立测试）─────────────────────────


def _strip_markdown_fences(text: str) -> str:
    """去掉 ```json ... ``` 代码块栅栏。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _close_truncated_json(text: str) -> str:
    """对被 max_tokens 截断的 JSON：补全未闭合的引号与括号。"""
    text = text.strip()
    if text and text[-1] not in '",}]':
        text += '"'
    text += "]" * (text.count("[") - text.count("]"))
    text += "}" * (text.count("{") - text.count("}"))
    return text


def parse_json_lenient(raw: str) -> dict[str, Any]:
    """尽力把 LLM 文本解析为 JSON 对象：直解 → 去栅栏 → 截断闭合 → 控制字符清洗。

    全部失败抛 ``ValueError``（附原文片段，便于定位）。
    """
    cleaned = _strip_markdown_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 提取最外层 {...} 并补全截断
    candidate = _close_truncated_json(cleaned)
    match = re.search(r"\{[\s\S]*\}", candidate)
    if match:
        json_str = match.group()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # 移除控制字符后再试
            json_str = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", json_str)
            json_str = re.sub(r"\s+", " ", json_str)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

    raise ValueError(f"LLM 返回的 JSON 无法解析: {cleaned[:200]}")


class LLMClient:
    """LLM客户端（OpenAI 兼容）。"""

    def __init__(
        self, api_key: str | None = None, base_url: str | None = None, model: str | None = None
    ):
        self.api_key = api_key or settings.llm_api_key
        self.base_url = base_url or settings.llm_base_url
        self.model = model or settings.llm_model_name

        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=settings.llm_request_timeout,
        )

    def _create(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: dict | None = None,
    ) -> tuple[str, str | None]:
        """底层调用，返回 (清洗后的文本, finish_reason)。"""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        content = choice.message.content or ""
        # 部分模型（如 MiniMax M2.5）会在 content 中夹带 <think> 思考段，需移除
        content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
        return content, choice.finish_reason

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> str:
        """发送聊天请求，返回模型响应文本。"""
        content, _ = self._create(messages, temperature, max_tokens, response_format)
        return content

    def chat_json(
        self, messages: list[dict[str, str]], temperature: float = 0.3, max_tokens: int = 4096
    ) -> dict[str, Any]:
        """JSON 模式调用并健壮解析为 dict（去栅栏/截断闭合/控制字符清洗）。"""
        content, _ = self._create(
            messages, temperature, max_tokens, response_format={"type": "json_object"}
        )
        return parse_json_lenient(content)

    def chat_structured(
        self,
        messages: list[dict[str, str]],
        schema: type[T],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        retries: int = 2,
    ) -> T:
        """JSON 模式调用 + pydantic 校验，返回 schema 实例。

        失败（解析失败/校验失败/调用异常）按温度衰减重试 ``retries`` 次；
        截断（finish_reason==length）时先补全再解析。最终仍失败则抛最后一次异常。
        """
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            temp = max(0.0, temperature - attempt * 0.1)  # 每次重试降温，提高确定性
            try:
                content, finish_reason = self._create(
                    messages, temp, max_tokens, response_format={"type": "json_object"}
                )
                if finish_reason == "length":
                    content = _close_truncated_json(content)
                data = parse_json_lenient(content)
                return schema.model_validate(data)
            except (ValueError, ValidationError, KeyError) as e:
                last_error = e
            except Exception as e:  # 网络/限频等
                last_error = e
        raise last_error or RuntimeError("LLM structured 调用失败")
