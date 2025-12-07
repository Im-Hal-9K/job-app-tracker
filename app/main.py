"""Main FastAPI application."""

import logging
from datetime import datetime
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import init_db, get_db, SessionLocal
from app.models import Application, ApplicationStatus, Notification, Interview, AppSettings, User
from app.routers import applications, resumes, sync, interviews, notifications, export, followups, auth
from app.routers.auth import get_user_from_session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create FastAPI app
app = FastAPI(
    title="Job Tracker",
    description="Personal job application tracking system",
    version="2.0.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")


# Middleware to add user to all template contexts
@app.middleware("http")
async def add_user_to_request(request: Request, call_next):
    """Add current user to request state for templates."""
    db = SessionLocal()
    try:
        request.state.user = get_user_from_session(request, db)
    finally:
        db.close()
    response = await call_next(request)
    return response


# Include routers
app.include_router(auth.router)
app.include_router(applications.router)
app.include_router(resumes.router)
app.include_router(sync.router)
app.include_router(interviews.router)
app.include_router(notifications.router)
app.include_router(export.router)
app.include_router(followups.router)


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    init_db()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Main dashboard with overview stats."""
    # Get current user
    user = getattr(request.state, 'user', None)

    # Redirect to login if not authenticated
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)

    # Base query filtered by user
    user_apps = db.query(Application).filter(Application.user_id == user.id)

    # Get counts by status
    status_counts = {}
    for status in ApplicationStatus:
        count = user_apps.filter(Application.status == status).count()
        status_counts[status.value] = count

    total = sum(status_counts.values())

    # Get recent applications
    recent = user_apps.order_by(
        Application.last_updated.desc()
    ).limit(5).all()

    # Get recent status changes
    from app.models import StatusChange
    recent_changes = db.query(StatusChange).join(Application).filter(
        Application.user_id == user.id
    ).order_by(StatusChange.changed_at.desc()).limit(10).all()

    # Calculate response rate
    responded = status_counts.get('declined', 0) + status_counts.get('interviewing', 0) + \
               status_counts.get('screening', 0) + status_counts.get('offer', 0) + \
               status_counts.get('accepted', 0)
    response_rate = (responded / total * 100) if total > 0 else 0

    # Interview rate
    interviewed = status_counts.get('interviewing', 0) + status_counts.get('offer', 0) + \
                  status_counts.get('accepted', 0)
    interview_rate = (interviewed / total * 100) if total > 0 else 0

    # Notification count (for this user's applications)
    unread_notifications = db.query(func.count(Notification.id)).join(
        Application, Notification.application_id == Application.id
    ).filter(
        Application.user_id == user.id,
        Notification.is_read == False
    ).scalar() or 0

    # Upcoming interviews
    upcoming_interviews = db.query(Interview).join(Application).filter(
        Application.user_id == user.id,
        Interview.scheduled_at >= datetime.utcnow()
    ).order_by(Interview.scheduled_at.asc()).limit(3).all()

    # Check if setup is complete
    setup_complete = db.query(AppSettings).filter(
        AppSettings.key == "setup_complete"
    ).first()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "status_counts": status_counts,
        "total": total,
        "recent": recent,
        "recent_changes": recent_changes,
        "response_rate": response_rate,
        "interview_rate": interview_rate,
        "statuses": ApplicationStatus,
        "unread_notifications": unread_notifications,
        "upcoming_interviews": upcoming_interviews,
        "show_setup_wizard": not setup_complete
    })


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
