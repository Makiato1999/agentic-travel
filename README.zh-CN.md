[English](./README.md) | 中文

# Agentic Travel Planner

一个由大语言模型驱动的多智能体差旅规划系统，围绕“偏好记忆 + 知识问答 + 实时信息查询 + 行程规划”构建完整差旅助手链路。项目当前采用 **Plan-and-Execute** 架构，基于 `AgentScope`、本地 RAG 知识库、长期记忆和技能化插件系统，支持从自然语言需求到可执行出行方案的端到端生成。

## 项目概览

- 面向企业差旅场景，而不是单点问答或单次 itinerary 生成
- 从自然语言输入出发，完成意图识别、能力编排、结果聚合与记忆更新
- 支持偏好管理、历史查询、企业知识库问答、实时信息查询、事项收集与行程规划
- 当前主链路已经完成验证：`preference`、`memory_query`、`rag_knowledge`、`information_query`、`event_collection`、`itinerary_planning`、`cli.py`

## 核心能力

- 多智能体编排：采用 `IntentionAgent -> OrchestrationAgent -> Skills` 的执行结构，支持多意图识别与优先级调度。
- 偏好记忆：支持记录和更新常住地、交通方式、酒店偏好、饮食偏好等长期信息，并可通过 `memory_query` 回查。
- 企业知识问答：基于本地向量库完成差旅政策检索，覆盖报销规则、差旅标准、预订指南、应急处理等内容。
- 实时信息查询：支持天气查询与公开网络信息检索。天气通过 `WeatherAPI.com` 获取，其他开放信息通过网页搜索补充，为后续规划提供外部上下文。
- 行程规划：将结构化事项、长期偏好和外部信息整合为完整的商务出行方案。
- 技能化插件架构：各子能力以 skill 形式组织在 `.claude/skills/` 中，通过 `LazyAgentRegistry` 按需加载；`SKILL.md` 负责定义行为边界与 prompt 规则，`script/agent.py` 负责实际执行逻辑。

## 综合场景

一个典型输入示例：

```text
我现在搬家去了苏州，这次出差不想坐高铁了，改成优先直飞航班；酒店还是希望安静一些，最好靠近地铁站，饮食上改成清淡一点。下周我要从苏州去武汉出差4天，请先告诉我差旅费用一般要在多久内报销，再查一下武汉下周天气，最后结合这些最新偏好帮我规划一个商务出行方案。
```

在这类输入下，系统会完成：

- 偏好更新
- 差旅政策问答
- 天气查询
- 出行事项提取
- 个性化商务行程规划

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

如果你单独调整过 RAG 相关依赖，请根据本地环境确认：

- `numpy`
- `torch`
- `sentence-transformers`

之间的兼容性。

### 2. 配置模型

编辑 [config.py](./config.py)，配置你可用的 LLM 接口：

```python
LLM_CONFIG = {
    "api_key": "YOUR_LLM_API_KEY",
    "model_name": "YOUR_MODEL_NAME",
    "base_url": "YOUR_BASE_URL",
}
```

### 3. 配置天气接口

在 [config.py](./config.py) 中配置 `WeatherAPI.com`：

```python
WEATHER_API_CONFIG = {
    "provider": "weatherapi",
    "api_key": "YOUR_WEATHERAPI_KEY",
    "base_url": "https://api.weatherapi.com/v1",
    "language": "zh",
}
```

### 4. 初始化知识库

```bash
python .claude/skills/ask-question/script/init_knowledge_base.py
```

### 5. 运行 CLI

```bash
python cli.py
```

## 系统架构

```text
用户输入
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
CLI / 最终回复
```

## 目录结构

```text
.
├── agents/                  # intention / orchestration / registry 等核心逻辑
├── context/                 # memory manager / long-term memory
├── data/                    # 本地 memory、模型、知识库文件
├── .claude/skills/          # 各类 skill 插件
├── tests/                   # 单元 / 集成测试
├── cli.py                   # 交互入口
├── config.py                # 模型、天气、RAG 等配置
└── README.zh-CN.md
```

## 测试说明

- 已完成 `IntentionAgent` 与 `OrchestrationAgent` 的集成验证
- 已完成偏好记忆、知识库问答、天气查询、事项抽取和行程规划的主链路验证
- CLI 入口已完成基本回归测试

## 下一阶段规划

- Redis 作为热数据与会话缓存层
- PostgreSQL 作为长期结构化记忆存储
- RAG 增强：query rewrite、hybrid retrieval、rerank
- 更强的交通现实约束与预算估计能力
