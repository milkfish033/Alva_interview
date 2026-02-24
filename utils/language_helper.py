"""
utils/language_helper.py
根据文件路径/后缀识别编程语言，用于提示词与代码块标记。

保证：传入 .go 则分析与输出均为 Go，.java 则为 Java，.py 则为 Python，以此类推。
"""

import os
from typing import Tuple

# 后缀 -> (语言显示名, 代码块标记，如 ```go ```java)
_EXT_TO_LANG: dict[str, Tuple[str, str]] = {
    ".py":   ("Python", "python"),
    ".go":   ("Go", "go"),
    ".java": ("Java", "java"),
    ".kt":   ("Kotlin", "kotlin"),
    ".js":   ("JavaScript", "javascript"),
    ".ts":   ("TypeScript", "typescript"),
    ".tsx":  ("TypeScript React", "tsx"),
    ".jsx":  ("JavaScript React", "jsx"),
    ".rs":   ("Rust", "rust"),
    ".cpp":  ("C++", "cpp"),
    ".cc":   ("C++", "cpp"),
    ".cxx":  ("C++", "cpp"),
    ".c":    ("C", "c"),
    ".h":    ("C/C++ Header", "c"),
    ".rb":   ("Ruby", "ruby"),
    ".php":  ("PHP", "php"),
    ".swift": ("Swift", "swift"),
    ".scala": ("Scala", "scala"),
}


def get_language_from_path(file_path: str) -> Tuple[str, str]:
    """
    根据文件路径得到语言名和代码块标记。

    :param file_path: 目标文件路径（如 workspace/main.go）
    :return: (language_name, code_fence)，如 ("Go", "go")，用于提示词和 ```go ... ```
    """
    if not file_path:
        return "Python", "python"
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    return _EXT_TO_LANG.get(ext, ("Python", "python"))
