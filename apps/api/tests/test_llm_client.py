"""LLM 客户端可复用原语的单测（不真调 LLM）。

覆盖健壮 JSON 解析与 chat_structured 的 pydantic 校验/重试，
这是各服务共享的「解析+校验+重试」逻辑上提后的回归网。
"""

import pytest
from pydantic import BaseModel

from app.utils import llm_client
from app.utils.llm_client import LLMClient, parse_json_lenient

# ───────────────────────── 健壮 JSON 解析 ─────────────────────────


def test_parse_json_plain():
    assert parse_json_lenient('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_parse_json_with_markdown_fence():
    raw = '```json\n{"a": 1}\n```'
    assert parse_json_lenient(raw) == {"a": 1}


def test_parse_json_truncated_gets_closed():
    # 被截断（缺右括号与右引号）
    raw = '{"name": "alice", "tags": ["x", "y"'
    assert parse_json_lenient(raw) == {"name": "alice", "tags": ["x", "y"]}


def test_parse_json_with_control_chars():
    raw = '{"text": "line1\x07line2"}'
    out = parse_json_lenient(raw)
    assert "text" in out


def test_parse_json_unrecoverable_raises():
    with pytest.raises(ValueError):
        parse_json_lenient("totally not json at all")


# ───────────────────────── chat_structured + pydantic ─────────────────────────


class _Profile(BaseModel):
    name: str
    age: int


def _client_returning(monkeypatch, sequence):
    """构造一个不真连网络的 LLMClient，_create 依次返回 sequence 中的 (content, finish)。"""
    client = LLMClient.__new__(LLMClient)  # 跳过 __init__（不需 api_key/网络）
    calls = {"i": 0}

    def fake_create(messages, temperature, max_tokens, response_format=None):
        item = sequence[min(calls["i"], len(sequence) - 1)]
        calls["i"] += 1
        return item

    monkeypatch.setattr(client, "_create", fake_create)
    return client, calls


def test_chat_structured_validates_into_model(monkeypatch):
    client, _ = _client_returning(monkeypatch, [('{"name": "alice", "age": 30}', "stop")])
    out = client.chat_structured([{"role": "user", "content": "x"}], _Profile)
    assert isinstance(out, _Profile)
    assert out.name == "alice" and out.age == 30


def test_chat_structured_retries_then_succeeds(monkeypatch):
    # 第一次坏 JSON，第二次合法 → 重试后成功
    client, calls = _client_returning(
        monkeypatch,
        [("not json", "stop"), ('{"name": "bob", "age": 7}', "stop")],
    )
    out = client.chat_structured([{"role": "user", "content": "x"}], _Profile, retries=2)
    assert out.name == "bob"
    assert calls["i"] == 2  # 确实重试了一次


def test_chat_structured_raises_after_exhausting_retries(monkeypatch):
    client, _ = _client_returning(monkeypatch, [("still not json", "stop")])
    with pytest.raises((ValueError, Exception)):
        client.chat_structured([{"role": "user", "content": "x"}], _Profile, retries=1)


def test_module_exposes_parse_helper():
    # 服务层可直接复用模块级解析器
    assert hasattr(llm_client, "parse_json_lenient")
