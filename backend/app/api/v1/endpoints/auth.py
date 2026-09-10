from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any
from app.schemas.auth import UserRegister, TokenResponse, TokenRefresh, UserResponse
from app.services.auth_service import auth_service
from app.dependencies import get_db, get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_token, TOKEN_TYPE_REFRESH

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: AsyncSession = Depends(get_db)) -> Any:
    """Register a new user."""
    return await auth_service.register_user(db, user_data)

@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Login to get access and refresh tokens."""
    user = await auth_service.authenticate_user(db, form_data.username, form_data.password)
    access_token = create_access_token(data={"sub": str(user.id)}, token_version=user.token_version)
    refresh_token = create_refresh_token(data={"sub": str(user.id)}, token_version=user.token_version)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

@router.post("/refresh", response_model=TokenResponse)
async def refresh(token_data: TokenRefresh, db: AsyncSession = Depends(get_db)) -> Any:
    """Refresh access token. Only accepts a refresh token, not an access token."""
    token_payload = decode_token(token_data.refresh_token, expected_type=TOKEN_TYPE_REFRESH)
    try:
        user_id = int(token_payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = await auth_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if token_payload.get("ver") != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")
        
    access_token = create_access_token(data={"sub": str(user.id)}, token_version=user.token_version)
    refresh_token = create_refresh_token(data={"sub": str(user.id)}, token_version=user.token_version)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

@router.post("/logout-all", status_code=status.HTTP_200_OK)
async def logout_all(current_user: Any = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Any:
    """Invalidate all active tokens for the current user."""
    current_user.token_version += 1
    db.add(current_user)
    await db.commit()
    return {"message": "All tokens revoked successfully"}

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: Any = Depends(get_current_user)) -> Any:
    """Get current user."""
    return current_user
