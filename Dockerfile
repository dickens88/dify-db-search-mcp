FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e . 2>/dev/null || pip install --no-cache-dir "mcp[cli]>=1.0.0" "asyncpg>=0.29.0" "uvicorn>=0.30.0"

COPY server.py .

# Database connection params — override these at runtime
ENV DB_HOST=localhost
ENV DB_PORT=5432
ENV DB_USER=postgres
ENV DB_PASSWORD=""
ENV DB_DATABASE=dify

# API Key for authentication (leave empty to disable auth)
ENV MCP_API_KEY=""

EXPOSE 8000

# MCP server runs with SSE transport on port 8000
ENTRYPOINT ["python", "server.py"]
