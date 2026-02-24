"""
agent/state.py
定义 Coding Agent 的全局状态（AgentState）。

LangGraph 中所有节点通过读写此 TypedDict 共享数据，
每个节点函数返回需要更新的字段子集，LangGraph 自动合并。
"""

from typing import TypedDict


class AgentState(TypedDict):
    # ── 工作目录 & 目标文件 ────────────────────────────────────────────────
    repo_path:    str   # workspace 目录绝对路径
    target_file:  str   # 待修复的原始文件绝对路径（只读，不修改）
    patched_file: str   # 修复后副本路径：repo_path/after_debug/{stem}_copy{suffix}
    file_content: str   # 当前参与运行的源码（来自原文件或 patched_file）
    language:     str   # 语言显示名，如 Python / Go / Java（由 target_file 后缀推断）
    code_fence:   str   # 代码块标记，如 python / go / java（用于 LLM 输出与提取）

    # ── 代码执行结果 ───────────────────────────────────────────────────────
    run_output:   str   # 代码运行的标准输出（stdout）
    error_log:    str   # 代码运行的错误输出（stderr）
    is_fixed:     bool  # True = 代码执行成功（returncode == 0）

    # ── LLM 推理结果 ───────────────────────────────────────────────────────
    analysis:     str   # LLM 对 root cause 的分析文本
    patch:        str   # LLM 生成的修复后完整代码

    # ── 重试控制 ───────────────────────────────────────────────────────────
    retry_count:  int   # 当前已重试次数（每次 validate_fix 后 +1）
    max_retry:    int   # 最大重试次数（从 config.yaml 读取）

    # ── plan-executor 架构 ─────────────────────────────────────────────────
    phase:        str   # "test" | "debug"：当前所在分支，供 solver 路由
