"""
Optional Jira enrichment (parity with testhide-pytest-plugin) so offline/air-gapped
agents work without the server. Looks up an issue by ``fail_id`` (used as a label) and
maps its status to a Testhide ``test_resolution``.

The ``jira`` package is imported lazily — it is an optional dependency
(``pip install testhide-unittest-plugin[jira]``); without it, enrichment is a no-op.
"""
from __future__ import annotations

from typing import Optional, Tuple


class JiraHelper:
    def __init__(self, url: str, username: str, password: str, label_field: str = "labels"):
        self._client = None
        self._ok = False
        try:
            from jira import JIRA  # type: ignore

            self._client = JIRA(server=url, basic_auth=(username, password))
            self._label_field = label_field
            self._ok = True
        except Exception:
            # Missing dependency or auth/connectivity failure — degrade to no-op.
            self._ok = False

    @property
    def available(self) -> bool:
        return self._ok

    def enrich(self, fail_id: str) -> Optional[Tuple[str, str, str]]:
        """
        Return (test_resolution, jira_reference, enriched_message) for a fail_id, or None.

        Resolution mapping mirrors the pytest plugin:
          - status Done/Closed/Resolved with a fixVersion -> "Resolved in branch"
          - status Done/Closed/Resolved without fixVersion -> "Verified at Branch"
          - reopened/to-do after being resolved          -> "Need to reopen"
          - otherwise                                     -> "Known Issue"
        """
        if not self._ok or not fail_id:
            return None
        try:
            issues = self._client.search_issues(  # type: ignore[union-attr]
                'labels = "%s" ORDER BY updated DESC' % fail_id, maxResults=1
            )
            if not issues:
                return None
            issue = issues[0]
            status = (issue.fields.status.name or "").lower()
            has_fix = bool(getattr(issue.fields, "fixVersions", None))
            if status in ("done", "closed", "resolved"):
                resolution = "Resolved in branch" if has_fix else "Verified at Branch"
            elif status in ("reopened", "to do", "open"):
                resolution = "Need to reopen"
            else:
                resolution = "Known Issue"
            summary = getattr(issue.fields, "summary", "") or ""
            ref = "%s %s [%s]" % (issue.key, resolution, summary)
            return resolution, ref, "%s: %s" % (issue.key, summary)
        except Exception:
            return None
