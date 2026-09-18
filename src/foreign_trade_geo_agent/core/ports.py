"""Ports implemented by external site-audit providers."""

from typing import Protocol

from .audit import SiteAuditResult


class SiteAuditor(Protocol):
    """Provider-independent site-audit boundary used by workflows."""

    def audit_site(self, url: str) -> SiteAuditResult:
        """Audit one public website URL."""
        ...
