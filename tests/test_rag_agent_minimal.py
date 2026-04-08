#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
最小 RAG 集成测试

目标：
1. 验证当前懒加载架构能否加载 rag_knowledge
2. 验证本地知识库 / embedding / Milvus 链路是否可用
3. 验证单条知识库问答能否返回结果
"""
import asyncio
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from agentscope.message import Msg
from agentscope.model import OpenAIChatModel

from agents.lazy_agent_registry import LazyAgentRegistry
from config import LLM_CONFIG
from config_agentscope import init_agentscope
from context.memory_manager import MemoryManager


TEST_QUERY = "北京的住宿标准是多少？"


def print_section(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


async def main():
    print_section("最小 RAG 集成测试")

    print("[1] 初始化系统")
    init_agentscope()

    model = OpenAIChatModel(
        model_name=LLM_CONFIG["model_name"],
        api_key=LLM_CONFIG["api_key"],
        client_kwargs={
            "base_url": LLM_CONFIG["base_url"],
        },
    )
    print("✓ 模型创建成功")

    memory_manager = MemoryManager(
        user_id="test_rag_user",
        session_id="test_rag_session",
        llm_model=model,
    )
    print("✓ 记忆管理器初始化成功")

    registry = LazyAgentRegistry(
        model=model,
        cache={},
        memory_manager=memory_manager,
    )
    print(f"✓ 懒加载注册器初始化成功，可用 agent: {sorted(registry.keys())}")

    print("\n[2] 加载 rag_knowledge")
    rag_agent = registry["rag_knowledge"]
    print("✓ rag_knowledge 加载成功")

    print("\n[3] 知识库问答")
    print(f"用户问题: {TEST_QUERY}")
    msg = Msg(name="user", content=TEST_QUERY, role="user")
    result = await rag_agent.reply(msg)

    print("\nraw result:")
    print(result.content)

    print("\nparsed result:")
    try:
        data = json.loads(result.content)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"JSON 解析失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
