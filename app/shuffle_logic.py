import random
from itertools import combinations
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from .models import TeammateStat

ATTEMPTS = 150


def _pair_key(a: int, b: int) -> Tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _load_history(db: Session, player_ids: List[int]) -> Dict[Tuple[int, int], int]:
    stats = (
        db.query(TeammateStat)
        .filter(
            TeammateStat.player_a_id.in_(player_ids),
            TeammateStat.player_b_id.in_(player_ids),
        )
        .all()
    )
    return {(s.player_a_id, s.player_b_id): s.matches_together for s in stats}


def _score_split(team: List[int], history: Dict[Tuple[int, int], int]) -> int:
    return sum(history.get(_pair_key(a, b), 0) for a, b in combinations(team, 2))


def split_teams(db: Session, player_ids: List[int]) -> Tuple[List[int], List[int]]:
    """Randomly split players into two near-equal teams, favoring pairings
    that haven't played together as much historically."""
    history = _load_history(db, player_ids)
    half = len(player_ids) // 2

    best_split = None
    best_score = None
    for _ in range(ATTEMPTS):
        shuffled = player_ids[:]
        random.shuffle(shuffled)

        cut = half + (1 if len(player_ids) % 2 == 1 and random.random() < 0.5 else 0)
        team_a = shuffled[:cut]
        team_b = shuffled[cut:]

        score = _score_split(team_a, history) + _score_split(team_b, history)
        if best_score is None or score < best_score:
            best_score = score
            best_split = (team_a, team_b)

    return best_split
