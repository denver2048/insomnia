"""
Post Insomnia investigation results to Jira (ITSM) via Jira Cloud REST API v3.

Uses the same credentials as Jira MCP (JIRA_BASE_URL, JIRA_USERNAME, JIRA_API_TOKEN).
MCP tools are read-oriented; writes use REST.

When INSOMNIA_JIRA_ITSM_NOTIFY_ENABLED is true:
- If the alert has label/annotation jira_issue / jira_key / issue_key → add a comment on that issue.
- Else if JIRA_ITSM_PROJECT_KEY is set → create an issue in that project with the report in the description.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from tools.jira_mcp import jira_credentials_configured, jira_issue_key_from_alert

logger = logging.getLogger(__name__)


def jira_itsm_notify_enabled() -> bool:
    v = os.getenv("INSOMNIA_JIRA_ITSM_NOTIFY_ENABLED", "false").strip().lower()
    return v in ("1", "true", "yes")


def _base_url() -> str:
    return os.environ["JIRA_BASE_URL"].strip().rstrip("/")


def _itsm_project_key() -> Optional[str]:
    k = os.getenv("JIRA_ITSM_PROJECT_KEY", "").strip()
    return k or None


def _itsm_issue_type() -> str:
    return os.getenv("JIRA_ITSM_ISSUE_TYPE", "Task").strip() or "Task"


def _jira_host_for_log() -> str:
    """Hostname from JIRA_BASE_URL for logs (no credentials)."""
    raw = os.getenv("JIRA_BASE_URL", "").strip()
    if not raw:
        return "(unset)"
    try:
        netloc = urlparse(raw).netloc
        return netloc or raw[:80]
    except Exception:
        return raw[:80]


def _build_notification_adf(alert: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    labels = alert.get("labels") or {}
    ns = str(labels.get("namespace", ""))
    pod = str(labels.get("pod", ""))
    alertname = str(labels.get("alertname", ""))
    report = result.get("report")
    report = "" if report is None else str(report)
    if len(report) > 32000:
        report = report[:32000] + "\n…(truncated)"

    meta = f"Namespace: {ns}\nPod: {pod}\nAlert: {alertname}"
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Insomnia investigation"}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": meta}],
            },
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Report"}],
            },
            {
                "type": "codeBlock",
                "attrs": {"language": "text"},
                "content": [{"type": "text", "text": report or "(no report text)"}],
            },
        ],
    }


def _session() -> requests.Session:
    user = os.environ["JIRA_USERNAME"].strip()
    token = os.environ["JIRA_API_TOKEN"].strip()
    s = requests.Session()
    s.auth = (user, token)
    s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    return s


def _post_comment(session: requests.Session, issue_key: str, adf: dict[str, Any]) -> None:
    url = f"{_base_url()}/rest/api/3/issue/{issue_key}/comment"
    logger.info(
        "ITSM: POST comment on Jira issue %s (host=%s)",
        issue_key,
        _jira_host_for_log(),
    )
    r = session.post(url, json={"body": adf}, timeout=60)
    if not r.ok:
        logger.error(
            "ITSM: comment on %s failed: HTTP %s %s",
            issue_key,
            r.status_code,
            r.text[:4000],
        )
        r.raise_for_status()
    logger.info("ITSM: success — added comment on Jira issue %s (HTTP %s)", issue_key, r.status_code)


def _create_issue(session: requests.Session, summary: str, adf: dict[str, Any]) -> None:
    project = _itsm_project_key()
    if not project:
        return
    itype = _itsm_issue_type()
    payload = {
        "fields": {
            "project": {"key": project},
            "summary": summary[:254],
            "description": adf,
            "issuetype": {"name": itype},
        }
    }
    url = f"{_base_url()}/rest/api/3/issue"
    logger.info(
        "ITSM: POST create issue project=%s issuetype=%s host=%s summary=%s",
        project,
        itype,
        _jira_host_for_log(),
        summary[:120],
    )
    r = session.post(url, json=payload, timeout=60)
    if not r.ok:
        logger.error(
            "ITSM: create issue in project %s failed: HTTP %s %s",
            project,
            r.status_code,
            r.text[:4000],
        )
        r.raise_for_status()
    key = (r.json() or {}).get("key", "?")
    logger.info("ITSM: success — created Jira issue %s (HTTP %s)", key, r.status_code)


def notify_jira_itsm_sync(alert: dict[str, Any], result: dict[str, Any]) -> None:
    """Post investigation to Jira (comment or new issue). Runs synchronously (use from asyncio.to_thread)."""
    if result is None or not isinstance(result, dict):
        result = {}
    if not jira_itsm_notify_enabled():
        logger.info(
            "ITSM: skip — INSOMNIA_JIRA_ITSM_NOTIFY_ENABLED is not true; "
            "enable Helm values jira.itsmNotify and jira.enabled (or itsmNotify) so the Deployment sets this env."
        )
        return
    if not jira_credentials_configured():
        logger.warning(
            "ITSM: skip — Jira credentials missing from env "
            "(need JIRA_BASE_URL, JIRA_USERNAME, JIRA_API_TOKEN; mount secret insomnia-jira or equivalent).",
        )
        return

    labels = alert.get("labels") or {}
    ns = str(labels.get("namespace", "?"))
    pod = str(labels.get("pod", "?"))
    an = str(labels.get("alertname", ""))
    report_len = len(str(result.get("report") or ""))
    issue_key = jira_issue_key_from_alert(alert)
    project = _itsm_project_key()

    logger.info(
        "ITSM: start — host=%s namespace=%s pod=%s alertname=%s report_chars=%s mode=%s project=%s issue_key=%s",
        _jira_host_for_log(),
        ns,
        pod,
        an,
        report_len,
        "comment" if issue_key else "create_issue",
        project or "(none)",
        issue_key or "(new issue)",
    )

    adf = _build_notification_adf(alert, result)
    session = _session()

    if issue_key:
        _post_comment(session, issue_key, adf)
        return

    if not project:
        logger.warning(
            "ITSM: skip — no jira_issue/jira_key on alert and JIRA_ITSM_PROJECT_KEY unset; "
            "set Helm jira.itsmProjectKey (default in chart is KAN) or add label/annotation jira_issue to the alert."
        )
        return

    summary = f"[Insomnia] {an} {ns}/{pod}".strip()[:254]
    _create_issue(session, summary, adf)


async def notify_jira_itsm_async(alert: dict[str, Any], result: dict[str, Any]) -> None:
    await asyncio.to_thread(notify_jira_itsm_sync, alert, result)
