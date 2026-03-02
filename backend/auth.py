from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import secrets
import os
import bcrypt

from database import get_db, APIKey, User, UsageLog

# Security configuration
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Use bcrypt directly to avoid passlib's 72 byte check
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)
security = HTTPBearer(auto_error=False)

def truncate_password(password: str) -> str:
    """Truncate password to 72 bytes (bcrypt limit)"""
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        return password_bytes[:72].decode('utf-8', errors='ignore')
    return password

def verify_password(plain_password, hashed_password):
    """Verify password using bcrypt directly"""
    try:
        # Truncate to 72 bytes
        plain_password = truncate_password(plain_password)
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        print(f"Password verification error: {e}")
        return False

def get_password_hash(password):
    """Hash password using bcrypt directly with truncation"""
    # Truncate to 72 bytes before hashing
    password = truncate_password(password)
    # Generate salt and hash
    salt = bcrypt.gensalt(rounds=10)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        return email
    except JWTError:
        return None

def _apply_subscription_downgrade_if_needed(user: User, db: Session) -> User:
    """Downgrade user to free if subscription expired beyond 24h grace."""
    try:
        if not user:
            return user
        tier = (user.plan_tier or "free").lower()
        if tier == "free":
            return user
        if not getattr(user, "plan_expires_at", None):
            return user

        now = datetime.utcnow()
        grace_deadline = user.plan_expires_at + timedelta(hours=24)
        if now > grace_deadline:
            user.plan_tier = "free"
            db.commit()
    except Exception:
        # best-effort; don't block auth
        pass
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    email = verify_token(credentials.credentials)
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = _apply_subscription_downgrade_if_needed(user, db)
    return user

async def get_api_key_user(
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db)
) -> User:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide X-API-Key header."
        )
    
    api_key_record = db.query(APIKey).filter(
        APIKey.api_key == x_api_key,
        APIKey.active == True
    ).first()
    
    if not api_key_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key"
        )
    
    # Update last used
    api_key_record.last_used = datetime.utcnow()
    api_key_record.request_count += 1
    db.commit()
    
    user = api_key_record.user
    user = _apply_subscription_downgrade_if_needed(user, db)
    return user

TIER_DAILY_LIMITS = {
    "free": 10,
    "starter": 100,
    "pro": 1000,  # soft cap + fair use
}


def check_rate_limit(user: User, db: Session):
    """User-specific 24h epochs.

    Each user has an anchor timestamp. Quota resets every 24h from that anchor.
    This avoids timezone/DST issues and gives a clear "full reset" moment.

    - If anchor is missing, we set it at first successful request.
    - The current epoch is [anchor + k*24h, anchor + (k+1)*24h).
    """
    from datetime import timedelta

    tier = (user.plan_tier or "free").lower()
    limit = TIER_DAILY_LIMITS.get(tier, TIER_DAILY_LIMITS["free"])

    now = datetime.utcnow()

    anchor = getattr(user, "rate_epoch_anchor_at", None)
    if not anchor:
        # Initialize anchor at first use. We don't commit here yet; only if request succeeds.
        anchor = now

    # Find current epoch boundaries
    elapsed = now - anchor
    if elapsed.total_seconds() < 0:
        # clock skew; reset anchor to now
        anchor = now
        elapsed = timedelta(0)

    epoch_len = timedelta(hours=24)
    k = int(elapsed.total_seconds() // epoch_len.total_seconds())
    epoch_start = anchor + (k * epoch_len)
    epoch_end = epoch_start + epoch_len

    request_count = db.query(UsageLog).filter(
        UsageLog.user_id == user.id,
        UsageLog.timestamp >= epoch_start,
        UsageLog.timestamp < epoch_end,
        UsageLog.success == True,
    ).count()

    if request_count >= limit:
        detail = {
            "message": f"Daily limit exceeded for {tier} tier.",
            "tier": tier,
            "limit": limit,
            "used": request_count,
            "remaining": 0,
            "reset_time": epoch_end.isoformat() + "Z",
            "window": "user_epoch_24h",
        }
        if tier == "pro":
            detail["fair_use"] = "Pro includes a soft cap and is subject to fair-use policy for abuse prevention."

        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)

    return True

def generate_api_key():
    """Generate a secure API key"""
    return "sn_" + secrets.token_urlsafe(32)

def log_usage(user_id: int, endpoint: str, success: bool = True, error_message: str = None, db: Session = None):
    """Log API usage.

    When a user makes their first *successful* request, initialize their 24h epoch anchor.
    """
    log_entry = UsageLog(
        user_id=user_id,
        endpoint=endpoint,
        success=success,
        error_message=error_message
    )
    db.add(log_entry)

    if success:
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user and not getattr(user, "rate_epoch_anchor_at", None):
                user.rate_epoch_anchor_at = log_entry.timestamp
        except Exception:
            pass

    db.commit()
