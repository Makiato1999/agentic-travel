---
name: query-info
description: Use this skill when the user wants real-time information or general web search. Triggers when user asks "天气怎么样", "查一下XX", "搜索XX", "机场到市区怎么走", "哪些区域适合入住". This skill uses InformationQueryAgent (weather via WeatherAPI.com, web search via DDGS). For policy, standards, reimbursement, or internal rules use ask-question (RAG) instead.
---

# Query Information (天气与网络搜索)

查询**天气**（WeatherAPI.com）和**网络搜索**（DDGS），使用 **InformationQueryAgent**。差旅标准、报销政策、审批流程等由 **ask-question**（RAG）处理。

## When to Use

- 用户问「XX天气怎么样」「查一下XX」「搜索XX」
- 用户问「机场到市区怎么走」「哪个区域适合商务入住」「路线/交通方式怎么选」
- 不需要用 RAG 知识库、不需要用户记忆时

## Agent

- **InformationQueryAgent**（当前通过 `.claude/skills/query-info/script/agent.py` 加载）
- 入参为 **model 对象**（非 model_config_name）
- **异步**：`reply()` 为 `async`，需 `await`

## 支持的查询类型（本 Agent 实际实现）

1. **天气查询**：基于 WeatherAPI.com（需配置 API Key）
2. **网络搜索**：基于 DDGS（需 `pip install ddgs`），带摘要

## 初始化与调用

```python
import asyncio
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from config_agentscope import init_agentscope
from config import LLM_CONFIG
from agents.lazy_agent_registry import LazyAgentRegistry
import json

async def query_info(user_query: str):
    init_agentscope()
    model = OpenAIChatModel(
        model_name=LLM_CONFIG["model_name"],
        api_key=LLM_CONFIG["api_key"],
        client_kwargs={"base_url": LLM_CONFIG["base_url"], "timeout": 60},
        temperature=LLM_CONFIG.get("temperature", 0.7),
        max_tokens=LLM_CONFIG.get("max_tokens", 2000),
    )
    registry = LazyAgentRegistry(model=model, cache={})
    agent = registry["information_query"]
    user_msg = Msg(name="user", content=user_query, role="user")
    result = await agent.reply(user_msg)
    return json.loads(result.content) if isinstance(result.content, str) else result.content

# 使用
data = asyncio.run(query_info("北京明天天气怎么样？"))
# data: {"query_type": "天气查询"|"网络搜索", "query_success": bool, "results": {"summary": "...", "sources": [...]}}
```

## 返回格式

- `query_type`: `"天气查询"` 或 `"网络搜索"`
- `query_success`: 是否成功
- `results`: 含 `summary`、`sources` 等（天气无 sources 时可能仅有 summary）

## 注意

- 本 Agent **不**处理「差旅标准」「报销规则」「审批流程」「平台操作说明」「历史行程」等；这类问题优先使用 **ask-question**（RAG）或 **memory-query**。
- 对「机场到市区怎么走」「哪些区域适合商务入住」「某地公共交通/路线建议」这类公开信息，应优先使用本 Agent 的网络搜索，而不是 RAG。
- 网络搜索依赖：`pip install ddgs`（或 `duckduckgo-search`）。


## 信息查询总结指南

【要求】
1. 直接回答问题，不要说"根据搜索结果"
2. 保持简洁，2-3句话
3. 如果信息不完整，说明需要更多信息
