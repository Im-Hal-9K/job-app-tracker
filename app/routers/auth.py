"""Authentication routes for login/register."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from itsdangerous import URLSafeTimedSerializer, BadSignature

from app.database import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

# Session serializer - use SECRET_KEY from env in production
import os
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-to-a-random-string")
serializer = URLSafeTimedSerializer(SECRET_KEY)

SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def create_session_token(user_id: int) -> str:
    """Create a signed session token."""
    return serializer.dumps({"user_id": user_id})


def get_user_from_session(request: Request, db: Session) -> Optional[User]:
    """Get the current user from session cookie."""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        return None

    try:
        data = serializer.loads(session_token, max_age=SESSION_MAX_AGE)
        user_id = data.get("user_id")
        if user_id:
            return db.query(User).filter(User.id == user_id, User.is_active == True).first()
    except BadSignature:
        pass

    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Dependency to get current user."""
    return get_user_from_session(request, db)


def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency that requires a logged-in user."""
    user = get_user_from_session(request, db)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return user


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Show login page."""
    # If already logged in, redirect to dashboard
    user = get_user_from_session(request, db)
    if user:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse("auth/login.html", {
        "request": request,
        "error": request.query_params.get("error")
    })


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Process login form."""
    # Find user by username or email
    user = db.query(User).filter(
        (User.username == username) | (User.email == username)
    ).first()

    if not user or not user.verify_password(password):
        return RedirectResponse(url="/auth/login?error=invalid", status_code=303)

    if not user.is_active:
        return RedirectResponse(url="/auth/login?error=inactive", status_code=303)

    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()

    # Create session
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(user.id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax"
    )

    logger.info(f"User {user.username} logged in")
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: Session = Depends(get_db)):
    """Show registration page."""
    # If already logged in, redirect to dashboard
    user = get_user_from_session(request, db)
    if user:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse("auth/register.html", {
        "request": request,
        "error": request.query_params.get("error")
    })


@router.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    display_name: str = Form(""),
    db: Session = Depends(get_db)
):
    """Process registration form."""
    # Validate passwords match
    if password != password_confirm:
        return RedirectResponse(url="/auth/register?error=password_mismatch", status_code=303)

    # Validate password length
    if len(password) < 6:
        return RedirectResponse(url="/auth/register?error=password_short", status_code=303)

    # Check if username exists
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return RedirectResponse(url="/auth/register?error=username_taken", status_code=303)

    # Check if email exists
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return RedirectResponse(url="/auth/register?error=email_taken", status_code=303)

    # Create user
    user = User(
        username=username,
        email=email,
        display_name=display_name or username
    )
    user.set_password(password)

    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"New user registered: {username}")

    # Auto-login after registration
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(user.id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax"
    )

    return response


@router.get("/logout")
async def logout(request: Request):
    """Log out the current user."""
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    db: Session = Depends(get_db)
):
    """Show user profile page."""
    user = get_user_from_session(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)

    return templates.TemplateResponse("auth/profile.html", {
        "request": request,
        "user": user,
        "success": request.query_params.get("success"),
        "error": request.query_params.get("error")
    })


@router.post("/profile")
async def update_profile(
    request: Request,
    display_name: str = Form(""),
    email: str = Form(...),
    current_password: str = Form(""),
    new_password: str = Form(""),
    db: Session = Depends(get_db)
):
    """Update user profile."""
    user = get_user_from_session(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)

    # Check if email is being changed to one that exists
    if email != user.email:
        existing = db.query(User).filter(User.email == email, User.id != user.id).first()
        if existing:
            return RedirectResponse(url="/auth/profile?error=email_taken", status_code=303)
        user.email = email

    user.display_name = display_name or user.username

    # Password change
    if new_password:
        if not current_password or not user.verify_password(current_password):
            return RedirectResponse(url="/auth/profile?error=wrong_password", status_code=303)
        if len(new_password) < 6:
            return RedirectResponse(url="/auth/profile?error=password_short", status_code=303)
        user.set_password(new_password)

    db.commit()

    return RedirectResponse(url="/auth/profile?success=1", status_code=303)
