FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY agent /app/agent
COPY rag /app/rag
COPY mcp /app/mcp
COPY worker /app/worker
COPY infra/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir --no-deps .
COPY data /app/data
ENV PYTHONUNBUFFERED=1 DATA_DIR=/app/data MCP_HOST=0.0.0.0 MCP_PORT=8000
RUN mkdir -p /state && chown 65534:65534 /state
USER 65534:65534
HEALTHCHECK --interval=5s --timeout=5s --retries=20 CMD python -c "import os,urllib.request; r=urllib.request.Request('http://localhost:'+os.getenv('MCP_PORT','8000')+'/health',headers={'Authorization':'Bearer '+os.getenv('MCP_TOKEN','replace-this-local-mcp-token')}); urllib.request.urlopen(r,timeout=3)"
CMD ["python", "-m", "unlockops_worker"]
