"""Adapter for the geo-optimizer-skill Python API."""

from collections.abc import Callable, Mapping
from typing import Any

from foreign_trade_geo_agent.core.audit import AuditStatus, SiteAuditResult


AuditCallable = Callable[[str], Any]


def _load_default_audit() -> tuple[AuditCallable, str]:
    import geo_optimizer

    return geo_optimizer.audit, geo_optimizer.__version__


class GeoOptimizerAdapter:
    """Translate geo-optimizer results into the application's core model."""

    source = "geo-optimizer-skill"

    def __init__(
        self,
        audit_func: AuditCallable | None = None,
        source_version: str | None = None,
    ) -> None:
        if audit_func is None:
            audit_func, installed_version = _load_default_audit()
            source_version = source_version or installed_version

        self._audit_func = audit_func
        self._source_version = source_version or "unknown"

    def audit_site(self, url: str) -> SiteAuditResult:
        try:
            provider_result = self._audit_func(url)
        except Exception as exc:
            message = str(exc) or "no exception message"
            return self._failed_result(
                url=url,
                error=f"{self.source} raised {type(exc).__name__}: {message}",
            )

        result_url = self._require_str(getattr(provider_result, "url"), "url")
        provider_error = getattr(provider_result, "error")
        if provider_error is not None:
            error = self._require_str(provider_error, "error")
            error = error or f"{self.source} returned an unspecified error"
            return self._failed_result(url=result_url, error=error)

        score = self._require_int(getattr(provider_result, "score"), "score")
        band = self._require_str(getattr(provider_result, "band"), "band")
        score_breakdown = self._copy_score_breakdown(
            getattr(provider_result, "score_breakdown")
        )
        recommendations = self._copy_recommendations(
            getattr(provider_result, "recommendations")
        )

        return SiteAuditResult(
            url=result_url,
            status=AuditStatus.SUCCESS,
            score=score,
            band=band,
            score_breakdown=score_breakdown,
            recommendations=recommendations,
            error=None,
            source=self.source,
            source_version=self._source_version,
        )

    def _failed_result(self, url: str, error: str) -> SiteAuditResult:
        return SiteAuditResult(
            url=url,
            status=AuditStatus.FAILED,
            score=None,
            band=None,
            score_breakdown={},
            recommendations=(),
            error=error,
            source=self.source,
            source_version=self._source_version,
        )

    @staticmethod
    def _copy_score_breakdown(value: Mapping[object, object]) -> dict[str, int]:
        if not isinstance(value, Mapping):
            raise TypeError("geo-optimizer score_breakdown must be a mapping.")

        copied: dict[str, int] = {}
        for key, score in value.items():
            if type(key) is not str or type(score) is not int:
                raise TypeError(
                    "geo-optimizer score_breakdown must map strings to integers."
                )
            copied[key] = score
        return copied

    @staticmethod
    def _copy_recommendations(value: object) -> tuple[str, ...]:
        if not isinstance(value, list) or any(type(item) is not str for item in value):
            raise TypeError("geo-optimizer recommendations must be a list of strings.")
        return tuple(value)

    @staticmethod
    def _require_int(value: object, field_name: str) -> int:
        if type(value) is not int:
            raise TypeError(f"geo-optimizer {field_name} must be an integer.")
        return value

    @staticmethod
    def _require_str(value: object, field_name: str) -> str:
        if type(value) is not str:
            raise TypeError(f"geo-optimizer {field_name} must be a string.")
        return value
