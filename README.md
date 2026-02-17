# Dify DB Search MCP

一个连接到 Dify PostgreSQL 数据库的 MCP 工具，可根据关键字模糊搜索凭据、环境变量以及 Workflow 插件/模型的使用情况。

## 核心功能

本工具由于直接连接 Dify 数据库，可以快速检索以下信息：

- **凭据搜索**：查找模型供应商密钥和工具凭据。
- **环境变两搜索**：查找 Workflow 中配置的各种环境变量。
- **插件溯源**：查找哪些 Workflow 使用了特定的插件工具（如 Google Search, DALL·E）。
- **模型溯源**：查找哪些 Workflow 使用了特定的 LLM 模型（如 GPT-4, DeepSeek）。

## 搜索范围

| 功能 | 搜索对象 | 搜索字段 |
|------|---------|---------|
| **凭据搜索** | 模型/工具凭据 | `provider_name`, `provider`, `model_name` |
| **环境变量** | Workflow 变量 | `workflows.environment_variables` |
| **插件搜索** | Workflow 插件使用 | `workflows.graph` (Tool Nodes) |
| **模型搜索** | Workflow 模型使用 | `workflows.graph` (LLM Nodes) |

## 可用工具 (Tools)

1. `search_dify_credentials(keyword)`: 搜索 Dify 数据库中的凭据和环境变量配置。
2. `search_workflows_by_plugin(plugin_keyword)`: 搜索哪些 Workflow 使用了该插件及其具体节点。
3. `search_workflows_by_llm(model_keyword)`: 搜索哪些 Workflow 使用了该 LLM 模型及其具体节点。

## Docker 部署

### 1. 构建镜像

```bash
docker build -t dify-db-search-mcp .
```

### 2. 启动容器

服务使用 SSE 传输协议，暴露 `8000`端口，适合作为持久化服务运行。

```bash
docker run -d \
  --name dify-db-search-mcp \
  --restart unless-stopped \
  --network docker_default \
  -p 8000:8000 \
  -e DB_HOST=db_postgres \
  -e DB_PORT=5432 \
  -e DB_USER=postgres \
  -e DB_PASSWORD=your_password \
  -e DB_DATABASE=dify \
  dify-db-search-mcp
```

> **说明**：
> - `--network docker_default`：与 Dify 的 Docker 网络保持一致，确保可以通过容器名访问数据库。
> - `DB_HOST=db_postgres`：Dify 默认的 PostgreSQL 容器别名。

### 3. 在 Dify 中连接

1. 进入 Dify → **工具 (Tools)** → **MCP** 标签页
2. 点击 **Add MCP Server (HTTP)**
3. 填写配置：
   - **Server URL**: `http://dify-db-search-mcp:8000/sse`
   - **Name**: `Dify DB Search`
4. 保存后 Dify 会自动发现所有可用工具。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|-------|------|
| `DB_HOST` | `localhost` | PostgreSQL 主机地址 |
| `DB_PORT` | `5432` | PostgreSQL 端口 |
| `DB_USER` | `postgres` | 数据库用户名 |
| `DB_PASSWORD` | (空) | 数据库密码 |
| `DB_DATABASE` | `dify` | 数据库名 |
| `MCP_API_KEY` | (空) | 如果设置，则启用 Bearer Token 认证 |

## 本地开发

```bash
# 安装依赖
pip install -e .

# 运行（标准模式）
python server.py
```
