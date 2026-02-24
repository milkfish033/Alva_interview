"""
agent/evaluator.py
[run_code 节点] + [validate_fix 节点]

run_code     : 首次执行 workspace 中的目标文件，记录运行结果到状态。
validate_fix : 修复后重新执行目标文件，验证 patch 是否生效，递增 retry_count。
"""

from utils.logger_handler import logger
from tools.exec_tool import run_python_file
from tools.file_tool import read_file
from agent.state import AgentState


def make_run_code_node(workspace_config: dict):
    """
    工厂函数：返回 run_code 节点函数，通过闭包注入 workspace 配置。

    :param workspace_config: config.yaml 中 workspace 节的字典
    :return:                 符合 LangGraph 节点签名的可调用对象
    """
    timeout     = workspace_config.get("timeout", 30)
    python_exec = workspace_config.get("python_executable", "python3")

    def run_code(state: AgentState) -> dict:
        """
        run_code 节点：
          输入  → state.target_file
          输出  → {run_output, error_log, is_fixed, file_content（首次加载）}
        """
        target_file = state.get("target_file", "")
        logger.info(f"[evaluator] 执行代码: {target_file}")

        # 首次执行时将文件内容加载到状态，后续节点可直接读取
        file_content = state.get("file_content", "")
        if not file_content:
            file_content = read_file(target_file)

        success, stdout, stderr = run_python_file(
            file_path=target_file,
            timeout=timeout,
            python_executable=python_exec,
        )

        if success:
            logger.info("[evaluator] 执行成功")
        else:
            logger.warning(f"[evaluator] 执行失败  stderr: {stderr[:300]}")

        return {
            "run_output":   stdout,
            "error_log":    stderr,
            "is_fixed":     success,
            "file_content": file_content,
        }

    return run_code


def make_validate_fix_node(workspace_config: dict):
    """
    工厂函数：返回 validate_fix 节点函数，通过闭包注入 workspace 配置。

    :param workspace_config: config.yaml 中 workspace 节的字典
    :return:                 符合 LangGraph 节点签名的可调用对象
    """
    timeout     = workspace_config.get("timeout", 30)
    python_exec = workspace_config.get("python_executable", "python3")

    def validate_fix(state: AgentState) -> dict:
        """
        validate_fix 节点：
          输入  → state.target_file, state.retry_count
          输出  → {run_output, error_log, is_fixed, retry_count（+1）, file_content}

        每次调用 retry_count + 1，用于 runner 中的重试上限判断。
        """
        target_file  = state.get("target_file", "")
        retry_count  = state.get("retry_count", 0)

        logger.info(f"[evaluator] 验证修复（retry={retry_count}）: {target_file}")

        success, stdout, stderr = run_python_file(
            file_path=target_file,
            timeout=timeout,
            python_executable=python_exec,
        )

        new_retry_count = retry_count + 1

        if success:
            logger.info("[evaluator] 验证通过，代码修复成功！")
        else:
            logger.warning(
                f"[evaluator] 验证失败  retry_count={new_retry_count}  "
                f"stderr: {stderr[:300]}"
            )

        return {
            "run_output":   stdout,
            "error_log":    stderr,
            "is_fixed":     success,
            "retry_count":  new_retry_count,
            # 重新从磁盘读取，确保与 apply_patch 写入的内容一致
            "file_content": read_file(target_file),
        }

    return validate_fix
