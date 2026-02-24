"""
core/llm.py
根据 config.yaml 中的 provider 字段动态加载对应的 LangChain Chat 模型。

支持的 provider:
  - openai    : ChatOpenAI (需设置环境变量 OPENAI_API_KEY)
  - anthropic : ChatAnthropic (需设置环境变量 ANTHROPIC_API_KEY)
  - deepseek  : ChatOpenAI 兼容接口 (需设置环境变量 DEEPSEEK_API_KEY)
  - dashscope : ChatOpenAI 兼容接口，指向阿里云 DashScope (需设置环境变量 DASHSCOPE_API_KEY)
"""

import os
from langchain_core.language_models import BaseChatModel
from utils.logger_handler import logger


def load_llm(agent_config: dict) -> BaseChatModel:
    """
    根据 agent_config 加载对应 LLM 实例。

    :param agent_config: config.yaml 中 agent 节的字典
    :return: LangChain BaseChatModel 子类实例
    :raises ValueError: provider 不支持时抛出
    """
    provider    = agent_config.get("provider", "openai")
    model       = agent_config.get("model", "gpt-4o-mini")
    temperature = float(agent_config.get("temperature", 0))

    logger.info(f"[LLM] 加载模型 provider={provider}  model={model}  temperature={temperature}")

    # ── OpenAI ─────────────────────────────────────────────────────────────
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=os.environ.get("OPENAI_API_KEY"),
        )

    # ── Anthropic ──────────────────────────────────────────────────────────
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )

    # ── DeepSeek（OpenAI 兼容接口）────────────────────────────────────────
    elif provider == "deepseek":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )

    # ── DashScope / Qwen（OpenAI 兼容接口）───────────────────────────────
    elif provider == "dashscope":
        from langchain_openai import ChatOpenAI
        api_key = os.environ.get("DASHSCOPE_API_KEY", agent_config.get("api_key", ""))
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

    else:
        raise ValueError(
            f"[LLM] 不支持的 provider: '{provider}'，"
            f"请在 config.yaml 中使用: openai / anthropic / deepseek / dashscope"
        )
