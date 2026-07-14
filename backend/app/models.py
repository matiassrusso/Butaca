from typing import Literal

from pydantic import BaseModel, Field


class RatedItem(BaseModel):
    title: str
    rating: float = Field(ge=0, le=5)
    review: str = ""
    watched_date: str = ""


class RecommendRequest(BaseModel):
    mood: str = ""
    ratings: list[RatedItem] = Field(default_factory=list)


class Recommendation(BaseModel):
    id: int | None = None
    tmdb_id: int | None = None
    title: str
    year: int
    kind: str
    why: str
    match_score: int
    tags: list[str]
    poster_path: str | None = None
    backdrop_path: str | None = None
    overview: str = ""
    vote_average: float | None = None


class RecommendResponse(BaseModel):
    taste_summary: str
    recommendations: list[Recommendation]


class RecommendationSession(BaseModel):
    id: int
    mood: str
    taste_summary: str
    created_at: str
    recommendations: list[Recommendation]


class RecommendationHistoryResponse(BaseModel):
    sessions: list[RecommendationSession]


class WatchedItem(BaseModel):
    title: str
    rating: float
    review: str
    created_at: str


class WatchedHistoryResponse(BaseModel):
    items: list[WatchedItem]


class UserCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=200)


class AuthResponse(BaseModel):
    token: str
    username: str


class PasswordResetRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)


class PasswordResetStartResponse(BaseModel):
    status: Literal["ok"]
    reset_token: str | None = None


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class FeedbackRequest(BaseModel):
    recommendation_id: int
    status: Literal["interested", "not_interested", "seen"]


class CastMember(BaseModel):
    name: str
    character: str = ""
    profile_path: str | None = None


class MovieDetails(BaseModel):
    cast: list[CastMember]
    trailer_key: str | None = None
