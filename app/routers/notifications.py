"""Notification routes."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Notification, Application

router = APIRouter(prefix="/notifications", tags=["notifications"])
templates = Jinja2Templates(directory="app/templates")


def get_current_user(request: Request):
    """Get current user from request state."""
    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return user


@router.get("/", response_class=HTMLResponse)
async def list_notifications(request: Request, db: Session = Depends(get_db)):
    """List all notifications."""
    user = get_current_user(request)

    # Filter notifications by user's applications
    notifications = db.query(Notification).join(
        Application, Notification.application_id == Application.id
    ).filter(
        Application.user_id == user.id
    ).order_by(
        Notification.is_read.asc(),
        Notification.created_at.desc()
    ).limit(50).all()

    unread_count = db.query(func.count(Notification.id)).join(
        Application, Notification.application_id == Application.id
    ).filter(
        Application.user_id == user.id,
        Notification.is_read == False
    ).scalar()

    return templates.TemplateResponse("notifications/list.html", {
        "request": request,
        "user": user,
        "notifications": notifications,
        "unread_count": unread_count
    })


@router.get("/count")
async def get_notification_count(request: Request, db: Session = Depends(get_db)):
    """Get unread notification count (for badge)."""
    user = getattr(request.state, 'user', None)
    if not user:
        return JSONResponse({"count": 0})

    count = db.query(func.count(Notification.id)).join(
        Application, Notification.application_id == Application.id
    ).filter(
        Application.user_id == user.id,
        Notification.is_read == False
    ).scalar()
    return JSONResponse({"count": count or 0})


@router.post("/{notification_id}/read")
async def mark_as_read(request: Request, notification_id: int, db: Session = Depends(get_db)):
    """Mark a notification as read."""
    user = get_current_user(request)

    notification = db.query(Notification).join(
        Application, Notification.application_id == Application.id
    ).filter(
        Notification.id == notification_id,
        Application.user_id == user.id
    ).first()

    if notification:
        notification.is_read = True
        db.commit()
    return RedirectResponse(url="/notifications/", status_code=303)


@router.post("/read-all")
async def mark_all_as_read(request: Request, db: Session = Depends(get_db)):
    """Mark all notifications as read."""
    user = get_current_user(request)

    # Get all notification IDs for this user's applications
    notification_ids = db.query(Notification.id).join(
        Application, Notification.application_id == Application.id
    ).filter(
        Application.user_id == user.id,
        Notification.is_read == False
    ).all()

    if notification_ids:
        ids = [n.id for n in notification_ids]
        db.query(Notification).filter(Notification.id.in_(ids)).update(
            {"is_read": True}, synchronize_session=False
        )
        db.commit()

    return RedirectResponse(url="/notifications/", status_code=303)


@router.post("/{notification_id}/delete")
async def delete_notification(request: Request, notification_id: int, db: Session = Depends(get_db)):
    """Delete a notification."""
    user = get_current_user(request)

    notification = db.query(Notification).join(
        Application, Notification.application_id == Application.id
    ).filter(
        Notification.id == notification_id,
        Application.user_id == user.id
    ).first()

    if notification:
        db.delete(notification)
        db.commit()
    return RedirectResponse(url="/notifications/", status_code=303)


@router.post("/clear-all")
async def clear_all_notifications(request: Request, db: Session = Depends(get_db)):
    """Delete all notifications."""
    user = get_current_user(request)

    # Get all notification IDs for this user's applications
    notification_ids = db.query(Notification.id).join(
        Application, Notification.application_id == Application.id
    ).filter(
        Application.user_id == user.id
    ).all()

    if notification_ids:
        ids = [n.id for n in notification_ids]
        db.query(Notification).filter(Notification.id.in_(ids)).delete(synchronize_session=False)
        db.commit()

    return RedirectResponse(url="/notifications/", status_code=303)
