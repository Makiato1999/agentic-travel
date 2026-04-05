# 项目阅读笔记

## 主链路

- CLI 收用户输入
- `run()` 判断是命令还是自然语言请求
- 自然语言请求进入 `process_query()`
- `process_query()` 先做熔断检查：如果 breaker 已 `OPEN`，直接拒绝本次调用
- `process_query()` 组织长期/短期上下文
- 长期上下文来自 `_get_long_term_summary()`：
  `preference + 历史摘要(chat/trip) + 少量相关历史trip`
- 短期上下文来自 `short_term.get_recent_context(n_turns=5)`
- `process_query()` 把这些上下文拼成 `context_messages`
- `IntentionAgent` 用 LLM 产出 `agent_schedule`
- 意图识别这一步被 `retry_with_backoff()` 包裹：
  临时错误会指数退避重试
- 如果意图识别最终成功：
  `circuit_breaker.record_success()`
- 如果意图识别最终失败：
  `circuit_breaker.record_failure()`
- `process_query()` 把当前 user 输入写入 memory
- `OrchestrationAgent` 接收 `intention_result`
- `OrchestrationAgent` 解析 `agent_schedule`
- `OrchestrationAgent` 按优先级分批执行：
  同 priority 批内并发，不同 priority 批次串行
- orchestration 这一步同样被 `retry_with_backoff()` 包裹
- 执行单个 agent 时，通过 `LazyAgentRegistry` 按名字懒加载具体 agent
- 注册器内部靠动态导入 + `inspect` 找类并实例化
- registry 首次加载后会把 agent 放进内存 `cache`
- orchestrator 给子 agent 发送统一 `Msg`：
  `context + reason + expected_output + previous_results`
- 子 agent 执行业务逻辑并返回结构化 JSON
- orchestrator 统一解析每个子 agent 的结果
- orchestrator 聚合结果并更新记忆
- 当前 `_update_memory()` 主要把：
  `preference -> 长期偏好`
  `itinerary_planning + event_collection -> 历史trip`
- CLI 解析 orchestrator 返回的 JSON
- CLI 先显示调用了哪些 agent
- CLI 再根据各 agent 的 JSON 结果做结果渲染
- CLI 最后把 assistant 的结构化结果写回 memory

## Memory

- `MemoryManager` 是统一门面，但不是把所有方法都重新封装一层
- `add_message()` 会同时写：
  - `short_term`
  - `long_term.chat_history`
- `short_term`
  - 当前会话内存态消息
  - 程序停掉就没了
  - `get_recent_context(n_turns=5)` 本质是取最近几轮消息
- `long_term`
  - 当前项目是 JSON 文件持久化，不是数据库
  - 路径在 `data/memory/{user_id}.json`
  - 主要存：
    - `preferences`
    - `chat_history`
    - `trip_history`
    - `statistics`
- `_get_long_term_summary()` 组装长期上下文：
  - `preference`
  - `get_long_term_summary_async()` 生成的长期摘要
  - 和当前 query 相关的少量历史 trip
- `get_long_term_summary_async()` 主要总结：
  - 其他 session 的历史聊天
  - 历史 trip
- `history_from_other_sessions`
  - 表示排除当前 session 后的旧聊天记录
  - 避免和短期上下文重复

## Preference 结构

- 当前 `preferences` 在 JSON 里存成列表：
  `[{type, value}]`
- 读取时 `get_preference()` 再转成 dict 给上层使用
- 这样设计的好处：
  - 以后更容易给每条偏好加元数据
  - 更接近“每条偏好是一行记录”的表结构思维
- 如果工程化落库，长期记忆更适合 PostgreSQL

## Retry 与熔断

- `retry_with_backoff()` 是高阶函数
- 传进去的不是已经创建好的协程，而是“每次都能重新创建协程的函数”
- `lambda: self.intention_agent.reply(context_messages)`
  本质上是把“调用行为”作为参数传进去
- 这样 retry 失败后可以重新生成新的 coroutine
- retry 目标：
  - 尽量救活单次请求
  - 处理超时、网络抖动、限流、5xx
- 指数退避 + jitter 是经典工程重试策略

- 熔断器状态：
  - `CLOSED`
  - `OPEN`
  - `HALF_OPEN`
- 初始化时一定是 `CLOSED`
- `record_failure()` 记录的是“完整调用最终失败一次”
- 不是每个 retry attempt 失败都计数
- 连续失败达到 threshold 后：
  - `CLOSED -> OPEN`
- `OPEN` 后新请求通常会被 `raise_if_open()` 直接拒绝
- 到了恢复时间后，不靠后台任务，而是在读取 `self.state` 时懒判断：
  - `OPEN -> HALF_OPEN`
- `HALF_OPEN` 连续成功 enough 次：
  - `HALF_OPEN -> CLOSED`
- `HALF_OPEN` 失败一次：
  - `HALF_OPEN -> OPEN`

## Python 理解点

- `__getitem__`
  - 是 Python 特殊方法
  - 让对象支持 `obj[key]`
  - 在这里触发 `LazyAgentRegistry.__getitem__()`
- `hasattr(obj, "content")`
  - 检查对象有没有某个属性
  - 不是 `instanceof`
- Python 里更接近 Java `instanceof` 的是 `isinstance(...)`
- `@property`
  - 让方法看起来像属性
  - `self.state` 实际上会执行方法逻辑
- `inspect`
  - Python 标准库
  - 用来做运行时自省/反射
- `lambda`
  - 不只是做小计算
  - 本质是匿名函数
  - 这里用来包装“以后再执行的行为”

## 反射、动态加载、注册表

- 这个项目里用反射/动态加载，不是为了 URL 路由，而是为了插件化加载 agent
- 核心问题是：
  - orchestrator 只知道 `agent_name`
  - 但不想把每个 agent 类都硬编码在主流程里
- 所以需要运行时完成：
  - 按名字找到 skill 目录
  - 找到 `script/agent.py`
  - 把这个文件动态加载成模块
  - 在模块里找出继承 `AgentBase` 的类
  - 看构造函数需要哪些参数
  - 实例化 agent

- `_skill_map`
  - 本质是一个注册表
  - 存的是：
    - `skill_name -> agent.py 路径`
- `LazyAgentRegistry`
  - 像一个手搓的、插件化的懒加载 Bean 注册器
  - 初始化时只扫描和登记
  - 真正第一次 `registry[agent_name]` 时才加载 agent
- `cache`
  - 只是进程内内存 dict
  - 已加载 agent 放进去，下次复用

- `importlib.util.spec_from_file_location(...)`
  - Python 标准库能力
  - 作用是生成“如何加载这个模块”的说明对象 `spec`
- `importlib.util.module_from_spec(spec)`
  - 根据 `spec` 创建模块对象外壳
- `spec.loader.exec_module(module)`
  - 真正执行 `.py` 文件，把代码加载进模块对象

- `inspect`
  - 是 Python 标准库里的自省/反射工具
  - 这里主要用来：
    - 看模块里有哪些成员 `inspect.getmembers`
    - 判断成员是不是类 `inspect.isclass`
    - 判断是不是 `AgentBase` 子类 `issubclass`
    - 查看构造函数参数 `inspect.signature`

- 这个场景下反射的本质：
  - 运行时动态发现类
  - 运行时匹配类
  - 运行时实例化对象

### 和 Spring 的类比

- Spring 常见反射场景：
  - 扫描类路径
  - 识别注解
  - 自动注册 Controller / Bean
  - 运行时实例化和注入
- 这个项目里的 Python 场景：
  - 扫描 skills 目录
  - 按路径加载模块
  - 找 `AgentBase` 子类
  - 实例化 agent

- 相同点：
  - 都是在运行时自动发现和装配对象
  - 都是在避免把所有类手写死
- 不同点：
  - Spring 更依赖注解、BeanDefinition、容器
  - 这里更依赖文件路径、模块加载、`inspect`

- 可以粗暴记成：
  - Spring 里反射常用于“自动发现 Controller/Bean”
  - 这个项目里反射常用于“自动发现并加载 skill 里的 Agent 类”

## lambda、回调、高阶函数、retry

- `retry_with_backoff()` 不是接收“已经执行好的结果”
- 它接收的是：
  - 一个无参函数
  - 每次调用这个函数，都会返回一个新的协程
- 类型标注：
  - `Callable[[], Awaitable[T]]`
  - 可以理解成：
    - 一个不接收参数的函数
    - 每次调用都会返回一个可 `await` 的异步任务

- 这里传入：
  - `lambda: self.intention_agent.reply(context_messages)`
- 这个 `lambda` 的本质不是做计算
- 它是在包装一个“以后需要时再执行的调用行为”

### 为什么不能直接传函数返回值

- 如果直接传：
  - `self.intention_agent.reply(context_messages)`
- 那你得到的是：
  - 一个已经创建好的 coroutine 对象
- coroutine 对象通常只能被消费一次
- retry 失败后需要的是：
  - 再重新发起一次调用
  - 也就是重新创建一个新的 coroutine

- 所以 retry 需要的不是：
  - “第一次调用产生的那个协程对象”
- 而是：
  - “每次都能再造一个新协程的函数”

### 这一层最重要的理解

- 把“值”和“产生值的行为”分开
- retry 传进去的是行为，不是结果
- `lambda` 在这里本质上是：
  - 协程工厂函数
  - 延迟执行函数
  - 广义上也可以理解为一种回调

### 和回调函数的关系

- 回调函数的核心就是：
  - 先把函数行为传出去
  - 等合适时机再由别的代码调用
- retry 这里的思想是一样的：
  - 失败了，再调用一次你传进来的函数

### 和 Java / Node 的类比

- Python：
  - `lambda: self.intention_agent.reply(context_messages)`
- Java：
  - `() -> service.callAsync()`
  - 常见可对应 `Supplier<CompletableFuture<T>>`
- Node：
  - `() => fetchSomething()`

- 三者本质相同：
  - 传的不是结果
  - 而是“生成结果的函数/行为”

### 一个最重要的口头总结

- 这里不是把异步函数的返回值传给 retry
- 而是把“重新发起异步调用的动作”传给 retry
- 这样每次失败时，retry 都能重新创建一个新的 coroutine，再试一次

## AgentScope 使用边界

- 这个项目里 AgentScope 主要承担：
  - `AgentBase`
  - `Msg`
  - 模型封装
- 并发主要来自 Python `asyncio`
- orchestration 主要是作者手写 workflow
- 当前项目不是消息驱动/订阅广播式协作
- 结果传递主要靠：
  - `priority`
  - `previous_results`
- 所以它更像：
  - 用 AgentScope 组织 agent
  - 用 Python 手写 workflow

## 子 Agent 职责边界

- `event_collection`
  - 从当前用户需求里提取行程基础信息
  - 关注：
    - 出发地
    - 目的地
    - 日期
    - 出行目的
    - 缺失信息
  - 本质是“结构化行程信息收集”

- `preference`
  - 从当前输入中提取用户长期偏好
  - 关注：
    - 交通偏好
    - 酒店偏好
    - 航空公司偏好
    - 常驻地
    - 预算等
  - 本质是“偏好提取/更新建议”

- `information_query`
  - 查询外部客观信息
  - 例如：
    - 天气
    - 搜索结果
    - 实时信息
  - 本质是“联网信息查询”

- `itinerary_planning`
  - 基于已有 trip 信息和偏好生成具体行程方案
  - 本质是“行程规划”

- `memory_query`
  - 查询用户自己的历史信息
  - 例如：
    - 去过哪些地方
    - 之前说过什么偏好
    - 历史行程记录
  - 本质是“用户长期记忆查询”

- `rag_knowledge`
  - 查询知识库/政策/规则类信息
  - 例如：
    - 差旅标准
    - 报销规则
    - 企业知识库内容
  - 本质是“知识库问答”

## Skill 与运行时边界

- `SKILL.md` 不是当前 runtime 直接执行的脚本
- 对当前项目来说，`SKILL.md` 更像：
  - 说明书
  - prompt 指令来源
  - 使用约定
  - 有时附带伪代码/示例代码
- 真正运行时执行的是：
  - `script/agent.py`
- `IntentionAgent` 阶段对 skill 的使用：
  - 主要读取 `name` / `description`
  - 用来决定调哪些 agent
- 某些具体 agent 执行阶段对 skill 的使用：
  - 会读取完整 `SKILL.md`
  - 把它当作更详细的 prompt 指令
- 所以当前项目里：
  - 文档层和执行层没有完全分开
  - `SKILL.md` 的职责有些混杂

## Orchestration 结果结构

- `IntentionAgent` 返回的不是最终答案，而是调度计划
- 最关键字段是：
  - `agent_schedule`
- orchestrator 跑完后拿到的是每个 agent 的结果列表
- 每个 agent 的结果大致像：
  - `status`
  - `agent_name`
  - `data`
- orchestrator 最终会再聚合成总 JSON：
  - `status`
  - `intention`
  - `agents_executed`
  - `results`
- CLI 最后不是直接展示原始 JSON，而是按 `agent_name` 分支渲染

## Query Rewrite 作用

- `IntentionAgent` 不只负责调度，还负责生成 `rewritten_query`
- 后续很多 agent 消费的不是原始 `user_input`
- 而是：
  - `rewritten_query`
- 可以理解成：
  - `IntentionAgent` 先把用户原始输入做了一层标准化/补全
  - 后续 agent 再基于这层统一输入处理

## Memory 的两种使用方式

- `process_query()` 里的 memory：
  - 作为上下文背景
  - 帮助系统理解用户问题
- `memory_query` 里的 memory：
  - 作为回答的数据来源
  - 真正去查用户历史 trip / preference / chat
- 所以：
  - 一个是上下文增强
  - 一个是业务查询

## RAG 实现注意点

- 当前代码里的 RAG 主线：
  - 离线 `init_knowledge_base.py` 建库
  - 运行时 `RAGKnowledgeAgent.reply()` 检索 + 回答
- 运行时真正走的还是 agent 的 `reply()`
- `init_knowledge_base.py` 只是准备知识库数据，不在 CLI 主流程里自动执行
- 当前代码里的 RAG 更像：
  - 文本单模态
  - Milvus Lite 本地文件向量库
  - embedding + 余弦相似度 top-k 检索
  - 检索片段拼 prompt 后再交给 LLM 回答
- 当前代码没有明显看到：
  - 混合检索（向量 + 关键词）
  - metadata filter 后检索
  - rerank
- 文档宣传和代码实现存在不完全一致：
  - 文案里提到的模型、chunk 粒度、混合检索等细节，不一定和当前代码对齐
- 理解实现时：
  - 以代码为准
  - 文档只作为能力边界参考
