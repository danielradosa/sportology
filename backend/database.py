from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Text, UniqueConstraint, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import unicodedata
import re
import os

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    plan_tier = Column(String(20), default="free", nullable=False)
    
    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    usage_logs = relationship("UsageLog", back_populates="user", cascade="all, delete-orphan")

class APIKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    api_key = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, nullable=True)
    active = Column(Boolean, default=True)
    request_count = Column(Integer, default=0)
    
    # Relationships
    user = relationship("User", back_populates="api_keys")

class UsageLog(Base):
    __tablename__ = "usage_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=True)
    endpoint = Column(String(100), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="usage_logs")

class AnalysisHistory(Base):
    __tablename__ = "analysis_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sport = Column(String(50), nullable=False)
    player1_name = Column(String(100), nullable=False)
    player2_name = Column(String(100), nullable=False)
    match_date = Column(String(10), nullable=False)
    confidence = Column(String(20))
    winner_prediction = Column(String(100))
    bet_size = Column(String(50))
    score_difference = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.strip().lower()
    name = re.sub(r"[-_]+", " ", name)
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("sport", "name_norm", name="uq_players_sport_name_norm"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    name_norm = Column(String(120), nullable=False, index=True)
    birthdate = Column(String(10), nullable=True)  # YYYY-MM-DD
    sport = Column(String(50), nullable=False)      # tennis, table-tennis, etc.
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserIPClaim(Base):
    __tablename__ = "user_ip_claims"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    ip_address = Column(String(45), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class DemoUsage(Base):
    __tablename__ = "demo_usage"
    
    id = Column(Integer, primary_key=True, index=True)
    client_ip = Column(String(45), unique=True, index=True, nullable=False)  # IPv6 max length
    count = Column(Integer, default=0)
    reset_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sports_numerology.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_tables():
    Base.metadata.create_all(bind=engine)
    ensure_schema_updates()


def ensure_schema_updates():
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("users")}
    if "plan_tier" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN plan_tier VARCHAR(20) DEFAULT 'free'"))
            conn.execute(text("UPDATE users SET plan_tier='free' WHERE plan_tier IS NULL"))

    # add players.verified if missing (postgres only)
    if "players" in insp.get_table_names():
        cols_players = {c["name"] for c in insp.get_columns("players")}
        if "verified" not in cols_players:
            try:
                db_url = str(engine.url)
                if db_url.startswith("postgres"):
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE players ADD COLUMN verified BOOLEAN DEFAULT FALSE"))
            except Exception:
                pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
