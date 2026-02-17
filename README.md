# Dify DB Search MCP

一个连接到 Dify PostgreSQL 数据库的 MCP 工具，可根据关键字模糊搜索凭据和环境变量配置。

## 搜索范围

| 表名 | 搜索字段 | 返回字段 |
|------|---------|---------|
| `provider_model_credentials` | `provider_name`, `model_name` | `encrypted_config` |
| `tool_builtin_providers` | `provider` | `encrypted_credentials` |
| `workflows` | `environment_variables` | `app_id`, `environment_variables`（按 `app_id` 去重） |

## Docker 部署

### 1. 构建镜像

```bash
docker build -t dify-db-search-mcp .
```

### 2. 启动容器

服务使用 SSE 传输协议，暴露 `8000` 端口，适合作为持久化服务运行。

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
> - `DB_HOST=db_postgres`：Dify 默认的 PostgreSQL 容器别名，如果你的环境不同请自行修改。

### 3. 在 Dify 中连接

1. 进入 Dify → **工具 (Tools)** → **MCP** 标签页
2. 点击 **Add MCP Server (HTTP)**
3. 填写配置：

| 字段 | 值 |
|------|-----|
| Server URL | `http://dify-db-search-mcp:8000/sse` |
| Name | `Dify DB Search` |
| Server Identifier | `dify-db-search` |

4. 保存后 Dify 会自动发现 `search_dify_credentials` 工具
5. 在 Agent 或 Workflow 中选择该工具即可使用

### 环境变量

| 变量 | 默认值 | 说明 |
|------|-------|------|
| `DB_HOST` | `localhost` | PostgreSQL 主机地址 |
| `DB_PORT` | `5432` | PostgreSQL 端口 |
| `DB_USER` | `postgres` | 数据库用户名 |
| `DB_PASSWORD` | (空) | 数据库密码 |
| `DB_DATABASE` | `dify` | 数据库名 |

### 常用运维命令

```bash
# 查看日志
docker logs -f dify-db-search-mcp

# 重启
docker restart dify-db-search-mcp

# 停止并删除
docker stop dify-db-search-mcp && docker rm dify-db-search-mcp

# 重新构建并部署
docker stop dify-db-search-mcp && docker rm dify-db-search-mcp
docker build -t dify-db-search-mcp .
docker run -d --name dify-db-search-mcp --restart unless-stopped \
  --network docker_default -p 8000:8000 \
  -e DB_HOST=db_postgres -e DB_PORT=5432 \
  -e DB_USER=postgres -e DB_PASSWORD=your_password \
  -e DB_DATABASE=dify \
  dify-db-search-mcp
```

## 本地开发

```bash
# 安装依赖
pip install -e .

# 运行（stdio 模式）
python server.py
```
