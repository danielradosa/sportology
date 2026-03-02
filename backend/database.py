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

    # subscription
    plan_tier = Column(String(20), default="free", nullable=False)
    plan_expires_at = Column(DateTime, nullable=True)

    # crypto payment identity (optional)
    wallet_address = Column(String(64), unique=True, index=True, nullable=True)
    wallet_link_nonce = Column(String(64), nullable=True)
    
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
    # Store the full analysis payload so the UI can show a detailed breakdown later.
    analysis_json = Column(Text, nullable=True)
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

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    chain = Column(String(32), nullable=False, default="polygon")
    token = Column(String(16), nullable=False, default="USDC")
    amount_usdc = Column(String(32), nullable=False)
    plan_tier = Column(String(20), nullable=False)

    tx_hash = Column(String(80), nullable=False, unique=True, index=True)
    from_address = Column(String(64), nullable=True)
    to_address = Column(String(64), nullable=True)

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

    if "plan_expires_at" not in cols:
        try:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN plan_expires_at DATETIME"))
        except Exception:
            pass

    if "wallet_address" not in cols:
        try:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN wallet_address VARCHAR(64)"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_wallet_address ON users(wallet_address)"))
        except Exception:
            pass

    if "wallet_link_nonce" not in cols:
        try:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN wallet_link_nonce VARCHAR(64)"))
        except Exception:
            pass

    # analysis_history: store full analysis payload (sqlite + postgres)
    if "analysis_history" in insp.get_table_names():
        cols_hist = {c["name"] for c in insp.get_columns("analysis_history")}
        if "analysis_json" not in cols_hist:
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE analysis_history ADD COLUMN analysis_json TEXT"))
            except Exception:
                # Best-effort; older deployments might not support ALTER in some contexts
                pass

    # payments table (create if missing)
    if "payments" not in insp.get_table_names():
        try:
            Payment.__table__.create(bind=engine, checkfirst=True)
        except Exception:
            pass

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
