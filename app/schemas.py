from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    admin_id: str
    password: str


class LoginResponse(BaseModel):
    token: str


class PlayerCreate(BaseModel):
    name: str
    free_fire_id: str


class PlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    free_fire_id: str
    points: int
    matches_played: int
    matches_won: int


class TeammateOut(BaseModel):
    player: PlayerOut
    matches_together: int
    wins_together: int


class PlayerDetailOut(BaseModel):
    player: PlayerOut
    teammates: List[TeammateOut]


class ShuffleRequest(BaseModel):
    player_ids: List[int]


class ShuffleOut(BaseModel):
    id: int
    date: date
    team_a: List[PlayerOut]
    team_b: List[PlayerOut]
    winner: Optional[str]
    resolved: bool
    today_shuffle_count: int


class WinnerRequest(BaseModel):
    winner: str  # "A" or "B"


class SummaryOut(BaseModel):
    today_shuffle_count: int
    pending_shuffle: Optional[ShuffleOut]
    leaderboard: List[PlayerOut]


class NetworkNode(BaseModel):
    id: int
    name: str
    points: int


class NetworkEdge(BaseModel):
    source: int
    target: int
    matches_together: int
    wins_together: int


class TopDuo(BaseModel):
    player_a: PlayerOut
    player_b: PlayerOut
    wins_together: int


class NetworkOut(BaseModel):
    nodes: List[NetworkNode]
    edges: List[NetworkEdge]
    top_duo: Optional[TopDuo]
