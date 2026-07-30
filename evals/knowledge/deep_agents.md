# Deep Agents 框架

Deep Agents 是 LangChain 推出的新一代 Agent 框架，相比传统 Agent 具有更深层次的推理能力。它使用 create_deep_agent() 函数创建，并采用 Harness 架构运行。

## 核心特点

1. **深度推理**：支持多步推理和子目标拆解，适合复杂任务。
2. **Harness 架构**：Agent 运行在 Harness 中，支持中间件（Middleware）机制，可以在 Agent 执行流程中插入钩子函数。
3. **工具系统**：通过 @tool 装饰器定义工具，支持异步工具和流式输出。

## 中间件系统

Deep Agents 提供丰富的中间件：
- **HumanInTheLoopMiddleware**：在执行危险操作前请求人类审批。
- **SubAgentMiddleware**：将子任务委派给专门的子 Agent。
- **StatsMiddleware**：收集工具调用统计信息。

## 状态管理

Agent 状态通过 StateBackend（内存）和 StoreBackend（持久化）管理，支持：
- 对话历史持久化
- 状态快照和回滚
- 跨会话状态共享

## 使用方式

```python
from deep_agents import create_deep_agent

agent = create_deep_agent(
    model="deepseek-chat",
    tools=[my_tool],
    system_prompt="你是一个有用的助手"
)
result = agent.invoke("帮我完成这个任务")
```
