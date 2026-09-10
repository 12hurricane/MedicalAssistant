from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid
import bcrypt
from jose import jwt, JWTError
from fastapi import HTTPException, status
from app.core.config import settings

# bcrypt only considers the first 72 bytes of a password. We truncate to that
# explicitly (matching passlib's historical default) so hashing and verifying
# never raise on longer inputs and always operate on the same byte sequence.
_BCRYPT_MAX_BYTES = 72

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))

def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    hashed = bcrypt.hashpw(pwd_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")

# Tokens carry a "type" claim so a refresh token can't authenticate a request and
# an access token can't be exchanged for a new pair.
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None, token_version: int = 1) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    now = datetime.now(timezone.utc)
    to_encode.update({
        "exp": expire, 
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": TOKEN_TYPE_ACCESS,
        "ver": token_version
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, token_version: int = 1) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    now = datetime.now(timezone.utc)
    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": TOKEN_TYPE_REFRESH,
        "ver": token_version
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_token(token: str, expected_type: Optional[str] = None) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if expected_type is not None and payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token type: expected a {expected_type} token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
