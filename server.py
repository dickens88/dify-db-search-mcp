"""
Dify Database Search MCP Server

A standalone MCP tool that connects to Dify's PostgreSQL database
and performs fuzzy search across credential/config tables.
"""

import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass

import asyncpg
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Mount

# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------

@dataclass
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


_pool: asyncpg.Pool | None = None


async def get_pool(cfg: DbConfig) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            min_size=1,
            max_size=5,
        )
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

@asynccontextmanager
async def server_lifespan(server: FastMCP):
    """Manage connection pool lifecycle."""
    yield
    await close_pool()


mcp = FastMCP(
    "Dify DB Search",
    instructions="Search Dify PostgreSQL for credentials and environment variables",
    host="0.0.0.0",
    port=8000,
    lifespan=server_lifespan,
)


def _get_db_config() -> DbConfig:
    """Build DbConfig from the server's initialization options."""
    import os

    return DbConfig(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_DATABASE", "dify"),
    )


def _format_rows(rows: list[asyncpg.Record], columns: list[str]) -> list[dict]:
    """Convert asyncpg records to list of dicts with selected columns."""
    results = []
    for row in rows:
        item = {}
        for col in columns:
            val = row[col]
            if isinstance(val, (dict, list)):
                item[col] = val
            else:
                item[col] = str(val) if val is not None else None
        results.append(item)
    return results


@mcp.tool()
async def search_dify_credentials(keyword: str) -> str:
    """
    根据关键字模糊搜索 Dify 数据库中的凭据和环境变量配置。
    Args:
        keyword: 用于模糊搜索的关键字
    """
    cfg = _get_db_config()
    pool = await get_pool(cfg)

    pattern = f"%{keyword}%"
    results: dict[str, list] = {}

    async with pool.acquire() as conn:
        # 1. provider_model_credentials
        rows = await conn.fetch(
            """
            SELECT provider_name, model_name, model_type, encrypted_config,
                   created_at, updated_at
            FROM provider_model_credentials
            WHERE encrypted_config ILIKE $1 OR credential_name ILIKE $1
            ORDER BY updated_at DESC
            LIMIT 50
            """,
            pattern,
        )
        results["provider_model_credentials"] = _format_rows(
            rows,
            ["provider_name", "model_name", "model_type", "encrypted_config",
             "created_at", "updated_at"],
        )

        # 2. tool_builtin_providers
        rows = await conn.fetch(
            """
            SELECT provider, encrypted_credentials,
                   created_at, updated_at
            FROM tool_builtin_providers
            WHERE encrypted_credentials ILIKE $1
            ORDER BY updated_at DESC
            LIMIT 50
            """,
            pattern,
        )
        results["tool_builtin_providers"] = _format_rows(
            rows,
            ["provider", "encrypted_credentials", "created_at", "updated_at"],
        )

        # 3. workflows (deduplicated by app_id, keep latest)
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (w.app_id)
                   w.app_id, w.environment_variables,
                   w.created_at, w.updated_at
            FROM workflows w
            WHERE w.environment_variables ILIKE $1
            ORDER BY w.app_id, w.updated_at DESC
            LIMIT 50
            """,
            pattern,
        )
        results["workflows"] = _format_rows(
            rows,
            ["app_id", "environment_variables", "created_at", "updated_at"],
        )

    # Build summary
    summary_parts = []
    for table, items in results.items():
        summary_parts.append(f"[{table}] 找到 {len(items)} 条记录")

    output = {
        "summary": " | ".join(summary_parts),
        "keyword": keyword,
        "results": results,
    }
    return json.dumps(output, ensure_ascii=False, default=str, indent=2)


@mcp.tool()
async def search_workflows_by_plugin(plugin_keyword: str) -> str:
    """
    根据 plugin（插件/工具）名称关键字，搜索哪些 workflow 使用了该 plugin。
    会在 workflow 的 graph 定义中搜索匹配的 tool 节点，并返回 workflow 名称和匹配的工具节点详情。
    Args:
        plugin_keyword: 用于模糊搜索 plugin 名称的关键字（如 google, dalle, wikipedia）
    """
    cfg = _get_db_config()
    pool = await get_pool(cfg)

    pattern = f"%{plugin_keyword}%"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (w.app_id)
                   w.app_id,
                   a.name AS app_name,
                   w.graph,
                   w.created_at,
                   w.updated_at
            FROM workflows w
            LEFT JOIN apps a ON a.id = w.app_id
            WHERE w.graph ILIKE $1
            ORDER BY w.app_id, w.updated_at DESC
            LIMIT 50
            """,
            pattern,
        )

    # Parse graph JSON and extract matching tool nodes
    keyword_lower = plugin_keyword.lower()
    results = []

    for row in rows:
        graph_str = row["graph"]
        if not graph_str:
            continue

        try:
            graph = json.loads(graph_str)
        except (json.JSONDecodeError, TypeError):
            continue

        nodes = graph.get("nodes", [])
        matching_tools = []

        for node in nodes:
            data = node.get("data", {})
            node_type = data.get("type", "")

            # Only look at tool nodes
            if node_type != "tool":
                continue

            provider_id = data.get("provider_id", "")
            tool_name = data.get("tool_name", "")

            # Check if the keyword matches provider_id or tool_name
            if (keyword_lower in provider_id.lower()
                    or keyword_lower in tool_name.lower()):
                matching_tools.append({
                    "node_id": node.get("id", ""),
                    "node_title": data.get("title", node.get("data", {}).get("title", "")),
                    "provider_id": provider_id,
                    "tool_name": tool_name,
                })

        if matching_tools:
            results.append({
                "app_id": str(row["app_id"]),
                "app_name": row["app_name"] or "",
                "matching_tools": matching_tools,
                "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
            })

    output = {
        "summary": f"找到 {len(results)} 个 workflow 使用了匹配 '{plugin_keyword}' 的 plugin",
        "keyword": plugin_keyword,
        "results": results,
    }
    return json.dumps(output, ensure_ascii=False, default=str, indent=2)


@mcp.tool()
async def search_workflows_by_llm(model_keyword: str) -> str:
    """
    根据大语言模型（LLM）名称关键字，搜索哪些 workflow 使用了该模型。
    会在 workflow 的 graph 定义中搜索匹配的 LLM 节点，并返回 workflow 名称和匹配的 LLM 节点详情。
    Args:
        model_keyword: 用于模糊搜索 LLM 模型名称的关键字（如 gpt-4, claude, deepseek, qwen）
    """
    cfg = _get_db_config()
    pool = await get_pool(cfg)

    pattern = f"%{model_keyword}%"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (w.app_id)
                   w.app_id,
                   a.name AS app_name,
                   w.graph,
                   w.created_at,
                   w.updated_at
            FROM workflows w
            LEFT JOIN apps a ON a.id = w.app_id
            WHERE w.graph ILIKE $1
            ORDER BY w.app_id, w.updated_at DESC
            LIMIT 50
            """,
            pattern,
        )

    # Parse graph JSON and extract matching LLM nodes
    keyword_lower = model_keyword.lower()
    results = []

    for row in rows:
        graph_str = row["graph"]
        if not graph_str:
            continue

        try:
            graph = json.loads(graph_str)
        except (json.JSONDecodeError, TypeError):
            continue

        nodes = graph.get("nodes", [])
        matching_llms = []

        for node in nodes:
            data = node.get("data", {})
            node_type = data.get("type", "")

            # Only look at LLM nodes
            if node_type != "llm":
                continue

            model_name = data.get("model", {}).get("name", "") if isinstance(data.get("model"), dict) else str(data.get("model", ""))
            provider = data.get("model", {}).get("provider", "") if isinstance(data.get("model"), dict) else str(data.get("provider", ""))

            # Check if the keyword matches model name or provider
            if (keyword_lower in model_name.lower()
                    or keyword_lower in provider.lower()):
                matching_llms.append({
                    "node_id": node.get("id", ""),
                    "node_title": data.get("title", ""),
                    "model": model_name,
                    "provider": provider,
                })

        if matching_llms:
            results.append({
                "app_id": str(row["app_id"]),
                "app_name": row["app_name"] or "",
                "matching_llms": matching_llms,
                "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
            })

    output = {
        "summary": f"找到 {len(results)} 个 workflow 使用了匹配 '{model_keyword}' 的 LLM 模型",
        "keyword": model_keyword,
        "results": results,
    }
    return json.dumps(output, ensure_ascii=False, default=str, indent=2)


# ---------------------------------------------------------------------------
# API Key Authentication Middleware
# ---------------------------------------------------------------------------

class APIKeyAuthMiddleware:
    """ASGI middleware that enforces Bearer token authentication."""

    def __init__(self, app):
        self.app = app
        self.api_key = os.environ.get("MCP_API_KEY", "")

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # If no API key is configured, skip authentication
        if not self.api_key:
            await self.app(scope, receive, send)
            return

        # Extract Authorization header
        headers = dict(scope.get("headers", []))
        auth_value = headers.get(b"authorization", b"").decode()

        if auth_value != f"Bearer {self.api_key}":
            response = JSONResponse(
                {"error": "Unauthorized", "message": "Invalid or missing API key"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Get the underlying SSE Starlette app from FastMCP
    mcp_sse_app = mcp.sse_app()

    # Wrap it with auth middleware
    app = Starlette(
        routes=[Mount("/", app=mcp_sse_app)],
        middleware=[Middleware(APIKeyAuthMiddleware)],
    )

    uvicorn.run(app, host="0.0.0.0", port=8000)
