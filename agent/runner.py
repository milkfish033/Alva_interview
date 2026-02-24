"""
agent/runner.py
Coding Agent 的核心编排模块（Plan-Executor 架构）。

职责：
  1. 加载 config/config.yaml
  2. 初始化 LLM 及各节点函数
  3. 用 LangGraph StateGraph 构建 plan-executor 双分支 + solver 反馈流程图
  4. 提供 run_agent() 入口，执行 graph.invoke()

Graph 拓扑（plan-executor）：

  user_input
      │
  router ──────────────┬──────────────────────────────────────────────
      │                │
      ▼                │
  test (run_code)       │
      │                │
  test_writer           │
      │                │
  executor_test         │
      │                │
      ▼                │
  solver ◄──────────────┴──────────────────────────────────────────────
      │                     │
      │ is_fixed            │ is_fixed=False
      ├──► END              └──► debug ──► planner ──► executor ──► solver
      │                            │         ▲              │
      │ not fixed (test)            │         │              │
      └──► debug                   │         │              │
                                   │  replan │              │
                                   └─────────┴──────────────┘
                                     (retry_count < max_retry)
"""

import os
import yaml

from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.planner import make_analyze_error_node
from agent.patcher import make_generate_patch_node, make_apply_patch_node
from agent.evaluator import make_run_code_node
from agent.solver import (
    router,
    test_writer,
    executor_test,
    make_solver_node,
    solver_route,
)
from core.llm import load_llm
from tools.repo_tool import find_entry_file
from utils.logger_handler import logger
from utils.path_tool import get_abs_path
from utils.language_helper import get_language_from_path


# ── 配置加载 ───────────────────────────────────────────────────────────────

def _load_config(config_path: str = None) -> dict:
    """加载 config/config.yaml，返回配置字典。"""
    if config_path is None:
        config_path = get_abs_path("config/config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Graph 构建（plan-executor）───────────────────────────────────────────────

def build_graph(config: dict):
    """
    构建并编译 LangGraph StateGraph（plan-executor 架构）。

    :param config: 完整 config.yaml 字典
    :return:       已编译的 CompiledGraph 对象
    """
    agent_config = config.get("agent", {})
    workspace_config = config.get("workspace", {})

    llm = load_llm(agent_config)

    # 节点：test 分支 = test → test_writer → executor_test；debug 分支 = debug → planner → executor
    run_code_fn = make_run_code_node(workspace_config)
    analyze_error_fn = make_analyze_error_node(llm)
    generate_patch_fn = make_generate_patch_node(llm)
    apply_patch_fn = make_apply_patch_node()
    solver_fn = make_solver_node(workspace_config)

    workflow = StateGraph(AgentState)

    # 注册节点（与图中命名一致）
    workflow.add_node("router", router)
    workflow.add_node("test", run_code_fn)
    workflow.add_node("test_writer", test_writer)
    workflow.add_node("executor_test", executor_test)
    workflow.add_node("solver", solver_fn)
    workflow.add_node("debug", analyze_error_fn)
    workflow.add_node("planner", generate_patch_fn)
    workflow.add_node("executor", apply_patch_fn)

    # 入口：router
    workflow.set_entry_point("router")

    # router → test（当前实现：始终先走 test 分支）
    workflow.add_edge("router", "test")

    # test 分支：test → test_writer → executor_test → solver
    workflow.add_edge("test", "test_writer")
    workflow.add_edge("test_writer", "executor_test")
    workflow.add_edge("executor_test", "solver")

    # solver 条件边：END | debug | planner（replan）
    workflow.add_conditional_edges(
        "solver",
        solver_route,
        {"end": END, "debug": "debug", "planner": "planner"},
    )

    # debug 分支：debug → planner → executor → solver（反馈到 solver）
    workflow.add_edge("debug", "planner")
    workflow.add_edge("planner", "executor")
    workflow.add_edge("executor", "solver")

    return workflow.compile()


# ── 对外入口 ───────────────────────────────────────────────────────────────

def run_agent(target_path: str = None, config_path: str = None) -> AgentState:
    """
    启动 Coding Agent，执行完整的 检测 → 分析 → 修复 → 验证 流程。

    :param target_path: 可选，指定要修复的 Python 文件绝对/相对路径；
                        未指定时使用 workspace.entry_file 配置。
    :param config_path: 可选，config.yaml 路径；未指定时使用默认路径。
    :return:            流程结束时的最终 AgentState
    :raises FileNotFoundError: workspace 中找不到目标文件时抛出
    """
    config           = _load_config(config_path)
    agent_config     = config.get("agent", {})
    workspace_config = config.get("workspace", {})

    max_retry    = int(agent_config.get("max_retry", 5))
    repo_path    = get_abs_path(workspace_config.get("path", "workspace"))
    entry_file   = workspace_config.get("entry_file", "main.py")

    # ── 确定目标文件 ───────────────────────────────────────────────────────
    if target_path:
        target_file = os.path.abspath(target_path)
    else:
        target_file = find_entry_file(repo_path, entry_file)

    if not target_file or not os.path.isfile(target_file):
        raise FileNotFoundError(
            f"找不到目标文件: {target_file or repo_path}  "
            f"请在 workspace/ 中放置 Python 文件后重试。"
        )

    language_name, code_fence = get_language_from_path(target_file)
    logger.info("=" * 55)
    logger.info("[runner] Coding Agent 启动")
    logger.info(f"[runner] target_file : {target_file}")
    logger.info(f"[runner] language    : {language_name} (code_fence={code_fence})")
    logger.info(f"[runner] max_retry   : {max_retry}")
    logger.info("=" * 55)

    # ── 初始状态 ───────────────────────────────────────────────────────────
    initial_state: AgentState = {
        "repo_path":    repo_path,
        "target_file":  target_file,
        "patched_file": "",          # 修复后副本路径，由 apply_patch 写入 after_debug
        "file_content": "",          # 由 test(run_code) 首次加载
        "language":     language_name,
        "code_fence":   code_fence,
        "run_output":   "",
        "error_log":    "",
        "analysis":     "",
        "patch":        "",
        "retry_count":  0,
        "max_retry":    max_retry,
        "is_fixed":     False,
        "phase":        "test",       # plan-executor：先走 test 分支
    }

    # ── 编译并执行 Graph ───────────────────────────────────────────────────
    graph       = build_graph(config)
    final_state = graph.invoke(initial_state)

    return final_state
