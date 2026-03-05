from fastapi import FastAPI, Depends, HTTPException, status, Request # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from fastapi.staticfiles import StaticFiles # type: ignore
from fastapi.responses import FileResponse, JSONResponse, Response # type: ignore
from pydantic import BaseModel, EmailStr, Field # type: ignore
from sqlalchemy.orm import Session # type: ignore
from sqlalchemy import or_, and_, func # type: ignore
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

from database import create_tables, get_db, User, APIKey, DemoUsage, Player, UsageLog, UserIPClaim, AnalysisHistory, Payment
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
    updated: Optional[bool] = False
    created: Optional[bool] = False
    verified: Optional[bool] = False

class AddPlayerRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    sport: str = Field(default="tennis", pattern=r'^(tennis|table-tennis)$')
    birthdate: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')

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
            "plan_expires_at": user.plan_expires_at.isoformat() if getattr(user, 'plan_expires_at', None) else None,
            "wallet_address": user.wallet_address,
        }
    }

@app.get("/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "created_at": current_user.created_at.isoformat(),
        "plan_tier": current_user.plan_tier,
        "plan_expires_at": current_user.plan_expires_at.isoformat() if current_user.plan_expires_at else None,
        "wallet_address": current_user.wallet_address,
    }

@app.get("/api/v1/admin-email")
def get_admin_email(current_user: User = Depends(get_current_user)):
    return {"admin_email": os.getenv("VITE_ADMIN_EMAIL") or os.getenv("ADMIN_EMAIL") or ""}


# --- Subscriptions (USDC Polygon) ---

POLYGON_USDC_CONTRACTS = {
    # Native USDC (Circle) on Polygon
    "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
    # USDC.e (bridged) still commonly used
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",
}

USDC_DECIMALS = 6
STARTER_PRICE_USDC = 19
PRO_PRICE_USDC = 49


@app.get("/api/v1/subscription/nonce")
def get_wallet_link_nonce(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import secrets
    nonce = secrets.token_hex(16)
    current_user.wallet_link_nonce = nonce
    db.commit()
    return {
        "nonce": nonce,
        "message": f"Link wallet to Sportology (user {current_user.email}): {nonce}",
    }


@app.post("/api/v1/subscription/link-wallet")
def link_wallet(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Link an EVM wallet to the current user.

    Expects: { wallet_address, signature }
    Signature must be over the exact message returned by /api/v1/subscription/nonce.
    """
    wallet_address = (payload.get("wallet_address") or "").strip()
    signature = (payload.get("signature") or "").strip()

    if not wallet_address or not signature:
        raise HTTPException(status_code=400, detail="wallet_address and signature are required")

    if not current_user.wallet_link_nonce:
        raise HTTPException(status_code=400, detail="No nonce issued. Call /api/v1/subscription/nonce first")

    message_text = f"Link wallet to Sportology (user {current_user.email}): {current_user.wallet_link_nonce}"

    try:
        from web3 import Web3
        from eth_account.messages import encode_defunct

        recovered = Web3().eth.account.recover_message(
            encode_defunct(text=message_text),
            signature=signature,
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if recovered.lower() != wallet_address.lower():
        raise HTTPException(status_code=400, detail="Signature does not match wallet_address")

    # ensure wallet not linked to another user
    other = db.query(User).filter(User.wallet_address == wallet_address).first()
    if other and other.id != current_user.id:
        raise HTTPException(status_code=409, detail="Wallet already linked to another user")

    current_user.wallet_address = wallet_address
    current_user.wallet_link_nonce = None
    db.commit()

    return {"wallet_address": current_user.wallet_address}


@app.get("/api/v1/subscription/status")
def subscription_status(current_user: User = Depends(get_current_user)):
    treasury = (os.getenv("TREASURY_WALLET") or "").strip() or None
    return {
        "plan_tier": current_user.plan_tier,
        "plan_expires_at": current_user.plan_expires_at.isoformat() if current_user.plan_expires_at else None,
        "wallet_address": current_user.wallet_address,
        "treasury_wallet": treasury,
        "prices": {"starter_usdc": STARTER_PRICE_USDC, "pro_usdc": PRO_PRICE_USDC},
        "chain": "polygon",
    }


@app.post("/api/v1/subscription/verify-payment")
def verify_payment(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify a Polygon USDC transfer transaction and credit the subscription.

    Expects: { tx_hash }
    Rules: accept exact 19 USDC (starter) or 49 USDC (pro), sent from the user's linked wallet to TREASURY_WALLET.
    """
    tx_hash = (payload.get("tx_hash") or "").strip()
    if not tx_hash:
        raise HTTPException(status_code=400, detail="tx_hash is required")

    if not current_user.wallet_address:
        raise HTTPException(status_code=400, detail="No wallet linked")

    treasury = (os.getenv("TREASURY_WALLET") or "").strip()
    if not treasury:
        raise HTTPException(status_code=500, detail="TREASURY_WALLET not configured")

    rpc_url = (os.getenv("POLYGON_RPC_URL") or "").strip()
    if not rpc_url:
        raise HTTPException(status_code=500, detail="POLYGON_RPC_URL not configured")

    # replay protection
    existing = db.query(Payment).filter(Payment.tx_hash == tx_hash).first()
    if existing:
        raise HTTPException(status_code=409, detail="Transaction already processed")

    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        receipt = w3.eth.get_transaction_receipt(tx_hash)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not fetch transaction receipt")

    if not receipt or receipt.get("status") != 1:
        raise HTTPException(status_code=400, detail="Transaction not successful")

    # USDC Transfer event
    transfer_sig = w3.keccak(text="Transfer(address,address,uint256)").hex()
    wallet_lc = current_user.wallet_address.lower()
    treasury_lc = treasury.lower()

    matched = None  # (contract, from, to, amount)
    for log in receipt.get("logs", []):
        addr = (log.get("address") or "").lower()
        if addr not in POLYGON_USDC_CONTRACTS:
            continue
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue
        if topics[0].hex() != transfer_sig:
            continue

        # topics[1] = from, topics[2] = to
        from_addr = "0x" + topics[1].hex()[-40:]
        to_addr = "0x" + topics[2].hex()[-40:]

        if to_addr.lower() != treasury_lc:
            continue
        if from_addr.lower() != wallet_lc:
            continue

        amount = int(log.get("data") or "0x0", 16)
        matched = (addr, from_addr, to_addr, amount)
        break

    if not matched:
        raise HTTPException(status_code=400, detail="No matching USDC transfer found in transaction")

    _, from_addr, to_addr, amount = matched

    starter_amount = STARTER_PRICE_USDC * (10 ** USDC_DECIMALS)
    pro_amount = PRO_PRICE_USDC * (10 ** USDC_DECIMALS)

    if amount == starter_amount:
        new_tier = "starter"
        amount_usdc = str(STARTER_PRICE_USDC)
    elif amount == pro_amount:
        new_tier = "pro"
        amount_usdc = str(PRO_PRICE_USDC)
    else:
        raise HTTPException(status_code=400, detail="Amount must be exactly 19 or 49 USDC")

    # credit 30 days (stacking)
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    base = current_user.plan_expires_at if current_user.plan_expires_at and current_user.plan_expires_at > now else now
    current_user.plan_tier = new_tier
    current_user.plan_expires_at = base + timedelta(days=30)

    payment = Payment(
        user_id=current_user.id,
        chain="polygon",
        token="USDC",
        amount_usdc=amount_usdc,
        plan_tier=new_tier,
        tx_hash=tx_hash,
        from_address=from_addr,
        to_address=to_addr,
    )

    db.add(payment)
    db.commit()

    return {
        "credited": True,
        "plan_tier": current_user.plan_tier,
        "plan_expires_at": current_user.plan_expires_at.isoformat() if current_user.plan_expires_at else None,
        "tx_hash": tx_hash,
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

        # Save history
        import json
        history = AnalysisHistory(
            user_id=current_user.id,
            sport=request.sport,
            player1_name=request.player1_name,
            player2_name=request.player2_name,
            match_date=request.match_date,
            confidence=result.get("confidence"),
            winner_prediction=result.get("winner_prediction"),
            bet_size=result.get("bet_size"),
            score_difference=str(result.get("score_difference")),
            analysis_json=json.dumps(result),
        )
        db.add(history)
        db.commit()
        
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
    """Get usage statistics for the authenticated user.

    Rate limits use user-specific 24h epochs (see auth.check_rate_limit).

    Returns:
    - epoch_used / remaining / limit / reset_time (for the quota)
    - this_month / total (for overall counters)
    """
    from datetime import timedelta

    now = datetime.utcnow()

    tier = (current_user.plan_tier or "free").lower()
    limit_by_tier = {"free": 10, "starter": 100, "pro": 1000}
    limit = limit_by_tier.get(tier, 10)

    # Epoch boundaries (stabilize anchor)
    anchor = getattr(current_user, "rate_epoch_anchor_at", None)
    if not anchor:
        first = (
            db.query(UsageLog)
            .filter(UsageLog.user_id == current_user.id, UsageLog.success == True)
            .order_by(UsageLog.timestamp.asc())
            .first()
        )
        anchor = (first.timestamp if first else None) or getattr(current_user, "created_at", None) or now
        try:
            current_user.rate_epoch_anchor_at = anchor
            db.commit()
        except Exception:
            pass
    elapsed = now - anchor
    if elapsed.total_seconds() < 0:
        anchor = now
        elapsed = timedelta(0)

    epoch_len = timedelta(hours=24)
    k = int(elapsed.total_seconds() // epoch_len.total_seconds())
    epoch_start = anchor + (k * epoch_len)
    epoch_end = epoch_start + epoch_len

    epoch_used = db.query(UsageLog).filter(
        UsageLog.user_id == current_user.id,
        UsageLog.timestamp >= epoch_start,
        UsageLog.timestamp < epoch_end,
        UsageLog.success == True,
    ).count()

    remaining = max(0, limit - epoch_used)

    # This month / total (all logs)
    month_start = datetime(now.year, now.month, 1)

    month_count = db.query(UsageLog).filter(
        UsageLog.user_id == current_user.id,
        UsageLog.timestamp >= month_start,
        UsageLog.timestamp <= now,
    ).count()

    total_count = db.query(UsageLog).filter(
        UsageLog.user_id == current_user.id
    ).count()

    return JSONResponse(
        content={
            "epoch_used": epoch_used,
            "remaining": remaining,
            "limit": limit,
            "tier": tier,
            "reset_time": epoch_end.isoformat() + "Z",
            "this_month": month_count,
            "total": total_count,
            "window": "user_epoch_24h",
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

@app.get("/admin/users")
def list_users(request: Request, db: Session = Depends(get_db)):
    admin_key = request.headers.get("X-Admin-Key")
    expected_key = os.getenv("ADMIN_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured")
    if admin_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "created_at": u.created_at.isoformat(),
            "plan_tier": u.plan_tier,
        }
        for u in users
    ]


@app.post("/admin/users/{user_id}")
async def update_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin_key = request.headers.get("X-Admin-Key")
    expected_key = os.getenv("ADMIN_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured")
    if admin_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    try:
        data = await request.json()
    except Exception:
        data = {}

    email = (data.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.email = email
    db.commit()
    return {"message": "Email updated", "user_id": user.id, "email": user.email}


@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin_key = request.headers.get("X-Admin-Key")
    expected_key = os.getenv("ADMIN_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured")
    if admin_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    return {"message": "User deleted", "user_id": user.id}


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
@app.get("/api/v1/analysis-history")
def get_analysis_history(
    current_user: User = Depends(get_current_user),
    q: str = "",
    sport: str = "",
    start_date: str = "",
    end_date: str = "",
    db: Session = Depends(get_db)
):
    query = db.query(AnalysisHistory).filter(AnalysisHistory.user_id == current_user.id)
    if sport:
        query = query.filter(AnalysisHistory.sport == sport)
    if q:
        q_raw = q.strip()
        query = query.filter(
            or_(
                AnalysisHistory.player1_name.ilike(f"%{q_raw}%"),
                AnalysisHistory.player2_name.ilike(f"%{q_raw}%"),
            )
        )
    if start_date:
        query = query.filter(AnalysisHistory.match_date >= start_date)
    if end_date:
        query = query.filter(AnalysisHistory.match_date <= end_date)

    rows = query.order_by(AnalysisHistory.created_at.desc()).limit(200).all()
    return [
        {
            "id": r.id,
            "sport": r.sport,
            "player1_name": r.player1_name,
            "player2_name": r.player2_name,
            "match_date": r.match_date,
            "confidence": r.confidence,
            "winner_prediction": r.winner_prediction,
            "bet_size": r.bet_size,
            "score_difference": r.score_difference,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@app.delete("/api/v1/analysis-history")
def clear_analysis_history(
    current_user: User = Depends(get_current_user),
    q: str = "",
    sport: str = "",
    start_date: str = "",
    end_date: str = "",
    db: Session = Depends(get_db),
):
    """Delete analysis history entries for the current user.

    If q/sport/start_date/end_date are provided, only matching rows are deleted.
    """
    query = db.query(AnalysisHistory).filter(AnalysisHistory.user_id == current_user.id)

    if sport:
        query = query.filter(AnalysisHistory.sport == sport)
    if q:
        q_raw = q.strip()
        query = query.filter(
            or_(
                AnalysisHistory.player1_name.ilike(f"%{q_raw}%"),
                AnalysisHistory.player2_name.ilike(f"%{q_raw}%"),
            )
        )
    if start_date:
        query = query.filter(AnalysisHistory.match_date >= start_date)
    if end_date:
        query = query.filter(AnalysisHistory.match_date <= end_date)

    deleted = query.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


@app.get("/api/v1/analysis-history/{history_id}")
def get_analysis_history_detail(
    history_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch the full stored analysis payload for a specific history row."""
    row = (
        db.query(AnalysisHistory)
        .filter(AnalysisHistory.id == history_id, AnalysisHistory.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="History entry not found")

    if not row.analysis_json:
        # Backward compatibility for rows created before we started storing the payload.
        raise HTTPException(status_code=404, detail="No stored analysis payload for this entry")

    import json
    try:
        payload = json.loads(row.analysis_json)
    except Exception:
        raise HTTPException(status_code=500, detail="Stored analysis payload is corrupted")

    return {
        "id": row.id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "match_date": row.match_date,
        "sport": row.sport,
        "player1_name": row.player1_name,
        "player2_name": row.player2_name,
        "analysis": payload,
    }


@app.get("/api/v1/players")
def search_players(
    q: str = "",
    sport: str = "",
    db: Session = Depends(get_db)
):
    """Search players by name (autocomplete). Uses normalized name for accents/hyphens/etc."""
    query = db.query(Player).filter(Player.verified == True)

    if sport:
        query = query.filter(Player.sport == sport)

    if q:
        q_raw = q.strip()
        q_norm = normalize_name(q_raw)

        # Token-based match on normalized name so "Federer Roger" still matches "Roger Federer",
        # and so users can type without accents/punctuation.
        tokens = [t for t in q_norm.split(" ") if t]
        if tokens:
            norm_token_filter = and_(*[Player.name_norm.ilike(f"%{t}%") for t in tokens])
        else:
            norm_token_filter = Player.name_norm.ilike(f"%{q_norm}%")

        query = query.filter(
            or_(
                norm_token_filter,
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

        tokens = [t for t in q_norm.split(" ") if t]
        if tokens:
            norm_token_filter = and_(*[Player.name_norm.ilike(f"%{t}%") for t in tokens])
        else:
            norm_token_filter = Player.name_norm.ilike(f"%{q_norm}%")

        query = query.filter(
            or_(
                norm_token_filter,
                Player.name.ilike(f"%{q_raw}%"),
            )
        )
    db_players = query.limit(10).all()
    for p in db_players:
        # If missing data, refresh from Wikidata (source of truth)
        if not p.birthdate:
            sport_keyword = "tennis player" if p.sport == "tennis" else "table tennis"
            results = _wikidata_search(p.name, sport_keyword)
            if not results:
                results = _wikidata_search(p.name, "")
            entity_id = _pick_entity(results, sport_keyword)
            if entity_id:
                entity = _wikidata_get(entity_id)
                if _is_human_sport_entity(entity, p.sport):
                    birthdate = _extract_birthdate(entity)
                    updated = False
                    if birthdate and p.birthdate != birthdate:
                        p.birthdate = birthdate
                        updated = True
                    if updated:
                        db.commit()
        suggestions.append({
            "id": p.id,
            "name": p.name,
            "birthdate": p.birthdate,
            "sport": p.sport,
            "source": "db",
        })

    # 2) Wikidata suggestions disabled — DB only
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
        "sport": player.sport
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

    updated = False
    created = False

    if existing:
        if existing.birthdate != birthdate:
            existing.birthdate = birthdate
            updated = True
        if existing.name != name:
            existing.name = name
            existing.name_norm = name_norm
            updated = True
        existing.verified = True
        updated = True
        db.commit()
        player = existing
    else:
        player = Player(
            name=name,
            name_norm=name_norm,
            birthdate=birthdate,
            sport=sport,
            verified=True,
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
        "updated": updated,
        "created": created,
        "verified": player.verified,
    }


@app.post("/api/v1/players/add", response_model=ResolvePlayerResponse)
def add_player(request: AddPlayerRequest, db: Session = Depends(get_db)):
    name = request.name.strip()
    sport = request.sport.strip()
    birthdate = request.birthdate.strip()
    if not name or not sport:
        raise HTTPException(status_code=400, detail="name and sport are required")

    name_norm = normalize_name(name)
    existing = db.query(Player).filter(Player.sport == sport, Player.name_norm == name_norm).first()
    if existing:
        raise HTTPException(status_code=409, detail="Player already exists")

    # Verify via Wikidata; if fails, mark unverified but allow add
    verified = False
    try:
        sport_keyword = "tennis player" if sport == "tennis" else "table tennis"
        results = _wikidata_search(name, sport_keyword)
        if not results:
            results = _wikidata_search(name, "")
        entity_id = _pick_entity(results, sport_keyword)
        if entity_id:
            entity = _wikidata_get(entity_id)
            if _is_human_sport_entity(entity, sport):
                verified = True
    except Exception:
        verified = False

    player = Player(
        name=name,
        name_norm=name_norm,
        birthdate=birthdate,
        sport=sport,
        verified=verified,
    )
    db.add(player)
    db.commit()
    db.refresh(player)

    return {
        "id": player.id,
        "name": player.name,
        "birthdate": player.birthdate,
        "sport": player.sport,
        "created": True,
        "verified": player.verified,
    }


@app.get("/admin/players")
def list_players_admin(request: Request, verified: Optional[bool] = None, db: Session = Depends(get_db)):
    admin_key = request.headers.get("X-Admin-Key")
    expected_key = os.getenv("ADMIN_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured")
    if admin_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    query = db.query(Player)
    if verified is not None:
        query = query.filter(Player.verified == verified)
    players = query.order_by(Player.created_at.desc()).limit(500).all()
    return [
        {"id": p.id, "name": p.name, "birthdate": p.birthdate, "sport": p.sport, "verified": p.verified}
        for p in players
    ]


@app.get("/admin/unverified-players")
def list_unverified_players(request: Request, db: Session = Depends(get_db)):
    admin_key = request.headers.get("X-Admin-Key")
    expected_key = os.getenv("ADMIN_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured")
    if admin_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    players = db.query(Player).filter(Player.verified == False).limit(200).all()
    return [
        {"id": p.id, "name": p.name, "birthdate": p.birthdate, "sport": p.sport, "verified": p.verified}
        for p in players
    ]


@app.post("/admin/unverified-players/{player_id}/verify")
def verify_player(player_id: int, request: Request, db: Session = Depends(get_db)):
    admin_key = request.headers.get("X-Admin-Key")
    expected_key = os.getenv("ADMIN_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured")
    if admin_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    player.verified = True
    db.commit()
    return {"message": "Player verified", "id": player.id}


@app.post("/admin/players/{player_id}")
async def update_player(player_id: int, request: Request, db: Session = Depends(get_db)):
    admin_key = request.headers.get("X-Admin-Key")
    expected_key = os.getenv("ADMIN_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured")
    if admin_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    try:
        data = await request.json()
    except Exception:
        data = {}

    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    name = (data.get("name") or "").strip()
    birthdate = (data.get("birthdate") or "").strip()
    sport = (data.get("sport") or "").strip()
    verified = data.get("verified")

    if name:
        player.name = name
        player.name_norm = normalize_name(name)
    if birthdate:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", birthdate):
            raise HTTPException(status_code=400, detail="birthdate must be YYYY-MM-DD")
        player.birthdate = birthdate
    if sport:
        if sport not in {"tennis", "table-tennis"}:
            raise HTTPException(status_code=400, detail="invalid sport")
        player.sport = sport
    if isinstance(verified, bool):
        player.verified = verified

    db.commit()
    return {"message": "Player updated", "id": player.id}


@app.delete("/admin/players/{player_id}")
def delete_player(player_id: int, request: Request, db: Session = Depends(get_db)):
    admin_key = request.headers.get("X-Admin-Key")
    expected_key = os.getenv("ADMIN_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured")
    if admin_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    db.delete(player)
    db.commit()
    return {"message": "Player deleted", "id": player.id}

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

    # Accept if occupation matches OR sport (P641) matches
    occupation_ids = []
    if "P106" in claims:
        for c in claims["P106"]:
            try:
                occupation_ids.append(c["mainsnak"]["datavalue"]["value"]["id"])
            except Exception:
                continue

    sport_ids = []
    if "P641" in claims:
        for c in claims["P641"]:
            try:
                sport_ids.append(c["mainsnak"]["datavalue"]["value"]["id"])
            except Exception:
                continue

    # tennis player Q10833314, table tennis player Q1700471
    if sport == "tennis":
        if "Q10833314" in occupation_ids or "Q847" in sport_ids:
            return True
        return False
    if sport == "table-tennis":
        if "Q1700471" in occupation_ids or "Q64667" in sport_ids:
            return True
        return False
    return False


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

        name_norm = normalize_name(name)

        # key: same person in same sport, ignore duplicates
        k = (sport, name_norm)
        if k not in deduped:
            deduped[k] = {
                "name": name,
                "name_norm": name_norm,
                "birthdate": birthdate,
                "sport": sport,
            }

    rows = list(deduped.values())

    # Upsert via Postgres ON CONFLICT (sport, name_norm)
    stmt = pg_insert(Player).values(rows)

    update_cols = {
        # keep name fresh (latest pretty formatting)
        "name": stmt.excluded.name,
        # only overwrite birthdate if seed provides a non-empty value
        "birthdate": func.coalesce(func.nullif(stmt.excluded.birthdate, ""), Player.birthdate),
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