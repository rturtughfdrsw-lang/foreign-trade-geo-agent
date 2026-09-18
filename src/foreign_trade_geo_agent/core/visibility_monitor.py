"""Deterministic AI visibility analysis and aggregation."""

from collections.abc import Sequence
from datetime import datetime, timezone

from .ports import VisibilityProvider
from .visibility import (
    ResponseStatus,
    VisibilityObservation,
    VisibilityReport,
)


def mentions_entity(text: str, entity: str) -> bool:
    """Match a literal entity using case-insensitive alphanumeric boundaries.

    Unlike ``\b``, checking the characters outside the complete literal works
    for names containing punctuation, such as ``C++``, ``.NET`` and
    ``B2B-Tech``. A short name such as ``AI`` therefore matches ``AI tools``
    but not the letters inside ``said``.
    """

    normalized_entity = entity.strip().casefold()
    if not normalized_entity:
        raise ValueError("Entity names must not be empty.")

    normalized_text = text.casefold()
    search_from = 0
    while True:
        start = normalized_text.find(normalized_entity, search_from)
        if start == -1:
            return False

        end = start + len(normalized_entity)
        left_is_boundary = start == 0 or not normalized_text[start - 1].isalnum()
        right_is_boundary = end == len(normalized_text) or not normalized_text[end].isalnum()
        if left_is_boundary and right_is_boundary:
            return True

        search_from = start + 1


class VisibilityMonitor:
    """Run a deterministic prompt-by-provider visibility measurement."""

    async def run(
        self,
        *,
        target_brand: str,
        competitor_names: Sequence[str],
        prompts: Sequence[str],
        providers: Sequence[VisibilityProvider],
    ) -> VisibilityReport:
        canonical_target = target_brand.strip()
        if not canonical_target:
            raise ValueError("Target brand must not be empty.")

        competitors = self._canonical_competitors(competitor_names)
        observations: list[VisibilityObservation] = []

        for prompt in prompts:
            for provider in providers:
                response = await provider.generate(prompt)
                observed_at = datetime.now(timezone.utc)

                if response.status is ResponseStatus.FAILED:
                    observations.append(
                        VisibilityObservation(
                            prompt=prompt,
                            provider=response.provider,
                            model=response.model,
                            response=response,
                            target_mentioned=None,
                            mentioned_competitors=(),
                            timestamp=observed_at,
                        )
                    )
                    continue

                answer = response.text
                if answer is None:
                    raise TypeError("A successful provider response must contain text.")

                mentioned_competitors = tuple(
                    competitor
                    for competitor in competitors
                    if mentions_entity(answer, competitor)
                )
                observations.append(
                    VisibilityObservation(
                        prompt=prompt,
                        provider=response.provider,
                        model=response.model,
                        response=response,
                        target_mentioned=mentions_entity(answer, canonical_target),
                        mentioned_competitors=mentioned_competitors,
                        timestamp=observed_at,
                    )
                )

        return self._build_report(canonical_target, competitors, observations)

    @staticmethod
    def _canonical_competitors(competitor_names: Sequence[str]) -> tuple[str, ...]:
        competitors: list[str] = []
        seen: set[str] = set()
        for competitor_name in competitor_names:
            competitor = competitor_name.strip()
            if not competitor:
                raise ValueError("Competitor names must not be empty.")
            identity = competitor.casefold()
            if identity not in seen:
                competitors.append(competitor)
                seen.add(identity)
        return tuple(competitors)

    @staticmethod
    def _build_report(
        target_brand: str,
        competitors: tuple[str, ...],
        observations: list[VisibilityObservation],
    ) -> VisibilityReport:
        successful = tuple(
            observation
            for observation in observations
            if observation.response.status is ResponseStatus.SUCCESS
        )
        failed_count = len(observations) - len(successful)
        mentioned_count = sum(
            observation.target_mentioned is True for observation in successful
        )
        mention_rate = mentioned_count / len(successful) if successful else None

        competitor_counts = {
            competitor: sum(
                competitor in observation.mentioned_competitors
                for observation in successful
            )
            for competitor in competitors
        }
        competitor_rates = {
            competitor: count / len(successful) if successful else None
            for competitor, count in competitor_counts.items()
        }
        citation_count = sum(
            len(observation.response.citations) for observation in successful
        )

        return VisibilityReport(
            target_brand=target_brand,
            total_attempts=len(observations),
            successful_observations=len(successful),
            failed_observations=failed_count,
            mentioned_count=mentioned_count,
            mention_rate=mention_rate,
            competitor_mention_counts=competitor_counts,
            competitor_mention_rates=competitor_rates,
            citation_count=citation_count,
            observations=tuple(observations),
        )
