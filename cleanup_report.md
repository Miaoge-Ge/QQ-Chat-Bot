## 概览

- 范围：`/opt/new_bot`（不修改 `.env`）
- 目标：减少上下文/运行时污染源（调试代码、pyc、静默吞异常）、提升可诊断性与配置集中度

## 修改文件列表

- 清理
  - [image_generate.py](file:///opt/new_bot/app/tools/builtin/image_generate.py)：删除 `print()` 调试输出；改为 `logger.opt(exception=True)`；补充更具体异常分支与 `CancelledError` 透传；修正潜在未定义变量风险
  - [history.py](file:///opt/new_bot/app/memory/history.py)：将 `json.loads` 的宽泛捕获改为 `json.JSONDecodeError`；读取失败时记录堆栈
- 修复
  - [client.py](file:///opt/new_bot/app/onebot/client.py)：完善 OneBot 调用异常处理（超时/断连/取消）；`_handle_message` 输出堆栈；修正缩进异常；本地图片 ingest 限制改为常量
  - [orchestrator.py](file:///opt/new_bot/app/runtime/orchestrator.py)：细化异常类型；对 `CancelledError` 透传；工具输出序列化异常更具体
  - [registry.py](file:///opt/new_bot/app/tools/registry.py)：工具失败返回加入 message，避免静默；`CancelledError` 透传
  - [openai_compat.py](file:///opt/new_bot/app/providers/openai_compat.py)：网络异常添加异常链 `raise ... from e`；schema/JSON 解析异常更具体并 debug 记录
- 优化
  - [config.py](file:///opt/new_bot/app/config.py)：NapCat onebot11.json 候选路径提取为常量；解析/读取异常更具体并 debug 记录
  - [sleep_state.py](file:///opt/new_bot/app/runtime/sleep_state.py)：睡眠状态读取异常改为更具体类型并记录 debug
  - [weather_query.py](file:///opt/new_bot/app/tools/builtin/weather_query.py)：网络异常捕获改为 `httpx.HTTPError` 并记录 debug；去除无意义的 `pass`
  - [web_search.py](file:///opt/new_bot/app/tools/builtin/web_search.py)：网络异常返回带 message，避免静默失败
  - [image_save.py](file:///opt/new_bot/app/tools/builtin/image_save.py)：文件/网络异常更具体（`OSError`/`httpx.HTTPError`）；补充类型注解
  - [time_now.py](file:///opt/new_bot/app/tools/builtin/time_now.py)：`ZoneInfoNotFoundError` 更具体捕获；补充类型注解
- 配置/依赖
  - [constants.py](file:///opt/new_bot/app/constants.py)：新增集中常量（NapCat 配置候选路径、最大图片 ingest 大小、常用图片扩展名）
  - [requirements.txt](file:///opt/new_bot/requirements.txt)：补充 `openai` 依赖（`image_generate` 使用）

## 删除项列表

- 删除 `__pycache__/` 与 `*.pyc`
  - 原因：生成文件会污染仓库与 diff；且会造成“行为看似变化但实际是缓存”的排障噪音
  - 处理：已删除工作区中 `app/**/__pycache__/*.pyc` 与根目录 `__pycache__/*.pyc`

## 潜在风险（发现但未完全修复）

- 代码风格统一（单引号/88 字符/全量 isort/black）尚未对全项目做一次性格式化：当前以“关键路径最小改动”为主，避免引入大范围 diff 风险
- 仍存在部分 `except Exception`（多用于“容错分支/兜底”）：后续可以继续细化到更具体异常并按模块制定策略（返回错误 vs raise）
- NapCat 路径候选仍包含 `/opt/...`：已集中到常量，但不同部署环境建议提供可配置覆盖项（环境变量/配置文件）

## 性能优化点

- 删除大量 `pyc`：减少 IO 噪音与仓库体积，避免误差异
- 工具/网络异常更可诊断：减少重复重试与“盲排查”时间成本

## 建议后续

- 增加自动化质量工具（建议加入 CI 或 pre-commit）
  - `ruff`：未使用 import、异常类型、简化表达式、格式化（可替代一部分 isort/pyflakes）
  - `black`：统一格式（注意它默认偏好双引号；若你坚持单引号，可用 ruff-format 或不启用该条）
  - `mypy`：类型检查（可以先从 `app/tools/*` 的 handler 开始）
  - `pytest`：为 OneBot 消息拼接、睡眠逻辑、图片工具等关键路径加回归测试

