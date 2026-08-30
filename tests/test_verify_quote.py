"""
Tests for src/tools/verify_quote.py.
"""

import pytest

from src.tools.verify_quote import verify_quote

ARTICLE_TEXT = """
Em "Entroncamento" acompanhamos Laura, que foge de um passado turbulento,
refugiando-se nesta cidade do distrito de Santarém para recomeçar a sua vida.
Contudo, apesar de tentar encontrar um emprego honesto e uma vida melhor,
começa a entrar em pequenos esquemas e crimes.
"""


def test_verify_quote_returns_true_for_exact_match():
    sentence = (
        'Em "Entroncamento" acompanhamos Laura, que foge de um passado turbulento,'
    )
    assert verify_quote(sentence, ARTICLE_TEXT) is True


def test_verify_quote_returns_true_when_whitespace_differs():
    sentence = (
        "Em \"Entroncamento\" acompanhamos Laura,\n"
        "que foge de um passado turbulento,"
    )
    assert verify_quote(sentence, ARTICLE_TEXT) is True


def test_verify_quote_returns_false_for_paraphrase():
    sentence = "Laura foge de um passado turbulento e recomeça a vida."
    assert verify_quote(sentence, ARTICLE_TEXT) is False


def test_verify_quote_returns_false_for_empty_sentence():
    assert verify_quote("", ARTICLE_TEXT) is False


def test_verify_quote_logs_result(capsys):
    sentence = "começa a entrar em pequenos esquemas e crimes."
    verify_quote(sentence, ARTICLE_TEXT)

    captured = capsys.readouterr()
    assert f"[quote_verifier] {sentence} → verified" in captured.out


def test_verify_quote_logs_not_found(capsys):
    sentence = "Esta frase não está no artigo."
    verify_quote(sentence, ARTICLE_TEXT)

    captured = capsys.readouterr()
    assert f"[quote_verifier] {sentence} → not found" in captured.out
