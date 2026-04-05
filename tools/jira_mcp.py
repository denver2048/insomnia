"""
Jira MCP client: stdio transport to @timbreeding/jira-mcp-server (npx).

Requires Node/npm in the container/host (see Dockerfile). Configure with
JIRA_MCP_ENABLED=true and JIRA_BASE_URL, JIRA_USERNAME, JIRA_API_TOKEN.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

logger = logging.getLogger(__name__)

JIRA_MCP_NPX_PACKAGE = os.getenv(
    "JIRA_MCP_NPX_PACKAGE",
    "@timbreeding/jira-mcp-server@latest",
).strip()


def jira_credentials_configured() -> bool:
    return bool(
        os.getenv("JIRA_BASE_URL", "").strip()
        and os.getenv("JIRA_USERNAME", "").strip()
        and os.getenv("JIRA_API_TOKEN", "").strip()
    )


def jira_mcp_enabled() -> bool:
    val = os.getenv("JIRA_MCP_ENABLED", "false").strip().lower()
    return val in ("1", "true", "yes") and jira_credentials_configured()


def _tool_result_text(result: CallToolResult) -> str:
    parts: list[str] = []
    for block in result.content:
        if isinstance(block, TextContent):
            parts.append(block.text)
        else:
            parts.append(str(block))
    return "\n".join(parts) if parts else ""


async def fetch_jira_issue_via_mcp(issue_key: str) -> str:
    """
    Call the Jira MCP tool getJiraIssue for the given key.
    Raises on transport or tool errors.
    """
    base = os.environ["JIRA_BASE_URL"].strip()
    user = os.environ["JIRA_USERNAME"].strip()
    token = os.environ["JIRA_API_TOKEN"].strip()

    server_params = StdioServerParameters(
        command="npx",
        args=[
            "-y",
            JIRA_MCP_NPX_PACKAGE,
            f"--jira-base-url={base}",
            f"--jira-username={user}",
            f"--jira-api-token={token}",
        ],
        env={
            **os.environ,
            "NPM_CONFIG_UPDATE_NOTIFIER": "false",
            "NO_UPDATE_NOTIFIER": "1",
        },
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "getJiraIssue",
                arguments={"issueKey": issue_key},
            )
            if result.isError:
                raise RuntimeError(_tool_result_text(result) or "Jira MCP tool error")
            return _tool_result_text(result)


def jira_issue_key_from_alert(alert: dict[str, Any]) -> Optional[str]:
    """Resolve issue key from labels or annotations (jira_issue, jira_key, issue_key)."""
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    for key in ("jira_issue", "jira_key", "issue_key"):
        raw = labels.get(key) or annotations.get(key)
        if raw is not None:
            s = str(raw).strip()
            if s:
                return s
    return None
