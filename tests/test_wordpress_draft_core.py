import unittest
from dataclasses import fields

from foreign_trade_geo_agent.core.change_plan import (
    ChangeTargetKind,
    SectionLocator,
    SectionLocatorKind,
)
from foreign_trade_geo_agent.core.content_draft import (
    BulletListBlock,
    ComparisonTableBlock,
    ContentDraftType,
    DraftBlockKind,
    DraftClaim,
    DraftClaimSupportKind,
    DraftClaimType,
    DraftItem,
    InternalLinkBlock,
    ParagraphBlock,
    TableCell,
)
from foreign_trade_geo_agent.core.wordpress_draft import (
    WordPressDraftFailureKind,
    WordPressDraftRequest,
    WordPressDraftResult,
    WordPressDraftStatus,
    WordPressDraftValidationError,
    build_wordpress_draft_request,
)


def _claim(text: str, number: int = 1) -> DraftClaim:
    return DraftClaim(
        claim_id=f"CL{number}",
        text=text,
        claim_type=DraftClaimType.GENERAL_TECHNICAL_CONTEXT,
        support_kind=DraftClaimSupportKind.EXTERNAL_CONTEXT,
        page_refs=(),
        source_refs=("S1",),
    )


def _draft(*blocks, heading: str | None = "Buyer Guide") -> DraftItem:
    return DraftItem(
        draft_id="D1",
        change_ref="C1",
        opportunity_ref="R1",
        draft_type=ContentDraftType.NEW_RESOURCE_DRAFT,
        target_kind=ChangeTargetKind.CREATE_NEW_PAGE,
        target_page_ref=None,
        locator=SectionLocator(SectionLocatorKind.NEW_PAGE, None, None, None, None),
        heading=heading,
        ordered_headings=(),
        blocks=tuple(blocks),
        page_refs=(),
        source_refs=("S1",),
    )


class WordPressDraftModelTests(unittest.TestCase):
    def test_request_requires_non_empty_title_and_content(self) -> None:
        for title, content in (("", "body"), ("  ", "body"), ("title", ""), ("title", "\n")):
            with self.subTest(title=title, content=content):
                with self.assertRaises(ValueError):
                    WordPressDraftRequest(title, content)

    def test_public_request_is_create_only_title_and_content(self) -> None:
        self.assertEqual(
            [field.name for field in fields(WordPressDraftRequest)],
            ["title", "content"],
        )

    def test_success_result_requires_valid_remote_draft_metadata(self) -> None:
        result = WordPressDraftResult(
            WordPressDraftStatus.SUCCESS,
            7,
            "https://example.com/?p=7",
            True,
            None,
            None,
        )
        self.assertEqual(result.remote_post_id, 7)
        for remote_id, link, created, failure_kind, error in (
            (True, "https://example.com/7", True, None, None),
            (0, "https://example.com/7", True, None, None),
            (7, "http://example.com/7", True, None, None),
            (7, "https://example.com/7", False, None, None),
            (7, "https://example.com/7", True, WordPressDraftFailureKind.HTTP_STATUS, None),
            (7, "https://example.com/7", True, None, "error"),
        ):
            with self.subTest(remote_id=remote_id, link=link):
                with self.assertRaises(ValueError):
                    WordPressDraftResult(
                        WordPressDraftStatus.SUCCESS,
                        remote_id,
                        link,
                        created,
                        failure_kind,
                        error,
                    )

    def test_failed_result_requires_sanitized_error_and_no_success_payload(self) -> None:
        result = WordPressDraftResult(
            WordPressDraftStatus.FAILED,
            None,
            None,
            False,
            WordPressDraftFailureKind.TIMEOUT,
            "WordPress request timed out.",
        )
        self.assertEqual(result.failure_kind, WordPressDraftFailureKind.TIMEOUT)
        for remote_id, link, created, failure_kind, error in (
            (1, None, False, WordPressDraftFailureKind.TIMEOUT, "timeout"),
            (None, "https://example.com/1", False, WordPressDraftFailureKind.TIMEOUT, "timeout"),
            (None, None, True, WordPressDraftFailureKind.TIMEOUT, "timeout"),
            (None, None, False, None, "timeout"),
            (None, None, False, WordPressDraftFailureKind.TIMEOUT, "  "),
            (None, None, False, WordPressDraftFailureKind.TIMEOUT, "bad\nsecret"),
        ):
            with self.subTest(error=error):
                with self.assertRaises(ValueError):
                    WordPressDraftResult(
                        WordPressDraftStatus.FAILED,
                        remote_id,
                        link,
                        created,
                        failure_kind,
                        error,
                    )


class WordPressDraftBuilderTests(unittest.TestCase):
    def test_title_prefers_heading_then_uses_override(self) -> None:
        block = ParagraphBlock(DraftBlockKind.PARAGRAPH, (_claim("Body"),))
        self.assertEqual(
            build_wordpress_draft_request(_draft(block), title_override="Fallback").title,
            "Buyer Guide",
        )
        self.assertEqual(
            build_wordpress_draft_request(
                _draft(block, heading=None), title_override="Fallback"
            ).title,
            "Fallback",
        )

    def test_missing_title_raises_explicit_validation_error(self) -> None:
        block = ParagraphBlock(DraftBlockKind.PARAGRAPH, (_claim("Body"),))
        with self.assertRaises(WordPressDraftValidationError):
            build_wordpress_draft_request(_draft(block, heading=None))

    def test_paragraph_and_bullet_rendering_escape_all_text(self) -> None:
        paragraph = ParagraphBlock(
            DraftBlockKind.PARAGRAPH,
            (_claim("Use <script>alert('x')</script> & verify."),),
        )
        bullets = BulletListBlock(
            DraftBlockKind.BULLET_LIST,
            (_claim('Size < 3"', 2), _claim("A & B", 3)),
        )
        request = build_wordpress_draft_request(_draft(paragraph, bullets))
        self.assertEqual(
            request.content,
            "<p>Use &lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; &amp; verify.</p>\n"
            "<ul><li>Size &lt; 3&quot;</li><li>A &amp; B</li></ul>",
        )
        self.assertNotIn("<script>", request.content)

    def test_comparison_table_rendering_is_deterministic_and_escaped(self) -> None:
        table = ComparisonTableBlock(
            DraftBlockKind.COMPARISON_TABLE,
            (
                TableCell("Pressure", "Model <A>", "10 & stable", (), ("S1",)),
                TableCell("Pressure", "Model B", "20", (), ("S1",)),
                TableCell("Flow", "Model <A>", "30", (), ("S1",)),
                TableCell("Flow", "Model B", '40"', (), ("S1",)),
            ),
        )
        request = build_wordpress_draft_request(_draft(table))
        self.assertEqual(
            request.content,
            "<table><thead><tr><th scope=\"col\">Dimension</th>"
            "<th scope=\"col\">Model &lt;A&gt;</th><th scope=\"col\">Model B</th>"
            "</tr></thead><tbody><tr><th scope=\"row\">Pressure</th>"
            "<td>10 &amp; stable</td><td>20</td></tr>"
            "<tr><th scope=\"row\">Flow</th><td>30</td><td>40&quot;</td>"
            "</tr></tbody></table>",
        )

    def test_internal_link_renders_claims_and_safe_escaped_anchor(self) -> None:
        block = InternalLinkBlock(
            DraftBlockKind.INTERNAL_LINK,
            'Pump <guide> "A"',
            "P2",
            "https://example.com/guides?a=1&b=2",
            (_claim("See the selection details."),),
        )
        request = build_wordpress_draft_request(_draft(block))
        self.assertEqual(
            request.content,
            '<p>See the selection details. <a href="https://example.com/guides?a=1&amp;b=2">'
            "Pump &lt;guide&gt; &quot;A&quot;</a></p>",
        )

    def test_unsafe_or_non_https_internal_link_is_rejected(self) -> None:
        for url in (
            "javascript:alert(1)",
            "http://example.com/guide",
            "https://user:secret@example.com/guide",
            "https://example.com/bad path",
            "https://example.com\\bad",
        ):
            with self.subTest(url=url):
                block = InternalLinkBlock(
                    DraftBlockKind.INTERNAL_LINK,
                    "Guide",
                    "P2",
                    url,
                    (_claim("Read more."),),
                )
                with self.assertRaises(WordPressDraftValidationError):
                    build_wordpress_draft_request(_draft(block))

    def test_empty_rendered_body_is_rejected(self) -> None:
        with self.assertRaises(WordPressDraftValidationError):
            build_wordpress_draft_request(_draft())

    def test_forged_block_kind_is_rejected(self) -> None:
        block = ParagraphBlock(DraftBlockKind.BULLET_LIST, (_claim("Body"),))
        with self.assertRaises(WordPressDraftValidationError):
            build_wordpress_draft_request(_draft(block))


if __name__ == "__main__":
    unittest.main()
