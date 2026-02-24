"""
tests/test_coding_agent.py

Coding Agent 完整测试套件，覆盖五个层次：
  ① tools/exec_tool  — 代码执行工具
  ② tools/file_tool  — 文件读写工具
  ③ tools/repo_tool  — 工作目录扫描
  ④ agent/runner     — 条件路由逻辑（纯单元）
  ⑤ 完整 Pipeline    — Mock LLM，无需真实 API Key

运行方式：
  pip install pytest
  pytest tests/test_coding_agent.py -v
"""

import os
import sys
import textwrap
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from tools.exec_tool import run_python_file
from tools.file_tool  import read_file, write_file
from tools.repo_tool  import find_entry_file, list_python_files
from agent.state      import AgentState
from agent.runner     import _should_analyze, _should_retry


# ─── 公共辅助 ────────────────────────────────────────────────────────────────

def _write(path: str, code: str) -> str:
    """将 code 写入 path，自动创建父目录，返回 path。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    return path


def _state(**overrides) -> AgentState:
    """构造最小化的 AgentState，支持任意字段覆盖。"""
    base: AgentState = {
        "repo_path":    "/tmp",
        "target_file":  "/tmp/main.py",
        "file_content": "",
        "run_output":   "",
        "error_log":    "",
        "analysis":     "",
        "patch":        "",
        "retry_count":  0,
        "max_retry":    3,
        "is_fixed":     False,
    }
    base.update(overrides)
    return base


def _mock_llm(*contents: str) -> MagicMock:
    """
    创建按顺序返回 contents 的 Mock LLM。
    单个 content 时永远返回同一值；多个时按调用顺序消费。
    """
    llm = MagicMock()
    responses = [MagicMock(content=c) for c in contents]
    if len(responses) == 1:
        llm.invoke.return_value = responses[0]
    else:
        llm.invoke.side_effect = responses
    return llm


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dir():
    """提供临时目录，测试结束后自动清理。"""
    with tempfile.TemporaryDirectory() as d:
        yield d


# ════════════════════════════════════════════════════════════════════════════
# ① tools/exec_tool
# ════════════════════════════════════════════════════════════════════════════

class TestExecTool:

    def test_valid_code_returns_success(self, tmp_dir):
        """正常代码：success=True，stdout 包含预期输出。"""
        path = _write(os.path.join(tmp_dir, "ok.py"), "print('hello')\n")
        success, stdout, stderr = run_python_file(path, python_executable=sys.executable)

        assert success is True
        assert "hello" in stdout
        assert stderr == ""

    def test_buggy_code_returns_failure(self, tmp_dir):
        """有 Bug 的代码：success=False，stderr 含错误类型。"""
        path = _write(os.path.join(tmp_dir, "bad.py"), "1 / 0\n")
        success, stdout, stderr = run_python_file(path, python_executable=sys.executable)

        assert success is False
        assert "ZeroDivisionError" in stderr

    def test_nonexistent_file_no_exception(self):
        """文件不存在：success=False，不抛出异常，stderr 非空。"""
        success, stdout, stderr = run_python_file("/no/such/file.py")

        assert success is False
        assert stderr != ""

    def test_timeout_returns_failure(self, tmp_dir):
        """超时：success=False，不阻塞测试进程。"""
        path = _write(
            os.path.join(tmp_dir, "loop.py"),
            "import time; time.sleep(999)\n",
        )
        success, _, stderr = run_python_file(
            path, timeout=1, python_executable=sys.executable
        )

        assert success is False

    def test_stdout_captured_correctly(self, tmp_dir):
        """多行输出：stdout 完整捕获所有行。"""
        code = "for i in range(3): print(i)\n"
        path = _write(os.path.join(tmp_dir, "multi.py"), code)
        success, stdout, _ = run_python_file(path, python_executable=sys.executable)

        assert success is True
        assert "0" in stdout and "1" in stdout and "2" in stdout


# ════════════════════════════════════════════════════════════════════════════
# ② tools/file_tool
# ════════════════════════════════════════════════════════════════════════════

class TestFileTool:

    def test_write_then_read_roundtrip(self, tmp_dir):
        """写入后读取：内容与写入完全一致。"""
        path    = os.path.join(tmp_dir, "f.py")
        content = "print('ok')\n"

        assert write_file(path, content) is True
        assert read_file(path) == content

    def test_read_nonexistent_returns_empty_string(self):
        """读取不存在的文件：返回空字符串，不抛出异常。"""
        assert read_file("/nonexistent/path/x.py") == ""

    def test_write_auto_creates_nested_dirs(self, tmp_dir):
        """写入时父目录不存在：自动创建，写入成功。"""
        path = os.path.join(tmp_dir, "a", "b", "c.py")

        assert write_file(path, "x\n") is True
        assert os.path.isfile(path)

    def test_overwrite_replaces_content(self, tmp_dir):
        """覆盖写入：以最新内容为准。"""
        path = os.path.join(tmp_dir, "ow.py")
        write_file(path, "v1\n")
        write_file(path, "v2\n")

        assert read_file(path) == "v2\n"


# ════════════════════════════════════════════════════════════════════════════
# ③ tools/repo_tool
# ════════════════════════════════════════════════════════════════════════════

class TestRepoTool:

    def test_finds_named_entry_file(self, tmp_dir):
        """精确命中 entry_filename 时返回该文件路径。"""
        path = _write(os.path.join(tmp_dir, "main.py"), "")
        assert find_entry_file(tmp_dir, "main.py") == path

    def test_fallback_to_first_py_file(self, tmp_dir):
        """未找到指定入口文件时，回退到第一个 .py 文件。"""
        path = _write(os.path.join(tmp_dir, "app.py"), "")
        assert find_entry_file(tmp_dir, "main.py") == path

    def test_empty_directory_returns_none(self, tmp_dir):
        """空目录：返回 None，不抛出异常。"""
        assert find_entry_file(tmp_dir, "main.py") is None

    def test_nonexistent_directory_returns_none(self):
        """目录不存在：返回 None，不抛出异常。"""
        assert find_entry_file("/no/such/dir") is None

    def test_list_python_files_sorted_alpha(self, tmp_dir):
        """list_python_files 返回 .py 文件列表，按文件名字母排序。"""
        for name in ["c.py", "a.py", "b.txt", "b.py"]:
            open(os.path.join(tmp_dir, name), "w").close()

        names = [os.path.basename(p) for p in list_python_files(tmp_dir)]
        assert names == ["a.py", "b.py", "c.py"]   # b.txt 被过滤掉


# ════════════════════════════════════════════════════════════════════════════
# ④ agent/runner — 条件路由（纯单元，不依赖 LLM）
# ════════════════════════════════════════════════════════════════════════════

class TestRouting:

    def test_should_analyze_routes_end_when_fixed(self):
        """run_code 成功后：路由到 END。"""
        from langgraph.graph import END
        assert _should_analyze(_state(is_fixed=True)) == END

    def test_should_analyze_routes_analyze_when_broken(self):
        """run_code 失败后：路由到 analyze_error。"""
        assert _should_analyze(_state(is_fixed=False)) == "analyze_error"

    def test_should_retry_routes_end_when_fixed(self):
        """validate_fix 成功后：路由到 END。"""
        from langgraph.graph import END
        assert _should_retry(_state(is_fixed=True, retry_count=1)) == END

    def test_should_retry_routes_run_code_within_limit(self):
        """retry_count < max_retry：路由回 run_code 重试。"""
        assert _should_retry(_state(is_fixed=False, retry_count=1, max_retry=3)) == "run_code"

    def test_should_retry_routes_end_at_limit(self):
        """retry_count >= max_retry：路由到 END（放弃）。"""
        from langgraph.graph import END
        assert _should_retry(_state(is_fixed=False, retry_count=3, max_retry=3)) == END

    def test_should_retry_routes_end_beyond_limit(self):
        """retry_count > max_retry（防御性）：同样路由到 END。"""
        from langgraph.graph import END
        assert _should_retry(_state(is_fixed=False, retry_count=5, max_retry=3)) == END


# ════════════════════════════════════════════════════════════════════════════
# ⑤ 完整 Pipeline（Mock LLM，无需 API Key）
#
# LLM 调用顺序（每一轮 retry）：
#   run_code → analyze_error（LLM #1）→ generate_patch（LLM #2）
#            → apply_patch → validate_fix
#              ├── 成功 → END
#              └── 失败 → run_code（retry_count+1，下一轮继续）
# ════════════════════════════════════════════════════════════════════════════

class TestFullPipeline:

    def _make_config(self, tmp_dir: str, max_retry: int = 3) -> dict:
        return {
            "agent": {
                "provider":  "mock",
                "model":     "mock",
                "max_retry": max_retry,
            },
            "workspace": {
                "path":              tmp_dir,
                "entry_file":        "main.py",
                "timeout":           10,
                "python_executable": sys.executable,
            },
        }

    def _run_graph(self, config: dict, target: str, mock_llm) -> dict:
        """在 Mock LLM patch 下编译并执行 Graph，返回最终 state。"""
        with patch("agent.runner.load_llm", return_value=mock_llm):
            from agent.runner import build_graph
            graph = build_graph(config)
            return graph.invoke({
                "repo_path":    config["workspace"]["path"],
                "target_file":  target,
                "file_content": "",
                "run_output":   "",
                "error_log":    "",
                "analysis":     "",
                "patch":        "",
                "retry_count":  0,
                "max_retry":    config["agent"]["max_retry"],
                "is_fixed":     False,
            })

    # ── 场景 A：代码本身正确，LLM 完全不参与 ────────────────────────────

    def test_clean_code_ends_immediately(self, tmp_dir):
        """
        场景：workspace 代码无 Bug，首次 run_code 即成功。
        预期：is_fixed=True，retry_count=0，LLM invoke 次数 = 0。
        """
        target   = _write(os.path.join(tmp_dir, "main.py"), "print('all good')\n")
        mock_llm = _mock_llm("unused")

        result = self._run_graph(self._make_config(tmp_dir), target, mock_llm)

        assert result["is_fixed"] is True
        assert "all good" in result["run_output"]
        assert result["retry_count"] == 0
        mock_llm.invoke.assert_not_called()        # LLM 不应被调用

    # ── 场景 B：一轮修复成功 ─────────────────────────────────────────────

    def test_one_round_fix_succeeds(self, tmp_dir):
        """
        场景：ZeroDivisionError，LLM 首次生成正确 patch。
        预期：is_fixed=True，retry_count=1，LLM invoke 次数 = 2。
        """
        buggy = textwrap.dedent("""\
            def divide(a, b):
                return a / b

            if __name__ == "__main__":
                print(divide(10, 0))
        """)
        fixed = textwrap.dedent("""\
            def divide(a, b):
                if b == 0:
                    return "Error: division by zero"
                return a / b

            if __name__ == "__main__":
                print(divide(10, 0))
        """)

        target   = _write(os.path.join(tmp_dir, "main.py"), buggy)
        mock_llm = _mock_llm(
            "根本原因：b=0 导致 ZeroDivisionError，需在除法前判断 b 是否为 0。",  # analyze_error
            f"```python\n{fixed}\n```",                                              # generate_patch
        )

        result = self._run_graph(self._make_config(tmp_dir), target, mock_llm)

        assert result["is_fixed"] is True
        assert result["retry_count"] == 1
        assert mock_llm.invoke.call_count == 2

    # ── 场景 C：第二轮修复成功 ───────────────────────────────────────────

    def test_second_round_fix_succeeds(self, tmp_dir):
        """
        场景：第一次 patch 仍有 Bug，第二次 patch 正确。
        预期：is_fixed=True，retry_count=2，LLM invoke 次数 = 4。
        """
        buggy  = "raise ValueError('first bug')\n"
        still  = "raise ValueError('second bug')\n"   # 第一次错误 patch
        fixed  = "print('fixed!')\n"                  # 第二次正确 patch

        target   = _write(os.path.join(tmp_dir, "main.py"), buggy)
        mock_llm = _mock_llm(
            "分析：ValueError",           # analyze_error（第 1 轮）
            f"```python\n{still}\n```",   # generate_patch（第 1 轮，patch 错误）
            "分析：仍然 ValueError",      # analyze_error（第 2 轮）
            f"```python\n{fixed}\n```",   # generate_patch（第 2 轮，patch 正确）
        )

        result = self._run_graph(self._make_config(tmp_dir, max_retry=3), target, mock_llm)

        assert result["is_fixed"] is True
        assert result["retry_count"] == 2
        assert mock_llm.invoke.call_count == 4

    # ── 场景 D：超过 max_retry，放弃修复 ────────────────────────────────

    def test_gives_up_after_max_retry(self, tmp_dir):
        """
        场景：LLM 每次生成的 patch 均无效，达到 max_retry 后停止。
        预期：is_fixed=False，retry_count == max_retry，LLM invoke 次数 = max_retry * 2。

        Graph 流程（max_retry=2）：
          run_code→fail→analyze(1)→patch(1)→apply→validate(retry=1)→fail
          run_code→fail→analyze(2)→patch(2)→apply→validate(retry=2)→fail→END
        """
        buggy_forever = "raise RuntimeError('unfixable')\n"
        max_retry     = 2

        target = _write(os.path.join(tmp_dir, "main.py"), buggy_forever)

        # 每轮 2 次 LLM 调用（analyze + generate_patch），共 max_retry 轮
        llm_responses = []
        for i in range(1, max_retry + 1):
            llm_responses.append(f"分析：第 {i} 轮 RuntimeError")
            llm_responses.append(f"```python\n{buggy_forever}\n```")

        mock_llm = _mock_llm(*llm_responses)

        result = self._run_graph(
            self._make_config(tmp_dir, max_retry=max_retry), target, mock_llm
        )

        assert result["is_fixed"] is False
        assert result["retry_count"] == max_retry
        assert mock_llm.invoke.call_count == max_retry * 2

    # ── 场景 E：patch 内容校验 ───────────────────────────────────────────

    def test_patch_is_written_to_disk(self, tmp_dir):
        """
        场景：apply_patch 之后，磁盘上的文件内容应等于 LLM 生成的 patch。
        验证 patcher 的写入逻辑确实落盘。
        """
        buggy = "1 / 0\n"
        fixed = "print('patched')\n"

        target   = _write(os.path.join(tmp_dir, "main.py"), buggy)
        mock_llm = _mock_llm(
            "根本原因：ZeroDivisionError",
            f"```python\n{fixed}\n```",
        )

        self._run_graph(self._make_config(tmp_dir), target, mock_llm)

        # 无论 validate_fix 结果如何，磁盘上的文件应已被 patch 替换
        disk_content = read_file(target)
        assert disk_content.strip() == fixed.strip()
