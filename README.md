# AI Coding Agent

基于 **LangGraph** 构建的 Plan-Executor 架构 AI 编码助手，能够自动检测、分析并修复代码中的 Bug，支持多种主流 LLM 提供商。

---

## 功能特性

- **自动检测**：运行目标文件，捕获 stdout / stderr 判断是否存在错误
- **智能分析**：调用 LLM 对错误日志进行 Root Cause 分析，定位错误类型与位置
- **自动修复**：根据分析结果生成完整的修复代码（patch），写入 `after_debug/` 副本
- **循环验证**：修复后重新运行代码，失败则自动重试，直至成功或达到最大重试次数
- **多语言支持**：Python / Go / Java（由文件后缀自动推断）
- **多 LLM 支持**：OpenAI、Anthropic Claude、DeepSeek、阿里云 DashScope（通义千问）

---

## 项目结构

```
.
├── main.py                  # 命令行入口
├── config/
│   └── config.yaml          # 核心配置（provider、model、workspace 路径等）
├── agent/
│   ├── state.py             # AgentState 全局状态定义
│   ├── runner.py            # LangGraph 图编排与 run_agent() 入口
│   ├── planner.py           # debug 节点：LLM 错误分析（analyze_error）
│   ├── patcher.py           # debug 节点：LLM 生成 patch + 写入磁盘（apply_patch）
│   ├── evaluator.py         # test 节点：运行代码（run_code）
│   └── solver.py            # router / test_writer / executor_test / solver / solver_route
├── core/
│   └── llm.py               # 根据 provider 动态加载 LangChain Chat 模型
├── tools/
│   ├── exec_tool.py         # 子进程执行 Python 文件，捕获 stdout/stderr
│   ├── file_tool.py         # 文件读写工具
│   ├── folder_tool.py       # 目录操作工具
│   └── repo_tool.py         # 工作区扫描，定位入口文件
├── utils/
│   ├── config_handler.py    # YAML 配置加载
│   ├── language_helper.py   # 根据文件后缀推断语言与 code_fence
│   ├── logger_handler.py    # 日志配置
│   └── path_tool.py         # 绝对路径辅助
├── workspace/               # 待修复的目标代码放置目录
│   ├── main.py              # 默认入口文件
│   └── after_debug/         # 修复后副本自动保存于此
├── tests/
│   └── test_coding_agent.py # 完整测试套件（含 Mock LLM 的全流程测试）
└── requirements.txt
```

---

## 工作流程（Graph 拓扑）

```
user_input
    │
  router
    │
  test (run_code)          ← 先运行代码，检测是否有错误
    │
  test_writer
    │
  executor_test
    │
  solver ──── is_fixed ──► END（代码正常，直接结束）
    │
    │ is_fixed=False
    ▼
  debug (analyze_error)    ← LLM 分析 Root Cause
    │
  planner (generate_patch) ← LLM 生成修复代码
    │
  executor (apply_patch)   ← 将 patch 写入 after_debug/ 副本
    │
  solver ──── is_fixed ──► END（修复成功）
    │
    │ retry_count < max_retry
    └──► planner（自动重试）
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 LLM

编辑 [config/config.yaml](config/config.yaml)，选择 LLM 提供商并设置对应环境变量：

```yaml
agent:
  provider: dashscope    # openai | anthropic | deepseek | dashscope
  model: qwen3-max
  temperature: 0
  max_retry: 5

workspace:
  path: workspace
  entry_file: main.py
  timeout: 30
  python_executable: python3
```

| provider    | 环境变量              | 说明                         |
|-------------|----------------------|------------------------------|
| `openai`    | `OPENAI_API_KEY`     | OpenAI GPT 系列               |
| `anthropic` | `ANTHROPIC_API_KEY`  | Anthropic Claude 系列         |
| `deepseek`  | `DEEPSEEK_API_KEY`   | DeepSeek（OpenAI 兼容接口）   |
| `dashscope` | `DASHSCOPE_API_KEY`  | 阿里云通义千问                |

```bash
export DASHSCOPE_API_KEY="your-api-key"
```

### 3. 准备待修复的代码

将有 Bug 的代码文件放入 `workspace/` 目录，默认入口为 `workspace/main.py`。

### 4. 运行 Agent

```bash
# 修复默认文件 workspace/main.py
python main.py

# 指定目标文件
python main.py -f workspace/broken_script.py

# 指定配置文件
python main.py -c config/config.yaml
```

修复后的代码副本保存在 `workspace/after_debug/` 目录下。

---

## 运行测试

```bash
pytest tests/test_coding_agent.py -v
```

测试套件覆盖五个层次：

| 层次 | 类 | 说明 |
|------|----|------|
| ① | `TestExecTool` | 代码执行工具（正常/异常/超时） |
| ② | `TestFileTool` | 文件读写工具（读写/覆盖/自动建目录） |
| ③ | `TestRepoTool` | 工作区扫描（入口定位/回退逻辑） |
| ④ | `TestRouting` | 条件路由逻辑（纯单元，无 LLM 依赖） |
| ⑤ | `TestFullPipeline` | 完整流程（Mock LLM，无需真实 API Key） |

---

## 配置说明

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `agent.provider` | `dashscope` | LLM 提供商 |
| `agent.model` | `qwen3-max` | 模型名称 |
| `agent.temperature` | `0` | 生成温度（建议保持 0 以确保稳定性） |
| `agent.max_retry` | `5` | 最大重试次数 |
| `workspace.path` | `workspace` | 目标代码目录 |
| `workspace.entry_file` | `main.py` | 默认入口文件名 |
| `workspace.timeout` | `30` | 代码执行超时（秒） |
| `workspace.python_executable` | `python3` | Python 解释器路径 |
