from datetime import date
from itertools import combinations
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models, schemas
from .auth import create_session, require_admin, verify_password
from .database import Base, SessionLocal, engine, get_db
from .seed import seed_admin
from .shuffle_logic import split_teams

Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    seed_admin(db)

app = FastAPI(title="Free Fire Team Shuffler")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _pair_key(a: int, b: int):
    return (a, b) if a < b else (b, a)


def _player_out(p: models.Player) -> schemas.PlayerOut:
    return schemas.PlayerOut.model_validate(p)


def _shuffle_out(s: models.Shuffle, db: Session) -> schemas.ShuffleOut:
    team_a_players = db.query(models.Player).filter(models.Player.id.in_(s.team_a)).all()
    team_b_players = db.query(models.Player).filter(models.Player.id.in_(s.team_b)).all()
    today_count = (
        db.query(models.Shuffle).filter(models.Shuffle.date == date.today()).count()
    )
    return schemas.ShuffleOut(
        id=s.id,
        date=s.date,
        team_a=[_player_out(p) for p in team_a_players],
        team_b=[_player_out(p) for p in team_b_players],
        winner=s.winner,
        resolved=s.resolved,
        today_shuffle_count=today_count,
    )


# ---------- auth ----------


@app.post("/auth/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    admin = db.query(models.Admin).filter(models.Admin.username == payload.admin_id).first()
    if admin is None or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid admin ID or password")
    token = create_session(admin.username)
    return schemas.LoginResponse(token=token)


# ---------- players (public read, admin write) ----------


@app.get("/players", response_model=List[schemas.PlayerOut])
def list_players(db: Session = Depends(get_db)):
    players = db.query(models.Player).order_by(models.Player.points.desc()).all()
    return [_player_out(p) for p in players]


@app.get("/players/{player_id}", response_model=schemas.PlayerDetailOut)
def get_player(player_id: int, db: Session = Depends(get_db)):
    player = db.query(models.Player).filter(models.Player.id == player_id).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    stats = (
        db.query(models.TeammateStat)
        .filter(
            (models.TeammateStat.player_a_id == player_id)
            | (models.TeammateStat.player_b_id == player_id)
        )
        .all()
    )
    teammates = []
    for s in stats:
        other_id = s.player_b_id if s.player_a_id == player_id else s.player_a_id
        other = db.query(models.Player).filter(models.Player.id == other_id).first()
        if other is None:
            continue
        teammates.append(
            schemas.TeammateOut(
                player=_player_out(other),
                matches_together=s.matches_together,
                wins_together=s.wins_together,
            )
        )
    teammates.sort(key=lambda t: t.wins_together, reverse=True)

    return schemas.PlayerDetailOut(player=_player_out(player), teammates=teammates)


@app.post("/players", response_model=schemas.PlayerOut)
def create_player(
    payload: schemas.PlayerCreate,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
):
    existing = (
        db.query(models.Player)
        .filter(models.Player.free_fire_id == payload.free_fire_id)
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=400, detail="That Free Fire ID is already registered")

    player = models.Player(name=payload.name, free_fire_id=payload.free_fire_id)
    db.add(player)
    db.commit()
    db.refresh(player)
    return _player_out(player)


@app.delete("/players/{player_id}", status_code=204)
def delete_player(
    player_id: int,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
):
    player = db.query(models.Player).filter(models.Player.id == player_id).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    pending = (
        db.query(models.Shuffle).filter(models.Shuffle.resolved == False).first()  # noqa: E712
    )
    if pending is not None and (
        player_id in pending.team_a or player_id in pending.team_b
    ):
        raise HTTPException(
            status_code=400,
            detail="This player is in a pending shuffle — record the winner before deleting them",
        )

    db.query(models.TeammateStat).filter(
        (models.TeammateStat.player_a_id == player_id)
        | (models.TeammateStat.player_b_id == player_id)
    ).delete(synchronize_session=False)

    db.delete(player)
    db.commit()


# ---------- admin summary ----------


@app.get("/admin/summary", response_model=schemas.SummaryOut)
def admin_summary(db: Session = Depends(get_db), admin_id: str = Depends(require_admin)):
    today_count = (
        db.query(models.Shuffle).filter(models.Shuffle.date == date.today()).count()
    )
    pending = (
        db.query(models.Shuffle)
        .filter(models.Shuffle.resolved == False)  # noqa: E712
        .order_by(models.Shuffle.id.desc())
        .first()
    )
    leaderboard = db.query(models.Player).order_by(models.Player.points.desc()).all()

    return schemas.SummaryOut(
        today_shuffle_count=today_count,
        pending_shuffle=_shuffle_out(pending, db) if pending else None,
        leaderboard=[_player_out(p) for p in leaderboard],
    )


# ---------- shuffle ----------


@app.post("/shuffle", response_model=schemas.ShuffleOut)
def create_shuffle(
    payload: schemas.ShuffleRequest,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
):
    if len(payload.player_ids) < 2:
        raise HTTPException(status_code=400, detail="Select at least 2 players")

    pending = (
        db.query(models.Shuffle).filter(models.Shuffle.resolved == False).first()  # noqa: E712
    )
    if pending is not None:
        raise HTTPException(
            status_code=400,
            detail="A shuffle is already pending — record its winner before shuffling again",
        )

    players = (
        db.query(models.Player).filter(models.Player.id.in_(payload.player_ids)).all()
    )
    if len(players) != len(set(payload.player_ids)):
        raise HTTPException(status_code=400, detail="One or more players not found")

    team_a, team_b = split_teams(db, payload.player_ids)

    shuffle = models.Shuffle(date=date.today(), team_a=team_a, team_b=team_b)
    db.add(shuffle)
    db.commit()
    db.refresh(shuffle)

    return _shuffle_out(shuffle, db)


@app.post("/shuffle/{shuffle_id}/winner", response_model=schemas.ShuffleOut)
def set_winner(
    shuffle_id: int,
    payload: schemas.WinnerRequest,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
):
    if payload.winner not in ("A", "B"):
        raise HTTPException(status_code=400, detail="winner must be 'A' or 'B'")

    shuffle = db.query(models.Shuffle).filter(models.Shuffle.id == shuffle_id).first()
    if shuffle is None:
        raise HTTPException(status_code=404, detail="Shuffle not found")
    if shuffle.resolved:
        raise HTTPException(status_code=400, detail="This shuffle already has a recorded winner")

    winning_ids = set(shuffle.team_a if payload.winner == "A" else shuffle.team_b)

    for team in (shuffle.team_a, shuffle.team_b):
        players = db.query(models.Player).filter(models.Player.id.in_(team)).all()
        for p in players:
            p.matches_played += 1
            if p.id in winning_ids:
                p.matches_won += 1
                p.points += 10

        for a, b in combinations(sorted(team), 2):
            stat = (
                db.query(models.TeammateStat)
                .filter(
                    models.TeammateStat.player_a_id == a,
                    models.TeammateStat.player_b_id == b,
                )
                .first()
            )
            if stat is None:
                stat = models.TeammateStat(player_a_id=a, player_b_id=b, matches_together=0, wins_together=0)
                db.add(stat)
            stat.matches_together += 1
            if a in winning_ids and b in winning_ids:
                stat.wins_together += 1

    shuffle.winner = payload.winner
    shuffle.resolved = True
    db.commit()
    db.refresh(shuffle)

    return _shuffle_out(shuffle, db)


@app.get("/shuffle/history", response_model=List[schemas.ShuffleOut])
def shuffle_history(db: Session = Depends(get_db), admin_id: str = Depends(require_admin)):
    shuffles = db.query(models.Shuffle).order_by(models.Shuffle.id.desc()).all()
    return [_shuffle_out(s, db) for s in shuffles]


@app.get("/shuffle/current", response_model=Optional[schemas.ShuffleOut])
def current_shuffle(db: Session = Depends(get_db)):
    pending = (
        db.query(models.Shuffle)
        .filter(models.Shuffle.resolved == False)  # noqa: E712
        .order_by(models.Shuffle.id.desc())
        .first()
    )
    return _shuffle_out(pending, db) if pending else None


# ---------- network graph (public) ----------


@app.get("/network", response_model=schemas.NetworkOut)
def network(db: Session = Depends(get_db)):
    players = db.query(models.Player).all()
    stats = db.query(models.TeammateStat).filter(models.TeammateStat.matches_together > 0).all()

    nodes = [schemas.NetworkNode(id=p.id, name=p.name, points=p.points) for p in players]
    edges = [
        schemas.NetworkEdge(
            source=s.player_a_id,
            target=s.player_b_id,
            matches_together=s.matches_together,
            wins_together=s.wins_together,
        )
        for s in stats
    ]

    top_duo = None
    if stats:
        best = max(stats, key=lambda s: s.wins_together)
        if best.wins_together > 0:
            top_duo = schemas.TopDuo(
                player_a=_player_out(best.player_a),
                player_b=_player_out(best.player_b),
                wins_together=best.wins_together,
            )

    return schemas.NetworkOut(nodes=nodes, edges=edges, top_duo=top_duo)
