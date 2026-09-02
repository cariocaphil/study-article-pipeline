"""Tests for src/utils/topic_disambiguation.py."""

from src.schemas.article import TopicType
from src.utils.topic_disambiguation import (
    parse_optional_release_year,
    topic_disambiguation_guidance,
)


class TestParseOptionalReleaseYear:
    def test_parses_trailing_release_year(self):
        assert parse_optional_release_year("Madre (2017)") == ("Madre", 2017)

    def test_parses_year_with_surrounding_whitespace(self):
        assert parse_optional_release_year("  Some Book  ( 1999 )  ") == ("Some Book", 1999)

    def test_returns_none_when_topic_has_no_year(self):
        assert parse_optional_release_year("Entroncamento") == ("Entroncamento", None)

    def test_ignores_non_trailing_parenthetical(self):
        assert parse_optional_release_year("Amadeus (director's cut)") == (
            "Amadeus (director's cut)",
            None,
        )

    def test_ignores_non_year_parenthetical_at_end(self):
        assert parse_optional_release_year("Topic (remastered)") == ("Topic (remastered)", None)


class TestTopicDisambiguationGuidance:
    def test_includes_year_and_exact_title_for_films(self):
        guidance = topic_disambiguation_guidance("Madre (2017)", TopicType.film)

        assert guidance
        assert '"Madre (2017)"' in guidance
        assert "2017" in guidance
        assert "Do not substitute a different work" in guidance

    def test_includes_year_guidance_for_books(self):
        guidance = topic_disambiguation_guidance("Some Book (1999)", TopicType.book)

        assert guidance
        assert "book" in guidance
        assert "1999" in guidance

    def test_returns_empty_string_when_year_missing(self):
        assert topic_disambiguation_guidance("Entroncamento", TopicType.film) == ""

    def test_returns_empty_string_for_non_disambiguation_topic_types(self):
        assert topic_disambiguation_guidance("Madre (2017)", TopicType.series) == ""
        assert topic_disambiguation_guidance("Madre (2017)", TopicType.album) == ""

    def test_madre_regression_mentions_exact_work_not_mother(self):
        guidance = topic_disambiguation_guidance("Madre (2017)", TopicType.film)

        assert "exactly as written" in guidance
        assert "mother!" not in guidance.lower()
