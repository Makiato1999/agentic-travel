#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
最小集成测试：IntentionAgent + OrchestrationAgent + 懒加载 Skills

覆盖当前可用主链路：
1. preference - 保存偏好
2. memory_query - 查询历史偏好
3. event_collection + itinerary_planning - 行程规划
4. information_query - 外部信息查询（可选）

RAG / ask-question 暂不纳入此脚本。
"""
import asyncio
import json
import sys
import uuid
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from agentscope.message import Msg
from agentscope.model import OpenAIChatModel

from agents.intention_agent import IntentionAgent
from agents.lazy_agent_registry import LazyAgentRegistry
from agents.orchestration_agent import OrchestrationAgent
from config import LLM_CONFIG
from config_agentscope import init_agentscope
from context.memory_manager import MemoryManager


TEST_CASES = [
    # 按次序执行测试，每次只开一个测试任务
    {
        "name": "保存偏好",
        "query": "我常住杭州，出差时喜欢住万豪或希尔顿，坐飞机尽量选大机型和靠窗座位，请记住。",
    },
    {
        "name": "查询历史偏好",
        "query": "我之前说过什么住宿和座位偏好？",
    },
    {
        "name": "行程规划",
        "query": "下周我要从深圳去上海出差3天，帮我规划一个商务出行方案。",
    },
    {
        "name": "信息查询",
        "query": "上海下周的天气怎么样？",
    },
]


def print_section(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def parse_msg_json(msg: Msg) -> dict:
    if isinstance(msg.content, str):
        return json.loads(msg.content)
    return msg.content


def summarize_intention(intention_data: dict):
    intents = [item.get("type", "unknown") for item in intention_data.get("intents", [])]
    schedule = [
        f"{item.get('priority', '?')}:{item.get('agent_name', 'unknown')}"
        for item in intention_data.get("agent_schedule", [])
    ]
    print(f"识别意图: {intents}")
    print(f"调度计划: {schedule}")
    print(f"关键实体: {json.dumps(intention_data.get('key_entities', {}), ensure_ascii=False)}")


def summarize_orchestration(result_data: dict):
    print(f"执行状态: {result_data.get('status')}")
    print(f"执行智能体数: {result_data.get('agents_executed')}")
    for item in result_data.get("results", []):
        agent_name = item.get("agent_name", "unknown")
        status = item.get("status", "unknown")
        data = item.get("data", {})
        print(f"- {agent_name}: {status}")

        if agent_name == "preference":
            print(f"  偏好结果: {json.dumps(data, ensure_ascii=False)}")
        elif agent_name == "memory_query":
            answer = data.get("answer") or data.get("message") or json.dumps(data, ensure_ascii=False)
            print(f"  记忆回答: {answer}")
        elif agent_name == "event_collection":
            print(f"  事项信息: {json.dumps(data, ensure_ascii=False)}")
        elif agent_name == "itinerary_planning":
            if isinstance(data, dict):
                if data.get("error"):
                    print(f"  规划错误: {data.get('error')}")
                elif data.get("itinerary"):
                    print(f"  规划摘要: {json.dumps(data.get('itinerary', {}), ensure_ascii=False)[:500]}")
                else:
                    print(f"  规划结果: {json.dumps(data, ensure_ascii=False)[:500]}")
        elif agent_name == "information_query":
            print(f"  查询结果: {json.dumps(data, ensure_ascii=False)[:500]}")


async def main():
    print_section("智能体协调系统最小集成测试")

    print("[1] 初始化系统")
    init_agentscope()
    
    model = OpenAIChatModel(
            model_name=LLM_CONFIG["model_name"],
            api_key=LLM_CONFIG["api_key"],
            client_kwargs={
                "base_url": LLM_CONFIG["base_url"],
            },
            # temperature=LLM_CONFIG.get("temperature", 0.7),
            # max_tokens=LLM_CONFIG.get("max_tokens", 2000),
        )
    print(f"✓ 模型创建成功")

    session_id = str(uuid.uuid4())[:8]
    memory_manager = MemoryManager(
        user_id="test_orchestration_user",
        session_id=session_id,
        llm_model=model,
    )
    print(f"✓ 记忆管理器初始化成功 (session={session_id})")

    intention_agent = IntentionAgent(
        name="IntentionAgent",
        model=model,
    )
    print("✓ 意图识别智能体初始化成功")

    agent_cache = {}
    lazy_registry = LazyAgentRegistry(
        model=model,
        cache=agent_cache,
        memory_manager=memory_manager,
    )
    print(f"✓ 懒加载注册器初始化成功，可用 agent: {sorted(lazy_registry.keys())}")

    orchestrator = OrchestrationAgent(
        name="OrchestrationAgent",
        agent_registry=lazy_registry,
        memory_manager=memory_manager,
    )
    print("✓ 协调器初始化成功")

    conversation_context = []

    for idx, case in enumerate(TEST_CASES, 1):
        print_section(f"[{idx}] {case['name']}")
        print(f"用户输入: {case['query']}")

        user_msg = Msg(name="user", content=case["query"], role="user")
        intention_input = conversation_context + [user_msg]

        print("\n步骤 1: 意图识别")
        intention_result = await intention_agent.reply(intention_input)
        intention_data = parse_msg_json(intention_result)
        summarize_intention(intention_data)

        print("\n步骤 2: 编排执行")
        orchestration_result = await orchestrator.reply(intention_result)
        orchestration_data = parse_msg_json(orchestration_result)
        summarize_orchestration(orchestration_data)

        conversation_context.append(user_msg)
        conversation_context.append(Msg(name="assistant", content=orchestration_result.content, role="assistant"))
        memory_manager.add_message("user", case["query"])
        memory_manager.add_message("assistant", orchestration_result.content)

    print_section("长期记忆快照")
    prefs = memory_manager.long_term.get_preference()
    trips = memory_manager.long_term.get_trip_history(limit=5)
    print(f"偏好: {json.dumps(prefs, ensure_ascii=False)}")
    print(f"行程历史: {json.dumps(trips, ensure_ascii=False)}")

    print_section("测试完成")


if __name__ == "__main__":
    asyncio.run(main())
