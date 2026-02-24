"""
agent/solver.py
Plan-Executor 架构中的 Router、Test 分支（test_writer、executor_test）、Solver/Replanner。

- router       : 接收 user_input，将请求分发到 test 或 debug 分支（当前实现：先走 test）
- test_writer  : 测试分支中，将测试结果整理/写入状态（当前为透传）
- executor_test: 测试分支中的执行器占位（当前为透传，实际执行在 test=run_code）
- solver       : 接收两路 executor 输出，判断成功/失败并决定 END、进入 debug、或 replan
"""

from utils.logger_handler import logger
from tools.exec_tool import run_python_file
from tools.file_tool import read_file
from agent.state import AgentState


def router(state: AgentState) -> dict:
    """
    路由器：根据输入决定进入 test 或 debug 分支。
    当前策略：始终先进入 test 分支（运行代码检测是否已有错误）。
    """
    logger.info("[router] 将请求分发到 test 分支（运行目标代码）")
    return {"phase": "test"}


def test_writer(state: AgentState) -> dict:
    """
    测试分支：将测试（run_code）结果整理进状态，供 solver 使用。
    当前为透传，不额外写入字段。
    """
    logger.info("[solver] test_writer: 测试结果已就绪")
    return {}


def executor_test(state: AgentState) -> dict:
    """
    测试分支的执行器：图中占位，实际执行已在 test（run_code）完成。
    透传状态。
    """
    return {}


def make_solver_node(workspace_config: dict):
    """
    Solver/Replanner 节点：
    - 来自 test 分支：仅根据 is_fixed 路由，不再次运行代码。
    - 来自 debug 分支：执行 validate_fix（再跑一次代码、retry_count+1），再根据结果路由。
    """

    timeout = workspace_config.get("timeout", 30)
    python_exec = workspace_config.get("python_executable", "python3")

    def solver(state: AgentState) -> dict:
        phase = state.get("phase", "test")

        if phase == "test":
            logger.info("[solver] 来自 test 分支，根据运行结果路由")
            return {}

        # phase == "debug"：执行验证（运行 after_debug 下的副本，不跑原文件）
        patched_file = state.get("patched_file", "")
        target_file = state.get("target_file", "")
        file_to_run = patched_file if patched_file else target_file
        retry_count = state.get("retry_count", 0)
        logger.info(f"[solver] 来自 debug 分支，验证修复（retry={retry_count}）: {file_to_run}")

        success, stdout, stderr = run_python_file(
            file_path=file_to_run,
            timeout=timeout,
            python_executable=python_exec,
        )
        new_retry_count = retry_count + 1

        if success:
            logger.info("[solver] 验证通过，代码修复成功")
        else:
            logger.warning(
                f"[solver] 验证失败  retry_count={new_retry_count}  stderr: {stderr[:300]}"
            )

        return {
            "run_output": stdout,
            "error_log": stderr,
            "is_fixed": success,
            "retry_count": new_retry_count,
            "file_content": read_file(file_to_run),
        }

    return solver


def solver_route(state: AgentState):
    """
    Solver 之后的条件路由：
    - is_fixed → END
    - phase=="test" 且未修复 → debug
    - phase=="debug" 且未修复且 retry_count < max_retry → planner（replan）
    - 否则 → END
    """
    is_fixed = state.get("is_fixed", False)
    phase = state.get("phase", "test")
    retry_count = state.get("retry_count", 0)
    max_retry = state.get("max_retry", 5)

    if is_fixed:
        logger.info("[solver] 结果正常 → END")
        return "end"

    if phase == "test":
        logger.info("[solver] 测试未通过 → debug 分支")
        return "debug"

    if retry_count < max_retry:
        logger.warning(f"[solver] 修复未通过，重试 {retry_count}/{max_retry} → planner（replan）")
        return "planner"

    logger.error(f"[solver] 已达最大重试次数 {max_retry} → END（失败）")
    return "end"
