"""
agent/planner.py
[analyze_error 节点]

职责：接收代码和错误日志，调用 LLM 分析 root cause，
      将分析结果写入状态字段 `analysis`。
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from utils.logger_handler import logger
from agent.state import AgentState


def _system_prompt_for_language(language: str) -> str:
    return f"""\
你是一位资深 {language} 工程师，专注于 Bug 分析和 Root Cause 定位。
请仔细阅读下方 {language} 代码和错误日志，输出以下结构化分析：

1. **错误类型**：（根据语言举例，如 Go 的 panic、Java 的 Exception、Python 的 ZeroDivisionError 等）
2. **根本原因**：一句话说明为什么会出现该错误
3. **出错位置**：文件名 + 行号（如可从 Traceback/堆栈 中获取）
4. **修复思路**：用自然语言描述如何修复，不要写代码
"""


def make_analyze_error_node(llm: BaseChatModel):
    """
    工厂函数：返回 analyze_error 节点函数，通过闭包注入 LLM 依赖。

    :param llm: 已初始化的 LangChain Chat 模型
    :return:    符合 LangGraph 节点签名的可调用对象
    """

    def analyze_error(state: AgentState) -> dict:
        """
        analyze_error 节点：
          输入  → state.file_content, state.error_log
          输出  → {"analysis": <LLM 分析文本>}
        """
        retry_count  = state.get("retry_count", 0)
        file_content = state.get("file_content", "")
        error_log    = state.get("error_log", "")
        language     = state.get("language", "Python")
        code_fence   = state.get("code_fence", "python")

        logger.info(f"[planner] 分析错误（第 {retry_count + 1} 轮，语言: {language}）")

        user_msg = (
            f"【{language} 源码】\n```{code_fence}\n{file_content}\n```\n\n"
            f"【运行错误日志】\n```\n{error_log}\n```\n\n"
            f"请按要求输出 root cause 分析。"
        )

        messages = [
            SystemMessage(content=_system_prompt_for_language(language)),
            HumanMessage(content=user_msg),
        ]

        response = llm.invoke(messages)
        analysis = response.content

        logger.info("[planner] 错误分析完成")
        logger.debug(f"[planner] analysis[:300]=\n{analysis[:300]}")

        # plan-executor：标记进入 debug 分支，供 solver 区分来源
        return {"analysis": analysis, "phase": "debug"}

    return analyze_error
