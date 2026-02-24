"""
将项目根目录加入 sys.path，使所有测试文件可以直接 import 项目模块。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
