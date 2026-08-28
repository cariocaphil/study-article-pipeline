from pydantic import BaseModel
from enum import Enum
from typing import Optional


class CEFRLevel(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"

    def __ge__(self, other):
        order = list(CEFRLevel)
        return order.index(self) >= order.index(other)

    def __gt__(self, other):
        order = list(CEFRLevel)
        return order.index(self) > order.index(other)


class PhraseCategory(str, Enum):
    vocab = "vocab"
    construction = "construction"
    idiom = "idiom"


class ExtractedPhrase(BaseModel):
    phrase: str                    # the word, expression, or construction
    sentence_context: str          # the sentence it appeared in
    translation: str               # in the user's target language
    category: PhraseCategory
    estimated_level: CEFRLevel     # agent's estimate of this item's difficulty


class Article(BaseModel):
    title: str
    author: Optional[str] = None   # None if not found on the page
    url: str
    source_name: str               # e.g. "fiocondutor.com.pt"
    full_text: str                 # full article body
    phrases: list[ExtractedPhrase] # filtered to >= user's CEFR level


class PipelineOutput(BaseModel):
    topic: str
    source_language: str
    translation_language: str
    user_level: CEFRLevel
    articles: list[Article]