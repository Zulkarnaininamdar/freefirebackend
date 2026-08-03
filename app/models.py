from datetime import date as date_type

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    free_fire_id = Column(String, unique=True, index=True, nullable=False)
    points = Column(Integer, default=0, nullable=False)
    matches_played = Column(Integer, default=0, nullable=False)
    matches_won = Column(Integer, default=0, nullable=False)


class Shuffle(Base):
    __tablename__ = "shuffles"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, default=date_type.today, nullable=False)
    team_a = Column(JSON, nullable=False)
    team_b = Column(JSON, nullable=False)
    winner = Column(String, nullable=True)  # "A" | "B" | None
    resolved = Column(Boolean, default=False, nullable=False)


class TeammateStat(Base):
    __tablename__ = "teammate_stats"
    __table_args__ = (
        UniqueConstraint("player_a_id", "player_b_id", name="uq_player_pair"),
    )

    id = Column(Integer, primary_key=True, index=True)
    player_a_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    player_b_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    matches_together = Column(Integer, default=0, nullable=False)
    wins_together = Column(Integer, default=0, nullable=False)

    player_a = relationship("Player", foreign_keys=[player_a_id])
    player_b = relationship("Player", foreign_keys=[player_b_id])
