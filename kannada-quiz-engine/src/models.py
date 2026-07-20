"""Typed data models. JSON is the single source of truth (design doc §10)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Question(BaseModel):
    id: int
    clue_emojis: list[str] = Field(min_length=1, description="Visual rebus clue parts")
    answer_kn: str = Field(description="Answer in Kannada script")
    answer_en: str = Field(description="Answer meaning in English")
    narration_kn: str = Field(description="Kannada narration when the clue is shown")
    reveal_narration_kn: str = Field(description="Kannada narration when the answer is revealed")


class Episode(BaseModel):
    id: str
    title_kn: str
    title_en: str
    intro_narration_kn: str
    outro_narration_kn: str
    questions: list[Question] = Field(min_length=1)
