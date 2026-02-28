# new_bot（Python）

一个可扩展的 QQ 聊天机器人：
- 通过 NapCat（OneBot v11 WebSocket）与 QQ 连接，收发消息
- 通过 OpenAI 兼容 HTTP 接口完成模型调用
- 支持工具调用、记忆、skill

## 运行

### 1) 安装依赖

```bash
cd /opt/new_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) 配置

```bash
cp .env.example .env
```

最关键的配置：
- OneBot：`ONEBOT_WS_URL`、`ONEBOT_ACCESS_TOKEN`
- 模型：
  - OpenAI 兼容：`OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL`

### 3) 启动

```bash
python main.py
```

## 工具

每个工具一个文件：`app/tools/builtin/*.py`
- `image_generate` 图像生成
- `image_understand` 图像理解
- `web_search` 网络查询
- `time_now` 时间查询
- `model_name` 当前模型名称

## Skills

skills 位于 `skills/`，每个 skill 一个目录，包含 `skill.json`：
- `name` / `version`
- `system_prompt`（可选）
- `enabled_tools`（可选）
