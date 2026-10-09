# Personal English Agent（Demo）

围绕真实 GAP 的个人英语学习工具。理念与需求见 [docs/Personal_English_Agent_理念与需求说明.md](docs/Personal_English_Agent_理念与需求说明.md)，技术方案见 [docs/技术方案_v0.md](docs/技术方案_v0.md)。

当前 demo 只实现**截图提问**这一个入口：

**发截图 + 疑问 → AI 当场讲解、可追问 → 点「记录」提炼 GAP（带原图）→ GAP 列表 / 翻卡复习 / 按模板导出**

## 运行

需要 Python 3.12+。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env          # 然后编辑 .env，配置模型
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

电脑浏览器打开 <http://127.0.0.1:8000>。

**手机访问**：手机和电脑连同一个 WiFi，打开 `http://<电脑的局域网 IP>:8000`（在 PowerShell 运行 `ipconfig` 查看 IPv4 地址）。第一次启动时，Windows 防火墙会询问是否允许 Python 访问网络，选择允许“专用网络”。

## 配置模型

编辑 `.env`。模型名使用 [LiteLLM](https://docs.litellm.ai/docs/providers) 格式 `<厂商>/<模型>`，**模型必须支持看图**。

| 厂商 | 配置示例 |
|---|---|
| 演示模式 | `LLM_MODEL=mock`（默认，AI 回复为假数据，用于试流程） |
| Claude | `LLM_MODEL=anthropic/claude-sonnet-5-5`，`LLM_API_KEY=sk-ant-...` |
| 通义千问 | `LLM_MODEL=openai/qwen-vl-max`，`LLM_API_KEY=sk-...`，`LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 其他 OpenAI 兼容接口 | `LLM_MODEL=openai/<模型名>` + `LLM_API_KEY` + `LLM_API_BASE` |

修改后重启服务生效。

## 测试

```powershell
.\.venv\Scripts\python -m pytest -q
```

测试使用演示模式，不调用真实模型。

## 目录

```text
app/
  main.py        接口：对话、记录、GAP、复习、导出
  prompts.py     讲解与 GAP 提炼的提示词（调教 AI 行为主要改这里）
  extract.py     “记录”流程：提炼 GAP 并与已有 GAP 合并
  llm.py         模型适配层（LiteLLM）与演示模式
  models.py      数据模型
  export.py      模板导出；模板在 app/templates/
static/          手机优先的单页前端（原生 JS）
data/            本地数据库与上传的截图（不进 git）
```

## Demo 的已知限制

- 没有登录，单用户；只能在本地或局域网使用。
- 只有截图入口；文字对话、语音、课程入口尚未实现。
- AI 回复不是流式输出，需要等模型完整回答。
