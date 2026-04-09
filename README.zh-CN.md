[English](./README.md) | 中文

# Agentic Travel Planner

一个由大语言模型驱动的多智能体差旅规划系统，围绕“偏好记忆 + 知识问答 + 实时信息查询 + 行程规划”构建完整差旅助手链路。项目当前采用 **Plan-and-Execute** 架构，基于 `AgentScope`、本地 RAG 知识库、长期记忆和技能化插件系统，支持从自然语言需求到可执行出行方案的端到端生成。

## 项目定位

这个项目关注的不是单点问答，而是一个更完整的差旅助手流程：

- 理解用户输入中的多重意图
- 记住并更新用户长期偏好
- 查询企业差旅知识库
- 查询实时天气等外部信息
- 将结构化事项与用户偏好整合为个性化出行方案

当前仓库已经验证通过的核心链路包括：

- `preference`
- `memory_query`
- `rag_knowledge`
- `information_query`
- `event_collection`
- `itinerary_planning`
- `cli.py` 交互入口

---

## 核心亮点

### 1. 多智能体意图识别与编排

- 基于 LLM 的多意图识别，而非简单关键词匹配
- 支持识别并调度行程规划、偏好管理、历史记忆查询、企业知识库问答、实时信息查询、事项收集等核心能力
- 使用 `IntentionAgent -> OrchestrationAgent -> Skills` 的分层执行结构
- 支持优先级调度：前置 agent 结果可作为后续规划输入

### 2. 用户偏好记忆

- 支持记录和更新用户的长期偏好，例如常住地、交通偏好、酒店偏好、餐饮偏好、座位/机型偏好
- 偏好写入后可通过 `memory_query` 回查
- 当前长期记忆以本地 JSON 持久化为主，适合单机开发与演示

### 3. 企业知识库 RAG

- 基于本地向量库进行差旅知识检索
- 覆盖差旅标准、报销时限与材料、预订指南、紧急情况处理、城市差旅注意事项等主题
- 返回最终答案的同时保留检索到的文档片段，便于追踪依据

### 4. 实时天气查询

- 当前天气能力已切换到 `WeatherAPI.com`
- 支持根据用户 query 或意图识别出的 `destination` 进行天气查询
- 作为实时信息输入供后续行程规划参考

### 5. 技能化插件架构

- 各子能力以 skill 的形式组织在 `.claude/skills/`
- 使用 `LazyAgentRegistry` 动态发现和按需加载 agent
- `SKILL.md` 负责定义行为边界与 prompt 规则
- `script/agent.py` 负责实际运行逻辑

### 6. 可解释的规划结果

- 行程规划输出包含路线、每日安排、交通建议、餐饮建议、注意事项和预算估计
- 规划阶段已补充现实性约束，尽量避免凭空虚构机场、车站、航班号等细节

---

## 系统架构

```text
用户输入
   ↓
IntentionAgent
  - 识别意图
  - 抽取关键实体
  - 生成 agent_schedule
   ↓
OrchestrationAgent
  - 按优先级调度各个技能 agent
  - 聚合各 agent 输出
  - 更新长期记忆
   ↓
Skills / Sub-agents
  - preference
  - memory_query
  - event_collection
  - rag_knowledge
  - information_query
  - itinerary_planning
   ↓
最终回复 / CLI 渲染
```

### 边界说明

- `IntentionAgent` 只负责“决定调用谁”，不直接完成业务动作
- `OrchestrationAgent` 才负责真正执行 agent 并汇总结果
- `memory_query` 与“上下文记忆增强”不是一回事：
  - 前者是业务查询
  - 后者是系统理解用户问题时的背景上下文

---

## 综合案例

项目支持在单轮输入中同时处理偏好更新、知识库问答、实时天气查询和行程规划。例如：

```text
我现在搬家去了苏州，这次出差不想坐高铁了，改成优先直飞航班；酒店还是希望商务一些，最好靠近CBD和地铁站，饮食上想要尝试当地的特色美食。下周我要从苏州去成都出差4天，请先告诉我差旅费用一般要在多久内报销，再查一下成都下周天气，最后结合这些最新偏好帮我规划一个商务出行方案。
```

在这类综合输入下，系统会：

- 更新用户偏好
- 抽取本次出差事项
- 从知识库中回答通用差旅政策问题
- 查询目的地实时天气
- 生成完整的个性化商务出行方案

---

## 已完成实现

当前仓库已经完成并验证的内容：

- 基于 LLM 的意图识别与多 agent 调度
- 本地 JSON 长期记忆读写
- 偏好写入与偏好回查
- 基于本地向量库的 RAG 知识库问答
- 基于 `WeatherAPI.com` 的天气查询
- 结构化事项收集与 itinerary 生成
- Skill 化插件结构与懒加载 agent 注册
- CLI 交互入口

---

## 下一阶段规划

以下内容是项目的下一步增强方向，目前不作为“已实现能力”：

- Redis 作为热数据与会话缓存层
  - 缓存用户偏好热点数据
  - 缓存长对话摘要结果
  - 降低重复查询与重复总结开销

- PostgreSQL 作为长期结构化记忆存储
  - 替代当前本地 JSON 持久化
  - 支持更稳定的多用户、多会话管理
  - 支持更细粒度统计与查询

- RAG 增强
  - query rewrite / query decomposition
  - hybrid retrieval
  - rerank
  - 更强的回答约束与证据对齐

- 规划阶段增强
  - 更强的现实交通约束
  - 更细的酒店/交通规则控制
  - 更稳定的预算估计

---

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

---

## 目录结构

```text
.
├── agents/                  # intention / orchestration / registry 等核心逻辑
├── context/                 # memory manager / long-term memory
├── data/                    # 本地 memory、模型、知识库文件
├── .claude/skills/          # 各类 skill 插件
│   ├── ask-question/
│   ├── event-collection/
│   ├── memory-query/
│   ├── plan-trip/
│   ├── preference/
│   └── query-info/
├── tests/                   # 单元/集成/实验性测试脚本
├── cli.py                   # 交互入口
├── config.py                # 模型、天气、RAG 等配置
└── README.zh-CN.md
```
