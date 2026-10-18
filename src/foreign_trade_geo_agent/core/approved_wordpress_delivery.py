"""Stable input for one explicitly approved WordPress draft delivery."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .content_draft import MAX_TITLE_CHARS
from .history import validate_uuid
from .wordpress_draft import normalize_wordpress_https_url


_DRAFT_ID_PATTERN = re.compile(r"D[1-9][0-9]*")


class ApprovedWordPressDraftDeliveryValidationError(ValueError):
    """A deterministic local validation failure before WordPress delivery."""


@dataclass(frozen=True, slots=True)
class ApprovedWordPressDraftDeliveryRequest:
    planning_run_id: str
    content_draft_artifact_id: str
    draft_id: str
    target_site_url: str
    title_override: str | None = None

    def __post_init__(self) -> None:
        try:
            validate_uuid(self.planning_run_id, "planning_run_id")
            validate_uuid(
                self.content_draft_artifact_id,
                "content_draft_artifact_id",
            )
        except ValueError:
            raise ApprovedWordPressDraftDeliveryValidationError(
                "Approved WordPress delivery identifiers are invalid."
            ) from None
        if (
            type(self.draft_id) is not str
            or _DRAFT_ID_PATTERN.fullmatch(self.draft_id) is None
        ):
            raise ApprovedWordPressDraftDeliveryValidationError(
                "Approved content draft ID is invalid."
            )
        if normalize_wordpress_https_url(self.target_site_url) is None:
            raise ApprovedWordPressDraftDeliveryValidationError(
                "Target WordPress URL is invalid."
            )
        if self.title_override is not None:
            if (
                type(self.title_override) is not str
                or not self.title_override.strip()
                or len(self.title_override.strip()) > MAX_TITLE_CHARS
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in self.title_override
                )
            ):
                raise ApprovedWordPressDraftDeliveryValidationError(
                    "WordPress title override is invalid."
                )
            object.__setattr__(self, "title_override", self.title_override.strip())
