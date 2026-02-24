"""
根级 conftest.py：确保项目根目录在 sys.path 中，
使 utils / tools / agent / core 等包可被所有测试文件 import。
"""
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
