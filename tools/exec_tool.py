"""
tools/exec_tool.py
在子进程中执行 Python 文件，捕获 stdout / stderr 和退出码。
"""

import os
import subprocess
from typing import Tuple

from utils.logger_handler import logger


def run_python_file(
    file_path: str,
    timeout: int = 30,
    python_executable: str = "python3",
) -> Tuple[bool, str, str]:
    """
    在子进程中执行指定 Python 文件。

    :param file_path:         .py 文件的绝对路径
    :param timeout:           最长等待秒数，超时强制终止
    :param python_executable: Python 解释器命令或路径
    :return:                  (success, stdout, stderr)
                              success=True 表示 returncode == 0
    """
    if not os.path.isfile(file_path):
        msg = f"[exec] 文件不存在: {file_path}"
        logger.error(msg)
        return False, "", msg

    # 以文件所在目录作为工作目录，保证相对导入正常
    work_dir = os.path.dirname(file_path)
    logger.info(f"[exec] 执行: {python_executable} {os.path.basename(file_path)}")

    try:
        result = subprocess.run(
            [python_executable, file_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir,
        )

        stdout  = result.stdout.strip()
        stderr  = result.stderr.strip()
        success = result.returncode == 0

        if success:
            logger.info(f"[exec] 执行成功  returncode=0")
        else:
            logger.warning(f"[exec] 执行失败  returncode={result.returncode}")
            logger.debug(f"[exec] stderr: {stderr[:500]}")

        return success, stdout, stderr

    except subprocess.TimeoutExpired:
        msg = f"[exec] 执行超时（>{timeout}s）"
        logger.error(msg)
        return False, "", msg

    except Exception as e:
        msg = f"[exec] 执行异常: {e}"
        logger.error(msg)
        return False, "", msg
