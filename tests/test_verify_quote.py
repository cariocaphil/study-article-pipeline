"""
Tests for src/tools/verify_quote.py.
"""

import logging

from src.tools.verify_quote import verify_quote

ARTICLE_TEXT = """
Em "Entroncamento" acompanhamos Laura, que foge de um passado turbulento,
refugiando-se nesta cidade do distrito de Santarém para recomeçar a sua vida.
Contudo, apesar de tentar encontrar um emprego honesto e uma vida melhor,
começa a entrar em pequenos esquemas e crimes.
"""


def test_verify_quote_returns_true_for_exact_match():
    sentence = 'Em "Entroncamento" acompanhamos Laura, que foge de um passado turbulento,'
    assert verify_quote(sentence, ARTICLE_TEXT) is True


def test_verify_quote_returns_true_when_whitespace_differs():
    sentence = 'Em "Entroncamento" acompanhamos Laura,\nque foge de um passado turbulento,'
    assert verify_quote(sentence, ARTICLE_TEXT) is True


def test_verify_quote_returns_false_for_paraphrase():
    sentence = "Laura foge de um passado turbulento e recomeça a vida."
    assert verify_quote(sentence, ARTICLE_TEXT) is False


def test_verify_quote_returns_false_for_empty_sentence():
    assert verify_quote("", ARTICLE_TEXT) is False


def test_verify_quote_logs_result(caplog):
    sentence = "começa a entrar em pequenos esquemas e crimes."
    with caplog.at_level(logging.INFO, logger="src.tools.verify_quote"):
        verify_quote(sentence, ARTICLE_TEXT)

    assert f"{sentence} → verified" in caplog.text


def test_verify_quote_logs_not_found(caplog):
    sentence = "Esta frase não está no artigo."
    with caplog.at_level(logging.INFO, logger="src.tools.verify_quote"):
        verify_quote(sentence, ARTICLE_TEXT)

    assert f"{sentence} → not found" in caplog.text
