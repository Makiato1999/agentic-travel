English | [中文](./README.zh-CN.md)

# Agentic Travel Planner

An LLM-powered multi-agent business travel planning system that connects preference memory, knowledge-grounded question answering, real-time information lookup, and itinerary generation into a single end-to-end assistant flow. The project follows a **Plan-and-Execute** architecture built on `AgentScope`, a local RAG knowledge base, long-term memory, and a skill-based plugin structure.

## Overview

- Designed for business travel scenarios rather than single-turn Q&A or one-off itinerary generation
- Starts from natural language input and completes intent recognition, agent orchestration, result aggregation, and memory updates
- Supports preference management, memory lookup, enterprise knowledge QA, real-time information queries, event collection, and itinerary planning
- The main flow has been validated end to end: `preference`, `memory_query`, `rag_knowledge`, `information_query`, `event_collection`, `itinerary_planning`, and `cli.py`

## Core Capabilities

- Multi-agent orchestration: uses an `IntentionAgent -> OrchestrationAgent -> Skills` execution flow with multi-intent recognition and priority-based scheduling
- Preference memory: stores and updates long-term user preferences such as home location, transportation, hotel, and food preferences, and supports recall through `memory_query`
- Enterprise knowledge QA: uses a local vector store to answer travel-policy questions such as reimbursement rules, booking guidance, standards, and emergency procedures
- Real-time information lookup: supports weather queries and public web search. Weather is provided by `WeatherAPI.com`, while open information is enriched through web search for downstream planning
- Itinerary planning: combines structured trip details, long-term preferences, and external information into a personalized business travel plan
- Skill-based plugin architecture: each capability is organized as a skill under `.claude/skills/`, loaded on demand through `LazyAgentRegistry`; `SKILL.md` defines behavior boundaries and prompt rules, while `script/agent.py` contains executable logic

## Example Scenario

A representative input:

```text
I recently moved to Suzhou. For this trip, I no longer want to take high-speed rail and would prefer a direct flight instead. I still want a quiet hotel, ideally close to a metro station, and I want lighter food. Next week I need to travel from Suzhou to Wuhan for a 4-day business trip. First, tell me how long I usually have to submit reimbursement after a trip, then check the weather in Wuhan for next week, and finally plan a business travel itinerary based on these updated preferences.
```

For a request like this, the system can:

- update user preferences
- answer travel-policy questions
- query weather information
- extract trip details
- generate a personalized business travel plan

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

If you have adjusted RAG-related dependencies locally, make sure the following remain compatible in your environment:

- `numpy`
- `torch`
- `sentence-transformers`

### 2. Configure the model

Edit [config.py](./config.py) and provide your LLM settings:

```python
LLM_CONFIG = {
    "api_key": "YOUR_LLM_API_KEY",
    "model_name": "YOUR_MODEL_NAME",
    "base_url": "YOUR_BASE_URL",
}
```

### 3. Configure weather access

Set up `WeatherAPI.com` in [config.py](./config.py):

```python
WEATHER_API_CONFIG = {
    "provider": "weatherapi",
    "api_key": "YOUR_WEATHERAPI_KEY",
    "base_url": "https://api.weatherapi.com/v1",
    "language": "zh",
}
```

### 4. Initialize the knowledge base

```bash
python .claude/skills/ask-question/script/init_knowledge_base.py
```

### 5. Run the CLI

```bash
python cli.py
```

### 6. Run the API

Install the new API dependencies and start `FastAPI`:

```bash
uvicorn api:app --reload
```

Core endpoints for the first phase:

- `POST /api/v1/sessions`: create a session with `user_id`
- `POST /api/v1/sessions/{session_id}/chat`: send one natural-language request
- `GET /api/v1/sessions/{session_id}/status`: inspect memory and loaded agents
- `GET /api/v1/sessions/{session_id}/history`: fetch trip history
- `GET /api/v1/sessions/{session_id}/preferences`: fetch saved preferences
- `POST /api/v1/sessions/{session_id}/clear`: clear short-term memory
- `POST /api/v1/sessions/{session_id}/end`: close the session

## Architecture

```text
User Input
   ↓
IntentionAgent
   ↓
OrchestrationAgent
   ↓
Skills
  - preference
  - memory_query
  - event_collection
  - rag_knowledge
  - information_query
  - itinerary_planning
   ↓
CLI / Final Response
```

## Repository Structure

```text
.
├── agents/                  # core logic for intention, orchestration, and registries
├── context/                 # memory manager and long-term memory
├── data/                    # local memory, models, and knowledge files
├── .claude/skills/          # skill plugins
├── tests/                   # unit and integration tests
├── cli.py                   # interactive entry point
├── config.py                # model, weather, and RAG configuration
└── README.md
```

## Testing

- Integrated validation has been completed for both `IntentionAgent` and `OrchestrationAgent`
- The main flow covering preference memory, enterprise knowledge QA, weather lookup, event extraction, and itinerary planning has been verified
- The CLI entry point has also passed basic regression testing

## Roadmap

- Redis as a hot-data and session cache layer
- PostgreSQL as structured long-term memory storage
- RAG improvements: query rewrite, hybrid retrieval, and reranking
- Stronger transport realism constraints and more stable budget estimation
