# LangChain 简介

LangChain 是一个用于构建大语言模型（LLM）应用程序的开源框架，2022 年 10 月由 Harrison Chase 创建。它提供了模块化的组件，帮助开发者将 LLM 与其他数据源和工具集成。

## 核心模块

1. **Model I/O**：处理与 LLM 的输入输出交互，包括 Prompt 模板、输出解析器等。
2. **Retrieval**：检索增强生成（RAG）的核心，包括文档加载器、文本分割器、向量存储和检索器。
3. **Chains**：将多个组件组合成序列化工作流，如 LLMChain、SequentialChain。
4. **Agents**：让 LLM 决定执行哪些操作，包括 Tool 定义、Agent 类型和 AgentExecutor。
5. **Memory**：为对话提供状态保持能力，如 ConversationBufferMemory。
6. **Callbacks**：提供日志记录和追踪的回调机制。

## 支持的模型提供商

LangChain 支持 OpenAI、Anthropic、Google、Azure、Hugging Face、DeepSeek 等几十种模型提供商。用户通过统一的接口调用不同模型。

## 应用场景

- 文档问答（RAG）
- 聊天机器人
- 代码生成和分析
- 数据分析和可视化
- 自动化工作流
