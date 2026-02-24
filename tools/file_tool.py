"""
tools/file_tool.py
简单的文件读写工具，供 Agent 节点读取源码、写入 patch 使用。
"""

import os
from utils.logger_handler import logger


def read_file(file_path: str, encoding: str = "utf-8") -> str:
    """
    读取文件内容。

    :param file_path: 文件绝对路径
    :param encoding:  文件编码，默认 utf-8
    :return:          文件文本内容；读取失败返回空字符串
    """
    if not os.path.isfile(file_path):
        logger.error(f"[file] 文件不存在: {file_path}")
        return ""

    try:
        with open(file_path, "r", encoding=encoding) as f:
            content = f.read()
        logger.debug(f"[file] 读取成功: {file_path}  ({len(content)} chars)")
        return content
    except Exception as e:
        logger.error(f"[file] 读取失败: {file_path} → {e}")
        return ""


def write_file(file_path: str, content: str, encoding: str = "utf-8") -> bool:
    """
    将内容写入文件，父目录不存在时自动创建。

    :param file_path: 文件绝对路径
    :param content:   待写入文本
    :param encoding:  文件编码，默认 utf-8
    :return:          True = 写入成功
    """
    try:
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(file_path, "w", encoding=encoding) as f:
            f.write(content)

        logger.info(f"[file] 写入成功: {file_path}  ({len(content)} chars)")
        return True
    except Exception as e:
        logger.error(f"[file] 写入失败: {file_path} → {e}")
        return False
