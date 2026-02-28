from fastapi import FastAPI, Depends, HTTPException, status, Request # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from fastapi.staticfiles import StaticFiles # type: ignore
from fastapi.responses import FileResponse, JSONResponse, Response # type: ignore
from pydantic import BaseModel, EmailStr, Field # type: ignore
from sqlalchemy.orm import Session # type: ignore
from sqlalchemy import or_, func # type: ignore
from datetime import date, datetime, timedelta
from fastapi import WebSocket, WebSocketDisconnect # type: ignore
from typing import List, Optional
import os
from collections import defaultdict
from sqlalchemy.dialects.postgresql import insert as pg_insert # type: ignore
import unicodedata, re
from urllib.request import Request as UrlRequest, urlopen
from urllib.parse import urlencode

import json

from database import create_tables, get_db, User, APIKey, DemoUsage, Player, UsageLog, UserIPClaim
from auth import (
    get_password_hash, verify_password, create_access_token, 
    get_current_user, get_api_key_user, generate_api_key, 
    check_rate_limit, log_usage
)
from numerology import analyze_match

def get_client_ip(req: Request) -> str:
    """Extract client IP from request"""
    # Try X-Forwarded-For first (for proxies/load balancers)
    forwarded = req.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # Try X-Real-IP
    real_ip = req.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    # Fall back to direct connection
    if req.client:
        return req.client.host
    return "unknown"

def check_demo_rate_limit_db(client_ip: str, db: Session) -> tuple[bool, int, int, datetime]:
    """
    Check if client has exceeded demo rate limit using PostgreSQL
    Returns: (allowed, current_count, remaining, reset_time)
    """
    now = datetime.utcnow()
    
    # Get or create entry for this IP
    usage = db.query(DemoUsage).filter(DemoUsage.client_ip == client_ip).first()
    
    if not usage:
        # Create new entry
        reset_time = now + timedelta(days=1)
        usage = DemoUsage(
            client_ip=client_ip,
            count=0,
            reset_time=reset_time
        )
        db.add(usage)
        db.commit()
    
    # Reset if day has passed
    if now > usage.reset_time:
        usage.count = 0
        usage.reset_time = now + timedelta(days=1)
        db.commit()
    
    # Check limit (max 5 per day)
    if usage.count >= 5:
        return False, usage.count, 0, usage.reset_time
    
    # Increment count
    usage.count += 1
    usage.updated_at = now
    db.commit()
    
    remaining = 5 - usage.count
    
    return True, usage.count, remaining, usage.reset_time

# Create app
app = FastAPI(
    title="Sports Numerology API",
    description="Analyze sports matches using numerology principles",
    version="1.0.0"
)

# CORS middleware
# - Dev: allow local frontend/backend origins
# - Prod: allow only explicit origin(s) from env (no wildcard)
env_name = os.getenv("ENV", "development").lower()
explicit_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

if explicit_origins:
    cors_origins = explicit_origins
elif env_name == "production":
    # In production, keep this strict. Set CORS_ORIGINS or PUBLIC_ORIGIN.
    public_origin = os.getenv("PUBLIC_ORIGIN", "").strip()
    cors_origins = [public_origin] if public_origin else []
else:
    cors_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    created_at: str
    plan_tier: str
    
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class APIKeyCreate(BaseModel):
    name: Optional[str] = "Default Key"


TIER_API_KEY_LIMITS = {
    "free": 1,
    "starter": 3,
    "pro": None,  # unlimited keys
}

class APIKeyResponse(BaseModel):
    id: int
    name: Optional[str]
    api_key: str
    created_at: str
    last_used: Optional[str]
    active: bool
    request_count: int
    
    class Config:
        from_attributes = True

class MatchAnalysisRequest(BaseModel):
    player1_name: str = Field(..., min_length=1, max_length=100)
    player1_birthdate: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    player2_name: str = Field(..., min_length=1, max_length=100)
    player2_birthdate: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    match_date: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    sport: str = Field(default="tennis", pattern=r'^(tennis|table-tennis)$')

class MatchAnalysisResponse(BaseModel):
    match_date: str
    sport: str
    universal_year: int
    universal_month: int
    universal_day: int
    player1: dict
    player2: dict
    winner_prediction: str
    confidence: str
    score_difference: int
    recommendation: str
    bet_size: str
    analysis_summary: str
    demo: Optional[bool] = None
    note: Optional[str] = None
    remaining_tries: Optional[int] = None
    used_today: Optional[int] = None

class DemoRequest(BaseModel):
    player1_name: str = Field(..., min_length=1, max_length=100)
    player1_birthdate: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    player2_name: str = Field(..., min_length=1, max_length=100)
    player2_birthdate: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    match_date: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    sport: str = Field(default="tennis", pattern=r'^(tennis|table-tennis)$')

class ResolvePlayerRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    sport: str = Field(default="tennis", pattern=r'^(tennis|table-tennis)$')

class ResolvePlayerResponse(BaseModel):
    id: int
    name: str
    birthdate: str
    sport: str
    country: Optional[str] = None
    updated: Optional[bool] = False
    created: Optional[bool] = False

# Startup event
@app.on_event("startup")
async def startup_event():
    try:
        create_tables()
        print("Database tables created successfully")
    except Exception as e:
        print(f"Warning: Database initialization error: {e}")
        # Continue anyway - might be first deploy

@app.websocket("/ws/stats")
async def ws_stats(ws: WebSocket):
    """
    Connect: /ws/stats?token=<JWT>
    Messages:
      { "action": "get_stats" }
    Replies:
      { "type": "stats", "data": {...} }
    """
    await ws.accept()

    token = ws.query_params.get("token")
    if not token:
        await ws.send_text(json.dumps({"type": "error", "message": "Missing token"}))
        await ws.close(code=1008)
        return

    # manual DB session (Depends doesn't work the same in WS)
    db: Session = next(get_db())

    try:
        # Use your existing token verifier (same as HTTP auth)
        from auth import verify_token
        email = verify_token(token)
        if not email:
            await ws.send_text(json.dumps({"type": "error", "message": "Invalid token"}))
            await ws.close(code=1008)
            return

        user = db.query(User).filter(User.email == email).first()
        if not user:
            await ws.send_text(json.dumps({"type": "error", "message": "User not found"}))
            await ws.close(code=1008)
            return

        def build_stats():
            now = datetime.utcnow()
            today = now.date()
            today_start = datetime.combine(today, datetime.min.time())
            today_end = datetime.combine(today, datetime.max.time())

            # Daily successful requests (same logic as rate limit)
            daily_requests = db.query(UsageLog).filter(
                UsageLog.user_id == user.id,
                UsageLog.timestamp >= today_start,
                UsageLog.timestamp <= today_end,
                UsageLog.success == True
            ).count()

            total_requests = db.query(UsageLog).filter(
                UsageLog.user_id == user.id,
                UsageLog.success == True
            ).count()

            # Active users = users who made a request today
            active_today = db.query(UsageLog.user_id).filter(
                UsageLog.timestamp >= today_start,
                UsageLog.timestamp <= today_end,
                UsageLog.success == True
            ).distinct().count()

            return {
                "timestamp": now.isoformat(),
                "daily_requests": daily_requests,
                "total_requests": total_requests,
                "current_active_users": active_today,
            }

        # Send initial stats immediately
        await ws.send_text(json.dumps({"type": "stats", "data": build_stats()}))

        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await ws.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            if msg.get("action") == "get_stats":
                await ws.send_text(json.dumps({"type": "stats", "data": build_stats()}))
            else:
                await ws.send_text(json.dumps({"type": "error", "message": "Unknown action"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await ws.send_text(json.dumps({"type": "error", "message": f"Server error: {str(e)}"}))
        await ws.close(code=1011)
    finally:
        try:
            db.close()
        except Exception:
            pass

# Health check
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "sports-numerology-api",
        "version": "1.0.0",
        "frontend_path": frontend_dist_path,
        "static_path": static_path,
        "frontend_exists": os.path.exists(frontend_dist_path),
        "static_exists": os.path.exists(static_path)
    }

# Authentication endpoints
@app.post("/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(user_data: UserCreate, req: Request, db: Session = Depends(get_db)):
    try:
        # Check if user exists
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Anti-abuse: one account per IP
        client_ip = get_client_ip(req)
        existing_ip_claim = db.query(UserIPClaim).filter(UserIPClaim.ip_address == client_ip).first()
        if existing_ip_claim:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account limit reached for this IP (max 1 free account)."
            )

        # Create user
        try:
            hashed_password = get_password_hash(user_data.password)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password processing failed: {str(e)}"
            )

        new_user = User(
            email=user_data.email,
            password_hash=hashed_password,
            plan_tier="free"
        )
        db.add(new_user)
        db.flush()

        # Lock IP -> user mapping
        ip_claim = UserIPClaim(user_id=new_user.id, ip_address=client_ip)
        db.add(ip_claim)

        # Create default API key
        api_key = generate_api_key()
        new_api_key = APIKey(
            user_id=new_user.id,
            api_key=api_key,
            name="Default Key"
        )
        db.add(new_api_key)
        db.commit()
        db.refresh(new_user)
        
        # Generate token
        access_token = create_access_token(data={"sub": new_user.email})
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": new_user.id,
                "email": new_user.email,
                "created_at": new_user.created_at.isoformat(),
                "plan_tier": new_user.plan_tier,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Signup error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )

@app.post("/auth/login", response_model=TokenResponse)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()
    
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    access_token = create_access_token(data={"sub": user.email})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "created_at": user.created_at.isoformat(),
            "plan_tier": user.plan_tier,
        }
    }

@app.get("/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "created_at": current_user.created_at.isoformat(),
        "plan_tier": current_user.plan_tier,
    }

# API Key management endpoints
@app.post("/api-keys", response_model=APIKeyResponse)
def create_api_key(
    key_data: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tier = (current_user.plan_tier or "free").lower()
    key_limit = TIER_API_KEY_LIMITS.get(tier, 1)

    active_keys_count = db.query(APIKey).filter(
        APIKey.user_id == current_user.id,
        APIKey.active == True
    ).count()

    if key_limit is not None and active_keys_count >= key_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": f"API key limit reached for {tier} tier.",
                "tier": tier,
                "key_limit": key_limit,
                "active_keys": active_keys_count,
            }
        )

    api_key = generate_api_key()
    new_key = APIKey(
        user_id=current_user.id,
        api_key=api_key,
        name=key_data.name
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)

    return {
        "id": new_key.id,
        "name": new_key.name,
        "api_key": new_key.api_key,
        "created_at": new_key.created_at.isoformat(),
        "last_used": new_key.last_used.isoformat() if new_key.last_used else None,
        "active": new_key.active,
        "request_count": new_key.request_count
    }

@app.get("/api-keys", response_model=List[APIKeyResponse])
def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    keys = db.query(APIKey).filter(APIKey.user_id == current_user.id).all()
    return [
        {
            "id": key.id,
            "name": key.name,
            "api_key": key.api_key,  # Return full key for owner's use
            "created_at": key.created_at.isoformat(),
            "last_used": key.last_used.isoformat() if key.last_used else None,
            "active": key.active,
            "request_count": key.request_count
        }
        for key in keys
    ]

@app.delete("/api-keys/{key_id}")
def delete_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    ).first()
    
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    db.delete(key)
    db.commit()
    
    return {"message": "API key deleted successfully"}

@app.post("/api-keys/{key_id}/revoke")
def revoke_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    ).first()
    
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    key.active = False
    db.commit()
    
    return {"message": "API key revoked successfully"}

# Protected API endpoint
@app.post("/api/v1/analyze-match", response_model=MatchAnalysisResponse)
def analyze_match_endpoint(
    request: MatchAnalysisRequest,
    current_user: User = Depends(get_api_key_user),
    db: Session = Depends(get_db)
):
    # Check rate limit
    check_rate_limit(current_user, db)
    
    try:
        result = analyze_match(
            player1_name=request.player1_name,
            player1_birthdate=request.player1_birthdate,
            player2_name=request.player2_name,
            player2_birthdate=request.player2_birthdate,
            match_date_str=request.match_date,
            sport=request.sport
        )
        
        # Log successful usage
        log_usage(
            user_id=current_user.id,
            endpoint="/api/v1/analyze-match",
            success=True,
            db=db
        )
        
        return result
        
    except Exception as e:
        # Log failed usage
        log_usage(
            user_id=current_user.id,
            endpoint="/api/v1/analyze-match",
            success=False,
            error_message=str(e),
            db=db
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )

# Demo endpoint (no auth required, max 5 per IP per day)
@app.post("/api/v1/demo-analyze")
def demo_analyze(request: DemoRequest, req: Request, db: Session = Depends(get_db)):
    """Demo endpoint - max 5 uses per IP per day"""
    # Get client IP
    client_ip = get_client_ip(req)
    
    # Check rate limit using database
    allowed, count, remaining, reset_time = check_demo_rate_limit_db(client_ip, db)
    
    if not allowed:
        # Calculate time until reset
        now = datetime.utcnow()
        time_until_reset = reset_time - now
        hours = int(time_until_reset.total_seconds() // 3600)
        minutes = int((time_until_reset.total_seconds() % 3600) // 60)
        
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "Demo limit reached (5 per day).",
                "reset_in_hours": hours,
                "reset_in_minutes": minutes,
                "reset_time": reset_time.isoformat(),
                "suggestion": "Sign up for unlimited access."
            }
        )
    
    try:
        result = analyze_match(
            player1_name=request.player1_name,
            player1_birthdate=request.player1_birthdate,
            player2_name=request.player2_name,
            player2_birthdate=request.player2_birthdate,
            match_date_str=request.match_date,
            sport=request.sport
        )
        # Add disclaimer for demo
        result["demo"] = True
        result["note"] = f"This is a demo ({remaining} free tries remaining today). Sign up for unlimited access."
        result["remaining_tries"] = remaining
        result["used_today"] = count
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )

# Check demo rate limit status (no auth required)
@app.get("/api/v1/demo-status")
def demo_status(req: Request, db: Session = Depends(get_db)):
    """Check current demo rate limit status for this IP"""
    client_ip = get_client_ip(req)
    
    usage = db.query(DemoUsage).filter(DemoUsage.client_ip == client_ip).first()
    now = datetime.utcnow()
    
    if not usage:
        return {
            "used": 0,
            "remaining": 5,
            "limit": 5,
            "reset_time": (now + timedelta(days=1)).isoformat(),
            "limited": False
        }
    
    # Reset if day has passed
    if now > usage.reset_time:
        return {
            "used": 0,
            "remaining": 5,
            "limit": 5,
            "reset_time": (now + timedelta(days=1)).isoformat(),
            "limited": False
        }
    
    remaining = max(0, 5 - usage.count)
    limited = usage.count >= 5
    
    # Calculate time until reset
    time_until_reset = usage.reset_time - now
    hours = int(time_until_reset.total_seconds() // 3600)
    minutes = int((time_until_reset.total_seconds() % 3600) // 60)
    
    return {
        "used": usage.count,
        "remaining": remaining,
        "limit": 5,
        "reset_time": usage.reset_time.isoformat(),
        "reset_in_hours": hours,
        "reset_in_minutes": minutes,
        "limited": limited
    }

# Get user usage statistics
@app.get("/api/v1/usage-stats")
def get_usage_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get real usage statistics for the authenticated user"""
    from datetime import date
    
    # Use UTC consistently (matches database timestamps)
    now = datetime.utcnow()
    today = now.date()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    
    # This month
    month_start = datetime.combine(today.replace(day=1), datetime.min.time())
    
    # Count ALL requests for today
    today_count = db.query(UsageLog).filter(
        UsageLog.user_id == current_user.id,
        UsageLog.timestamp >= today_start,
        UsageLog.timestamp <= today_end
    ).count()
    
    month_count = db.query(UsageLog).filter(
        UsageLog.user_id == current_user.id,
        UsageLog.timestamp >= month_start,
        UsageLog.timestamp <= today_end
    ).count()
    
    total_count = db.query(UsageLog).filter(
        UsageLog.user_id == current_user.id
    ).count()
    
    tier = (current_user.plan_tier or "free").lower()
    limit_by_tier = {"free": 10, "starter": 100, "pro": 1000}

    return JSONResponse(
        content={
            "today": today_count,
            "this_month": month_count,
            "total": total_count,
            "tier": tier,
            "limit": limit_by_tier.get(tier, 10),
            "reset_time": today_end.isoformat()
        },
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

# Debug endpoint - view recent usage logs
@app.get("/api/v1/debug/usage-logs")
def debug_usage_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Debug: View recent usage logs for current user"""
    logs = db.query(UsageLog).filter(
        UsageLog.user_id == current_user.id
    ).order_by(UsageLog.timestamp.desc()).limit(10).all()
    
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "recent_logs": [
            {
                "id": log.id,
                "endpoint": log.endpoint,
                "timestamp": log.timestamp.isoformat(),
                "success": log.success
            }
            for log in logs
        ]
    }

@app.post("/admin/users/{user_id}/tier")
def set_user_tier(
    user_id: int,
    tier: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Set user tier manually (admin). Requires X-Admin-Key header."""
    admin_key = request.headers.get("X-Admin-Key")
    expected_key = os.getenv("ADMIN_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured")
    if admin_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    normalized = tier.strip().lower()
    if normalized not in {"free", "starter", "pro"}:
        raise HTTPException(status_code=400, detail="tier must be one of: free, starter, pro")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.plan_tier = normalized
    db.commit()

    return {"message": "Tier updated", "user_id": user.id, "tier": user.plan_tier}

# Player database endpoints
@app.get("/api/v1/players")
def search_players(
    q: str = "",
    sport: str = "",
    db: Session = Depends(get_db)
):
    """Search players by name (autocomplete). Uses normalized name for accents/hyphens/etc."""
    query = db.query(Player)

    if sport:
        query = query.filter(Player.sport == sport)

    if q:
        q_raw = q.strip()
        q_norm = normalize_name(q_raw)

        query = query.filter(
            or_(
                Player.name_norm.ilike(f"%{q_norm}%"),
                Player.name.ilike(f"%{q_raw}%"),
            )
        )

    players = query.limit(10).all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "birthdate": p.birthdate,
            "sport": p.sport,
            "country": p.country,
        }
        for p in players
    ]


@app.get("/api/v1/players/suggest")
def suggest_players(
    q: str = "",
    sport: str = "",
    db: Session = Depends(get_db)
):
    """Suggest players from DB; if not enough, enrich via Wikidata and return DOB."""
    if not sport:
        return []

    suggestions = []

    # 1) DB suggestions
    query = db.query(Player)
    if sport:
        query = query.filter(Player.sport == sport)
    if q:
        q_raw = q.strip()
        q_norm = normalize_name(q_raw)
        query = query.filter(
            or_(
                Player.name_norm.ilike(f"%{q_norm}%"),
                Player.name.ilike(f"%{q_raw}%"),
            )
        )
    db_players = query.limit(10).all()
    for p in db_players:
        # If missing data, refresh from Wikidata (source of truth)
        if not p.birthdate or not p.country:
            sport_keyword = "tennis player" if p.sport == "tennis" else "table tennis"
            results = _wikidata_search(p.name, sport_keyword)
            if not results:
                results = _wikidata_search(p.name, "")
            entity_id = _pick_entity(results, sport_keyword)
            if entity_id:
                entity = _wikidata_get(entity_id)
                if _is_human_sport_entity(entity, p.sport):
                    birthdate = _extract_birthdate(entity)
                    country = _extract_country(entity)
                    updated = False
                    if birthdate and p.birthdate != birthdate:
                        p.birthdate = birthdate
                        updated = True
                    if country and p.country != country:
                        p.country = country
                        updated = True
                    if updated:
                        db.commit()
        suggestions.append({
            "id": p.id,
            "name": p.name,
            "birthdate": p.birthdate,
            "sport": p.sport,
            "country": p.country,
            "source": "db",
        })

    # 2) Wikidata suggestions (only if needed and query provided)
    if q and len(suggestions) < 10:
        sport_keyword = "tennis player" if sport == "tennis" else "table tennis"
        results = _wikidata_search(q, sport_keyword)
        if not results:
            results = _wikidata_search(q, "")

        for item in results:
            if len(suggestions) >= 10:
                break
            # filter by sport keyword in description when possible
            desc = (item.get("description") or "").lower()
            if sport_keyword and sport_keyword not in desc:
                continue
            entity_id = item.get("id")
            if not entity_id:
                continue
            entity = _wikidata_get(entity_id)
            if not _is_human_sport_entity(entity, sport):
                continue
            birthdate = _extract_birthdate(entity)
            if not birthdate:
                continue
            name = entity.get("labels", {}).get("en", {}).get("value") or item.get("label")
            if not name:
                continue
            display_name = name.strip()
            name_norm = normalize_name(display_name)
            if any(normalize_name(s["name"]) == name_norm for s in suggestions):
                continue

            country = _extract_country(entity)

            # Upsert into DB (prefer Wikidata birthdate)
            existing = db.query(Player).filter(Player.sport == sport, Player.name_norm == name_norm).first()
            if existing:
                if existing.birthdate != birthdate:
                    existing.birthdate = birthdate
                existing.name = display_name
                existing.name_norm = name_norm
                if country:
                    existing.country = country
                db.commit()
                player_id = existing.id
            else:
                new_player = Player(
                    name=display_name,
                    name_norm=name_norm,
                    birthdate=birthdate,
                    sport=sport or "",
                    country=country,
                )
                db.add(new_player)
                db.commit()
                db.refresh(new_player)
                player_id = new_player.id

            suggestions.append({
                "id": player_id,
                "name": display_name,
                "birthdate": birthdate,
                "sport": sport or "",
                "country": country,
                "source": "wikidata",
            })

    return suggestions

@app.get("/api/v1/players/{player_id}")
def get_player(player_id: int, db: Session = Depends(get_db)):
    """Get a specific player by ID"""
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    return {
        "id": player.id,
        "name": player.name,
        "birthdate": player.birthdate,
        "sport": player.sport,
        "country": player.country
    }


@app.post("/api/v1/players/resolve", response_model=ResolvePlayerResponse)
def resolve_player(request: ResolvePlayerRequest, db: Session = Depends(get_db)):
    name = request.name.strip()
    sport = request.sport.strip()
    if not name or not sport:
        raise HTTPException(status_code=400, detail="name and sport are required")

    name_norm = normalize_name(name)
    existing = db.query(Player).filter(Player.sport == sport, Player.name_norm == name_norm).first()

    sport_keyword = "tennis player" if sport == "tennis" else "table tennis"
    results = _wikidata_search(name, sport_keyword)
    if not results:
        results = _wikidata_search(name, "")
    entity_id = _pick_entity(results, sport_keyword)
    if not entity_id:
        raise HTTPException(status_code=404, detail="Player not found on Wikidata")

    entity = _wikidata_get(entity_id)
    if not _is_human_sport_entity(entity, sport):
        raise HTTPException(status_code=404, detail="No matching player found")

    birthdate = _extract_birthdate(entity)
    if not birthdate:
        raise HTTPException(status_code=404, detail="Birthdate not found")

    country = _extract_country(entity)

    updated = False
    created = False

    if existing:
        if existing.birthdate != birthdate:
            existing.birthdate = birthdate
            updated = True
        if country and existing.country != country:
            existing.country = country
            updated = True
        if existing.name != name:
            existing.name = name
            existing.name_norm = name_norm
            updated = True
        if updated:
            db.commit()
        player = existing
    else:
        player = Player(
            name=name,
            name_norm=name_norm,
            birthdate=birthdate,
            sport=sport,
            country=country,
        )
        db.add(player)
        db.commit()
        db.refresh(player)
        created = True

    return {
        "id": player.id,
        "name": player.name,
        "birthdate": player.birthdate,
        "sport": player.sport,
        "country": player.country,
        "updated": updated,
        "created": created,
    }

def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.strip().lower()
    name = re.sub(r"[-_]+", " ", name)
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _valid_birthdate(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise HTTPException(status_code=400, detail="birthdate must be YYYY-MM-DD")
    return value


def _wikidata_request(params: dict) -> dict:
    url = "https://www.wikidata.org/w/api.php?" + urlencode(params)
    req = UrlRequest(url, headers={"User-Agent": "sportology/1.0"})
    return json.loads(urlopen(req).read().decode())


def _wikidata_search(name: str, sport_keyword: str) -> list:
    params = {
        "action": "wbsearchentities",
        "search": f"{name} {sport_keyword}" if sport_keyword else name,
        "language": "en",
        "format": "json",
        "limit": 5,
    }
    data = _wikidata_request(params)
    return data.get("search", [])


def _wikidata_get(entity_id: str) -> dict:
    params = {
        "action": "wbgetentities",
        "ids": entity_id,
        "format": "json",
        "props": "claims|descriptions|labels",
    }
    data = _wikidata_request(params)
    return data.get("entities", {}).get(entity_id, {})


def _pick_entity(search_results: list, sport_keyword: str) -> Optional[str]:
    for item in search_results:
        desc = (item.get("description") or "").lower()
        if sport_keyword in desc:
            return item.get("id")
    return search_results[0].get("id") if search_results else None


def _extract_birthdate(entity: dict) -> Optional[str]:
    claims = entity.get("claims", {})
    if "P569" in claims:
        try:
            time_str = claims["P569"][0]["mainsnak"]["datavalue"]["value"]["time"]
            return time_str.strip("+")[:10]
        except Exception:
            return None
    return None


def _extract_country(entity: dict) -> Optional[str]:
    claims = entity.get("claims", {})
    if "P27" in claims:
        try:
            country_id = claims["P27"][0]["mainsnak"]["datavalue"]["value"]["id"]
            params = {
                "action": "wbgetentities",
                "ids": country_id,
                "format": "json",
                "props": "labels",
            }
            data = _wikidata_request(params)
            return data["entities"][country_id]["labels"].get("en", {}).get("value")
        except Exception:
            return None
    return None


def _is_human_sport_entity(entity: dict, sport: str) -> bool:
    claims = entity.get("claims", {})
    # P31: instance of human (Q5)
    if "P31" in claims:
        try:
            if not any(c["mainsnak"]["datavalue"]["value"]["id"] == "Q5" for c in claims["P31"]):
                return False
        except Exception:
            return False
    else:
        return False
    # P106: occupation (required)
    if "P106" not in claims:
        return False
    occupation_ids = []
    for c in claims["P106"]:
        try:
            occupation_ids.append(c["mainsnak"]["datavalue"]["value"]["id"])
        except Exception:
            continue
    # tennis player Q10833314, table tennis player Q1700471
    if sport == "tennis" and "Q10833314" not in occupation_ids:
        return False
    if sport == "table-tennis" and "Q1700471" not in occupation_ids:
        return False
    return True


def resolve_birthdate(name: str, sport: str, db: Session) -> Optional[str]:
    name_norm = normalize_name(name)
    player = db.query(Player).filter(Player.sport == sport, Player.name_norm == name_norm).first()
    if player and player.birthdate:
        return player.birthdate

    sport_keyword = "tennis player" if sport == "tennis" else "table tennis"
    results = _wikidata_search(name, sport_keyword)
    if not results:
        results = _wikidata_search(name, "")
    entity_id = _pick_entity(results, sport_keyword)
    if not entity_id:
        return None

    entity = _wikidata_get(entity_id)
    birthdate = _extract_birthdate(entity)
    if not birthdate:
        return None

    if player:
        player.birthdate = birthdate
    else:
        player = Player(
            name=name.strip(),
            name_norm=name_norm,
            birthdate=birthdate,
            sport=sport,
        )
        db.add(player)
    db.commit()
    return birthdate

# Seed players data (run once)
@app.post("/admin/seed-players")
def seed_players(
    request: Request,
    db: Session = Depends(get_db),
):
    """Seed player database (idempotent upsert). Requires ADMIN_KEY header."""
    admin_key = request.headers.get("X-Admin-Key")
    expected_key = os.getenv("ADMIN_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured")
    if admin_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    
    players = [
        
    ]
    
    deduped = {}
    seed_use_birthdates = os.getenv("SEED_USE_BIRTHDATES", "false").lower() == "true"

    for p in players:
        name = p["name"].strip()
        sport = p["sport"].strip()
        birthdate = (p.get("birthdate") or "").strip() if seed_use_birthdates else ""
        if not birthdate:
            birthdate = None
        country = (p.get("country") or "").strip() or None

        name_norm = normalize_name(name)

        # key: same person in same sport, ignore duplicates
        k = (sport, name_norm)
        if k not in deduped:
            deduped[k] = {
                "name": name,
                "name_norm": name_norm,
                "birthdate": birthdate,
                "sport": sport,
                "country": country,
            }
        else:
            # if existing is missing country and new has it, fill it
            if not deduped[k].get("country") and country:
                deduped[k]["country"] = country

    rows = list(deduped.values())

    # Upsert via Postgres ON CONFLICT (sport, name_norm)
    stmt = pg_insert(Player).values(rows)

    update_cols = {
        # keep name fresh (latest pretty formatting)
        "name": stmt.excluded.name,
        # only overwrite birthdate if seed provides a non-empty value
        "birthdate": func.coalesce(func.nullif(stmt.excluded.birthdate, ""), Player.birthdate),
        # only update country if new one is not null
        "country": stmt.excluded.country,
    }

    stmt = stmt.on_conflict_do_update(
        constraint="uq_players_sport_name_norm",
        set_=update_cols,
    )

    result = db.execute(stmt)
    db.commit()

    return {
        "message": "Seed completed (upsert)",
        "input_count": len(players),
        "deduped_count": len(rows),
        "note": "Upserted by (sport, name_norm). No deletes performed.",
    }

# ---------------- FRONTEND (Vite React SPA) ----------------
# Base paths (work both locally and in Docker/Railway)
BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Built React app output (Vite `npm run build`)
frontend_dist_path = os.path.join(BASE_PATH, "frontend", "dist")
static_path = os.path.join(BASE_PATH, "static")

# Fallbacks for typical Docker/Railway layout
if not os.path.exists(frontend_dist_path):
    frontend_dist_path = "/app/frontend/dist"

if not os.path.exists(static_path):
    static_path = "/app/static"

# Mount backend static if present
if os.path.isdir(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    print(f"Static files mounted from: {static_path}")
else:
    print(f"Warning: static path not found: {static_path}")

# Mount Vite assets (/assets/*) so JS/CSS always work
assets_path = os.path.join(frontend_dist_path, "assets")
if os.path.isdir(assets_path):
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    print(f"Frontend assets mounted from: {assets_path}")
else:
    print(f"Warning: frontend assets path not found: {assets_path}")

def _spa_index() -> FileResponse:
    index_path = os.path.join(frontend_dist_path, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Frontend not built (index.html missing)")
    return FileResponse(index_path)

# Serve SPA entry on /
@app.get("/", include_in_schema=False)
def serve_frontend_root():
    return _spa_index()

# SPA history fallback for client-side routes (/login, /signup, /dashboard, ...)
# IMPORTANT: this must be AFTER your API routes in the file (it is).
@app.get("/{path:path}", include_in_schema=False)
def serve_frontend_spa(path: str):
    # Let API/static routes behave normally
    if path.startswith((
        "api/",
        "auth/",
        "assets/",
        "static/",
        "admin/",
        "health",
        "openapi.json",
    )):
        raise HTTPException(status_code=404, detail="Not Found")

    # Optional: if someone requests a file that doesn't exist, still return SPA
    return _spa_index()

# Optional: docs route, try to serve docs.html from the built frontend or static
@app.get("/docs", include_in_schema=False)
def serve_docs():
    candidate_paths = [
        os.path.join(frontend_dist_path, "docs.html"),
        os.path.join(static_path, "docs.html"),
    ]
    for p in candidate_paths:
        if os.path.exists(p):
            return FileResponse(p)
    raise HTTPException(status_code=404, detail="Docs page not found")

# Railway provides PORT env var, fallback to 8000 for local runs
port = int(os.getenv("PORT", 8000))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)