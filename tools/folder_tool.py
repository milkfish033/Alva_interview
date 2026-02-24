"""
tools/folder_tool.py
读取文件夹结构与文件内容的工具，供 Agent 在「整个文件夹」模式下收集上下文。

- 路径解析与 utils.path_tool.get_abs_path 一致：相对路径基于工程根目录转为绝对路径。
- 可列出目录树、按后缀过滤，并批量读取文件内容。
"""

import os
from typing import Optional

from utils.path_tool import get_abs_path
from utils.logger_handler import logger
from tools.file_tool import read_file


def get_folder_abs_path(folder_path: str) -> str:
    """
    将文件夹路径转为绝对路径，与 get_abs_path 约定一致。
    - 若已是绝对路径，则先 normpath 后返回；
    - 否则视为相对工程根的路径，用 get_abs_path 解析。

    :param folder_path: 相对路径（如 workspace/py）或绝对路径
    :return: 绝对路径
    """
    if not folder_path:
        return ""
    if os.path.isabs(folder_path):
        return os.path.normpath(folder_path)
    return get_abs_path(folder_path)


def list_folder_structure(
    folder_path: str,
    recursive: bool = True,
    extensions: Optional[list[str]] = None,
    exclude_dirs: Optional[list[str]] = None,
) -> list[str]:
    """
    列出文件夹内文件路径（相对该文件夹）。

    :param folder_path: 文件夹路径，相对工程根或绝对路径（见 get_folder_abs_path）
    :param recursive: 是否递归子目录
    :param extensions: 仅保留这些后缀的文件，如 [".py", ".go"]；None 表示全部
    :param exclude_dirs: 排除的目录名，如 ["__pycache__", ".git"]；None 表示不排除
    :return: 相对路径列表，如 ["main.py", "eval_module.py", "subdir/foo.py"]
    """
    root = get_folder_abs_path(folder_path)
    if not os.path.isdir(root):
        logger.error(f"[folder] 目录不存在: {root}")
        return []

    exclude_dirs = exclude_dirs or ["__pycache__", ".git", ".venv", "venv", "node_modules"]
    norm_ext = [e.lower() if e.startswith(".") else f".{e.lower()}" for e in (extensions or [])]
    rel_paths: list[str] = []

    if recursive:
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
            try:
                rel_base = os.path.relpath(dirpath, root)
            except ValueError:
                continue
            for name in filenames:
                if norm_ext and os.path.splitext(name)[1].lower() not in norm_ext:
                    continue
                if rel_base == ".":
                    rel_paths.append(name)
                else:
                    rel_paths.append(os.path.join(rel_base, name))
    else:
        for name in sorted(os.listdir(root)):
            full = os.path.join(root, name)
            if os.path.isfile(full):
                if norm_ext and os.path.splitext(name)[1].lower() not in norm_ext:
                    continue
                rel_paths.append(name)
            # 不递归时不列出子目录内的文件

    logger.info(f"[folder] 列出 {root} 共 {len(rel_paths)} 个文件")
    return sorted(rel_paths)


# 常用源码后缀，用于 read_folder_files 在 extensions=None 时的默认过滤
_DEFAULT_SOURCE_EXTENSIONS = [
    ".py", ".java", ".go", ".kt", ".rs", ".c", ".h", ".cpp", ".cc", ".cxx",
    ".js", ".ts", ".tsx", ".jsx", ".rb", ".php", ".swift", ".scala", ".sh", ".bash",
]

def read_folder_files(
    folder_path: str,
    recursive: bool = True,
    extensions: Optional[list[str]] = None,
    exclude_dirs: Optional[list[str]] = None,
    encoding: str = "utf-8",
) -> dict[str, str]:
    """
    读取文件夹内相关文件内容。路径约定同 list_folder_structure。

    :param folder_path: 文件夹路径（相对或绝对）
    :param recursive: 是否递归
    :param extensions: 只读这些后缀，如 [".py", ".java", ".go"]；None 表示使用常用源码后缀
    :param exclude_dirs: 排除的目录名
    :param encoding: 文件编码
    :return: { 相对路径: 文件内容 }，读取失败的文件不在此 dict 中
    """
    root = get_folder_abs_path(folder_path)
    if not os.path.isdir(root):
        logger.error(f"[folder] 目录不存在: {root}")
        return {}

    use_ext = extensions if extensions is not None else _DEFAULT_SOURCE_EXTENSIONS
    rel_paths = list_folder_structure(
        folder_path,
        recursive=recursive,
        extensions=use_ext,
        exclude_dirs=exclude_dirs,
    )
    out: dict[str, str] = {}
    for rel in rel_paths:
        abs_path = os.path.join(root, rel)
        content = read_file(abs_path, encoding=encoding)
        if content != "":
            out[rel] = content
    return out


def get_folder_summary(folder_path: str, recursive: bool = True) -> str:
    """
    返回文件夹结构摘要（纯文本树形），便于 Agent 快速了解目录布局。
    不读文件内容，只列路径。

    :param folder_path: 文件夹路径
    :param recursive: 是否递归
    :return: 多行字符串，如 "workspace/py\\n  main.py\\n  eval_module.py\\n  test_eval.py"
    """
    root = get_folder_abs_path(folder_path)
    if not os.path.isdir(root):
        return f"[目录不存在] {root}"

    rel_paths = list_folder_structure(folder_path, recursive=recursive, extensions=None)
    base_name = os.path.basename(root.rstrip(os.sep))
    lines = [f"{base_name}/"]
    for rel in rel_paths:
        lines.append(f"  {rel}")
    return "\n".join(lines)
