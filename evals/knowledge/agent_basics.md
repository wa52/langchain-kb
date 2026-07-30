# LangChain Agent 基础

LangChain Agent 是一种让 LLM 能够自主决定调用外部工具的机制。Agent 的核心是让模型不只是生成文本，而是能够执行操作。

## Agent 的核心组件

1. **LLM**：作为 Agent 的"大脑"，决定执行哪些操作。
2. **Tool（工具）**：Agent 可以调用的外部函数，如搜索、计算器、API 调用等。
3. **AgentExecutor**：负责循环执行 Agent 的逻辑——思考、行动、观察。
4. **Memory**：让 Agent 记住之前的对话和操作。

## ReAct 模式

ReAct（Reasoning + Acting）是 Agent 的常用模式，它结合了推理和行动。Agent 在一轮中输出：
- Thought（思考）：分析当前状态和下一步计划
- Action（行动）：选择要调用的工具和参数
- Observation（观察）：工具返回的结果
- Final Answer（最终答案）：完成任务后的最终输出

## Agent 类型

- **zero-shot-react-description**：根据工具描述决定使用哪个工具，不依赖历史经验。
- **structured-chat-zero-shot**：支持结构化输出的工具调用。
- **conversational-react-description**：带对话记忆的 ReAct Agent。
- **openai-functions**：专为 OpenAI 函数调用优化的 Agent 类型。

## 工具定义

在 LangChain 中，使用 @tool 装饰器定义一个工具函数。工具需要包含名称、描述和实现逻辑，Agent 通过描述了解工具的用途和使用方式。
