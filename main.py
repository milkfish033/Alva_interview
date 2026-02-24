"""
main.py
AI Coding Agent 命令行入口。

用法：
  python main.py                        # 修复 workspace/main.py（默认）
  python main.py -f workspace/foo.py    # 指定目标文件
  python main.py -c config/config.yaml  # 指定配置文件
"""

import argparse
import sys

from agent.runner import run_agent
from utils.logger_handler import logger


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Coding Agent — 自动检测并修复 Python 代码 Bug",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="指定要修复的 Python 文件路径\n（默认: workspace/main.py）",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="指定 config.yaml 路径\n（默认: config/config.yaml）",
    )
    args = parser.parse_args()

    logger.info("=" * 55)
    logger.info("  AI Coding Agent  START")
    logger.info("=" * 55)

    try:
        final_state = run_agent(
            target_path=args.file,
            config_path=args.config,
        )
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Agent 运行异常: {e}")
        sys.exit(1)

    # ── 打印最终结果 ───────────────────────────────────────────────────────
    logger.info("=" * 55)
    if final_state.get("is_fixed"):
        logger.info("最终结果: 修复成功 ✓")
        output = final_state.get("run_output", "")
        if output:
            logger.info(f"代码运行输出:\n{output}")
        sys.exit(0)
    else:
        retry_count = final_state.get("retry_count", 0)
        error_log   = final_state.get("error_log", "")
        logger.error(f"最终结果: 修复失败（已重试 {retry_count} 次）")
        if error_log:
            logger.error(f"最后一次错误:\n{error_log}")
        sys.exit(1)


if __name__ == "__main__":
    main()
