"""
tools/repo_tool.py
工作目录扫描工具：定位入口 Python 文件，列举仓库内所有 .py 文件。
"""

import os
from typing import List, Optional

from utils.logger_handler import logger
from utils.path_tool import get_abs_path


def find_entry_file(repo_path: str, entry_filename: str = "main.py") -> Optional[str]:
    """
    在工作目录中查找入口 Python 文件。

    查找策略：
      1. 优先返回名称与 entry_filename 完全匹配的文件
      2. 若未找到，回退到目录内第一个 .py 文件（按名称排序）
      3. 若目录为空或不存在，返回 None

    :param repo_path:       工作目录路径（绝对或相对均可）
    :param entry_filename:  优先查找的入口文件名，默认 main.py
    :return:                入口文件绝对路径，或 None
    """
    abs_repo = repo_path if os.path.isabs(repo_path) else get_abs_path(repo_path)

    if not os.path.isdir(abs_repo):
        logger.error(f"[repo] 工作目录不存在: {abs_repo}")
        return None

    # ── 策略 1：精确匹配 ───────────────────────────────────────────────────
    candidate = os.path.join(abs_repo, entry_filename)
    if os.path.isfile(candidate):
        logger.info(f"[repo] 入口文件: {candidate}")
        return candidate

    # ── 策略 2：回退到第一个 .py 文件 ─────────────────────────────────────
    py_files = list_python_files(abs_repo)
    if py_files:
        logger.warning(f"[repo] 未找到 '{entry_filename}'，回退到: {py_files[0]}")
        return py_files[0]

    logger.error(f"[repo] 工作目录 {abs_repo} 内没有 Python 文件")
    return None


def list_python_files(repo_path: str) -> List[str]:
    """
    列出目录内所有顶层 .py 文件（不递归），按文件名排序。

    :param repo_path: 目录路径
    :return:          .py 文件绝对路径列表
    """
    if not os.path.isdir(repo_path):
        return []

    return [
        os.path.join(repo_path, f)
        for f in sorted(os.listdir(repo_path))
        if f.endswith(".py") and os.path.isfile(os.path.join(repo_path, f))
    ]
