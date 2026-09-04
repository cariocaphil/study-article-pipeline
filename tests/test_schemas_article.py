"""Unit tests for src/schemas/article.py (CEFRLevel comparisons)."""

from src.schemas.article import CEFRLevel


class TestCEFRLevelOrdering:
    def test_ge_orders_levels(self) -> None:
        assert CEFRLevel.C1 >= CEFRLevel.B2
        assert CEFRLevel.C1 >= CEFRLevel.C1
        assert not (CEFRLevel.B1 >= CEFRLevel.C1)

    def test_gt_orders_levels(self) -> None:
        assert CEFRLevel.C2 > CEFRLevel.C1
        assert not (CEFRLevel.C1 > CEFRLevel.C1)
        assert not (CEFRLevel.B2 > CEFRLevel.C1)

    def test_ge_returns_not_implemented_for_non_level(self) -> None:
        assert CEFRLevel.C1.__ge__("C1") is NotImplemented

    def test_gt_returns_not_implemented_for_non_level(self) -> None:
        assert CEFRLevel.C1.__gt__("C1") is NotImplemented
