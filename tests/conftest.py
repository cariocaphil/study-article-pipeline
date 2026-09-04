"""
Shared fixtures for the agent test suite.
"""

import os
import shutil
import tempfile
from collections.abc import Iterator

import anthropic
import pytest
from dotenv import load_dotenv

from src.schemas.article import CEFRLevel, ExtractedPhrase, PhraseCategory

load_dotenv()


@pytest.fixture(scope="session")
def anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


@pytest.fixture
def sample_portuguese_text() -> str:
    """~300-word Portuguese film review excerpt, used to exercise the
    extract agent against realistic prose (quoted dialogue, register-specific
    vocabulary, idiomatic constructions)."""
    return """
Em "Entroncamento" acompanhamos Laura, que foge de um passado turbulento,
refugiando-se nesta cidade do distrito de Santarém para recomeçar a sua vida.
Contudo, apesar de tentar encontrar um emprego honesto e uma vida melhor,
começa a entrar em pequenos esquemas e crimes, motivados por familiares e
conhecidos que a envolvem numa teia de cumplicidades difícil de escapar.

Pedro Cabeleira consegue mostrar-nos, sem tornar demasiado óbvio, as
dualidades das suas personagens. Reparei muitas vezes que o realizador
escolhe deixar-nos do lado de fora de janelas, de apartamentos, como se
fôssemos observadores exteriores do que se está a passar dentro daquelas
portas. Esta distância, longe de nos afastar emocionalmente, aproxima-nos
de uma verdade incómoda: a de que a violência quotidiana raramente é
espetacular, ela instala-se devagar, quase sem darmos conta.

Apesar de lidar com temas como a violência, o crime e as drogas, o filme
nunca cai na tentação de romantizar este universo. Na forma como
apresenta estas comunidades marginalizadas, há um cuidado notório em não
as reduzir a estereótipos fáceis. Ana Vilaça, no papel de Laura, é uma
protagonista forte e dura, que não apresenta facilmente as suas
fragilidades — e é precisamente aí que reside a força da sua interpretação.

Mas esta sensibilidade que sentimos no meio do caos só é possível pelos
atores que têm um grande range emocional e capacidade de apresentar uma
dualidade de ações e sentimentos. A fotografia acompanha esse tom: cores
frias, enquadramentos que privilegiam o espaço vazio, um ritmo que nunca
se apressa a explicar-se. É um cinema que confia no espetador, que o
deixa reconstruir, a partir de fragmentos, a teia de cumplicidades que
sustenta esta pequena comunidade à beira da linha ferroviária.
""".strip()


@pytest.fixture
def sample_phrases() -> list[ExtractedPhrase]:
    """5 hardcoded ExtractedPhrase objects covering the cases the review
    agent is expected to act on: a proper noun/topic derivative that should
    be removed, a near-duplicate pair that should be flagged for review,
    and clean C1 idioms that should be kept."""
    return [
        ExtractedPhrase(
            phrase="Entroncamento",
            sentence_context=(
                'Em "Entroncamento" acompanhamos Laura, que foge de um passado turbulento.'
            ),
            translation="Entroncamento (Ortsname)",
            category=PhraseCategory.vocab,
            estimated_level=CEFRLevel.C1,
        ),
        ExtractedPhrase(
            phrase="comunidades marginalizadas",
            sentence_context="Na forma como apresenta estas comunidades marginalizadas.",
            translation="marginalisierte Gemeinschaften",
            category=PhraseCategory.vocab,
            estimated_level=CEFRLevel.C1,
        ),
        ExtractedPhrase(
            phrase="marginalização",
            sentence_context="A marginalização destas comunidades é visível ao longo do filme.",
            translation="Marginalisierung",
            category=PhraseCategory.vocab,
            estimated_level=CEFRLevel.C1,
        ),
        ExtractedPhrase(
            phrase="entrar em pequenos esquemas",
            sentence_context=(
                "começa a entrar em pequenos esquemas e crimes, motivados "
                "por familiares e conhecidos"
            ),
            translation="in kleine Machenschaften verwickelt werden",
            category=PhraseCategory.idiom,
            estimated_level=CEFRLevel.C1,
        ),
        ExtractedPhrase(
            phrase="teia de cumplicidades",
            sentence_context="que a envolvem numa teia de cumplicidades difícil de escapar",
            translation="Netz aus Komplizenschaften",
            category=PhraseCategory.idiom,
            estimated_level=CEFRLevel.C1,
        ),
    ]


@pytest.fixture
def temp_output_dir() -> Iterator[str]:
    path = tempfile.mkdtemp(prefix="study_pipeline_test_")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
