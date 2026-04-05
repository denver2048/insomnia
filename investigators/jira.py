import logging

from tools.jira_mcp import (
    fetch_jira_issue_via_mcp,
    jira_issue_key_from_alert,
    jira_mcp_enabled,
)

logger = logging.getLogger(__name__)


async def jira_investigator(state: dict) -> dict:
    """
    When Jira MCP is enabled and the alert carries a Jira issue key, fetch issue text via MCP.
    """
    alert = state.get("alert") or {}

    if not jira_mcp_enabled():
        state["jira"] = {"skipped": "jira_mcp_disabled_or_unconfigured"}
        return state

    issue_key = jira_issue_key_from_alert(alert)
    if not issue_key:
        state["jira"] = {"skipped": "no_issue_key_in_labels_or_annotations"}
        return state

    logger.info("Step: jira investigator → MCP getJiraIssue %s", issue_key)
    try:
        details = await fetch_jira_issue_via_mcp(issue_key)
        state["jira"] = {"issue_key": issue_key, "details": details}
    except Exception as e:
        logger.exception("Step: jira investigator → MCP failed for %s", issue_key)
        state["jira"] = {"issue_key": issue_key, "error": str(e)}

    return state
