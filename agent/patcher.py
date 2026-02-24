"""
agent/patcher.py
[generate_patch 节点] + [apply_patch 节点]

generate_patch : 调用 LLM，根据错误分析生成修复后的完整代码（patch）。
apply_patch    : 不修改原文件，将 patch 写入 after_debug/{stem}_copy{suffix}，更新 patched_file、file_content。
"""

import os
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from utils.logger_handler import logger
from tools.file_tool import write_file
from agent.state import AgentState


def _patch_system_prompt_for_language(language: str, code_fence: str) -> str:
    return f"""\
你是一位资深 {language} 工程师。
根据提供的错误信息和分析，修复代码中的 Bug。

输出规则（严格遵守）：
- 只输出修复后的完整 {language} 代码，不省略任何一行
- 代码必须放在 ```{code_fence} ... ``` 代码块中
- 代码块之外不要有任何文字说明
"""


def make_generate_patch_node(llm: BaseChatModel):
    """
    工厂函数：返回 generate_patch 节点函数，通过闭包注入 LLM 依赖。

    :param llm: 已初始化的 LangChain Chat 模型
    :return:    符合 LangGraph 节点签名的可调用对象
    """

    def generate_patch(state: AgentState) -> dict:
        """
        generate_patch 节点：
          输入  → state.file_content, state.error_log, state.analysis
          输出  → {"patch": <修复后完整代码字符串>}
        """
        logger.info("[patcher] 生成修复代码（patch）")

        file_content = state.get("file_content", "")
        error_log    = state.get("error_log", "")
        analysis     = state.get("analysis", "")
        language     = state.get("language", "Python")
        code_fence   = state.get("code_fence", "python")

        user_msg = (
            f"【有 Bug 的 {language} 代码】\n```{code_fence}\n{file_content}\n```\n\n"
            f"【错误日志】\n```\n{error_log}\n```\n\n"
            f"【Root Cause 分析】\n{analysis}\n\n"
            f"请输出修复后的完整 {language} 代码（必须放在 ```{code_fence} ... ``` 代码块中）。"
        )

        messages = [
            SystemMessage(content=_patch_system_prompt_for_language(language, code_fence)),
            HumanMessage(content=user_msg),
        ]

        response    = llm.invoke(messages)
        patch_code  = _extract_code_block(response.content, code_fence)

        logger.info(f"[patcher] patch 生成完成  ({len(patch_code)} chars)")
        logger.debug(f"[patcher] patch[:200]:\n{patch_code[:200]}")

        return {"patch": patch_code}

    return generate_patch


def make_apply_patch_node():
    """
    工厂函数：返回 apply_patch 节点函数。
    不修改原文件，将修复后的代码写入 after_debug/{原名_copy}.{原后缀}。
    """

    def apply_patch(state: AgentState) -> dict:
        """
        apply_patch 节点：
          输入  → state.patch, state.target_file, state.repo_path
          输出  → {"patched_file", "file_content"}，原 target_file 不改动
          写入路径：repo_path/after_debug/{stem}_copy{suffix}，如 main.py → main_copy.py
        """
        logger.info("[patcher] 应用 patch（写入 after_debug 副本，不修改原文件）")

        patch       = state.get("patch", "")
        target_file = state.get("target_file", "")
        repo_path   = state.get("repo_path", "")

        if not patch:
            logger.error("[patcher] patch 为空，跳过写入")
            return {}

        if not target_file:
            logger.error("[patcher] target_file 未设置，无法写入")
            return {}

        # after_debug/{stem}_copy{suffix}，后缀保持不变 .py -> .py, .java -> .java
        basename = os.path.basename(target_file)
        stem, suffix = os.path.splitext(basename)
        out_name = f"{stem}_copy{suffix}"
        after_debug_dir = os.path.join(repo_path, "after_debug")
        patched_path = os.path.join(after_debug_dir, out_name)

        success = write_file(patched_path, patch)

        if success:
            logger.info(f"[patcher] 修复后代码已写入: {patched_path}（原文件未修改: {target_file}）")
            return {"patched_file": patched_path, "file_content": patch}
        else:
            logger.error(f"[patcher] 写入失败: {patched_path}")
            return {}

    return apply_patch


# ── 工具函数 ───────────────────────────────────────────────────────────────

def _extract_code_block(text: str, code_fence: str = "python") -> str:
    """
    从 LLM 输出中提取指定语言的代码块，如 ```go ... ```、```java ... ```。
    若未匹配到该语言的代码块，则尝试任意 ```lang ... ```，再回退到原始文本（trimmed）。
    """
    # 优先匹配当前语言
    escaped = re.escape(code_fence)
    pattern = rf"```(?:{escaped})?\s*\n?([\s\S]*?)```"
    matches = re.findall(pattern, text)
    if matches:
        return matches[0].strip()

    # 回退：匹配任意 ```xxx ... ``` 取第一块
    any_block = re.findall(r"```(?:\w+)?\s*\n?([\s\S]*?)```", text)
    if any_block:
        logger.warning(f"[patcher] 未找到 ```{code_fence}``` 代码块，使用其他代码块")
        return any_block[0].strip()

    logger.warning("[patcher] 未找到代码块，使用原始 LLM 输出")
    return text.strip()
