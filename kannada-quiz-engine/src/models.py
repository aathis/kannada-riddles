"""Typed data models. JSON is the single source of truth (design doc §10)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Question(BaseModel):
    id: int
    clue_emojis: list[str] = Field(min_length=1, description="Visual rebus clue parts")
    answer_en: str = Field(default="", description="Answer in English")
    answer_kn: str = Field(default="", description="Alternate answer text")
    prompt_text: str = Field(default="CAN YOU GUESS THE WORD?", description="Question prompt text shown below clues")
    narration_kn: str = Field(default="", description="Question narration text")
    reveal_narration_kn: str = Field(default="", description="Answer reveal narration text")


class Episode(BaseModel):
    id: str
    title_en: str = Field(default="Guess the Word!", description="Episode title")
    title_kn: str = Field(default="Guess the Word!", description="Alternate title")
    intro_narration_kn: str = Field(default="Welcome to the word riddle game! Combine the clues and guess the word.", description="Intro narration")
    outro_narration_kn: str = Field(default="Thanks for playing! Like, subscribe, and comment your score!", description="Outro narration")
    bg_music: str = Field(default="soft_piano_gymnopedie", description="Background music track choice")
    questions: list[Question] = Field(min_length=1)
