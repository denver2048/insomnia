FROM python:3.11-slim

WORKDIR /app

# Jira MCP runs via npx (@timbreeding/jira-mcp-server); Node 22 matches package engines.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
  && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]