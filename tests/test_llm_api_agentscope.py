import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agentscope.model import OpenAIChatModel
from config import LLM_CONFIG


async def main():
    model = OpenAIChatModel(
        model_name=LLM_CONFIG["model_name"],
        api_key=LLM_CONFIG["api_key"],
        client_kwargs={
            "base_url": LLM_CONFIG["base_url"],
            "timeout": 30,
        },
    )

    resp = await model([{"role": "user", "content": "只回复 OK"}])

    text = ""
    async for chunk in resp:
        if hasattr(chunk, "content") and isinstance(chunk.content, list):
            for item in chunk.content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
    
    print(text)

asyncio.run(main())