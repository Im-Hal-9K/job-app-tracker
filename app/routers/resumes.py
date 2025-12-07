"""Resume management routes."""

import os
import shutil
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Resume, Application

router = APIRouter(prefix="/resumes", tags=["resumes"])
templates = Jinja2Templates(directory="app/templates")

RESUME_DIR = "data/resumes"

# Ensure resume directory exists
os.makedirs(RESUME_DIR, exist_ok=True)


def get_current_user(request: Request):
    """Get current user from request state."""
    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return user


@router.get("/", response_class=HTMLResponse)
async def list_resumes(request: Request, db: Session = Depends(get_db)):
    """List all resumes."""
    user = get_current_user(request)

    resumes = db.query(Resume).filter(
        Resume.user_id == user.id
    ).order_by(Resume.is_default.desc(), Resume.created_at.desc()).all()

    # Count applications per resume
    resume_counts = {}
    for resume in resumes:
        count = db.query(Application).filter(
            Application.resume_id == resume.id,
            Application.user_id == user.id
        ).count()
        resume_counts[resume.id] = count

    return templates.TemplateResponse("resumes/list.html", {
        "request": request,
        "user": user,
        "resumes": resumes,
        "resume_counts": resume_counts
    })


@router.get("/upload", response_class=HTMLResponse)
async def upload_form(request: Request):
    """Show upload form."""
    user = get_current_user(request)
    return templates.TemplateResponse("resumes/upload.html", {
        "request": request,
        "user": user
    })


@router.post("/upload")
async def upload_resume(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    file: UploadFile = File(...),
    is_default: bool = Form(False)
):
    """Upload a new resume."""
    user = get_current_user(request)

    # Validate file type
    allowed_extensions = {'.pdf', '.doc', '.docx'}
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )

    # Generate unique filename with user id for isolation
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    filename = f"u{user.id}_{timestamp}_{safe_name}{file_ext}"
    file_path = os.path.join(RESUME_DIR, filename)

    # Save file
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # If this is default, unset other defaults for this user only
    if is_default:
        db.query(Resume).filter(
            Resume.user_id == user.id,
            Resume.is_default == True
        ).update({"is_default": False})

    # Create database record
    resume = Resume(
        user_id=user.id,
        name=name,
        filename=file.filename,
        file_path=file_path,
        is_default=is_default
    )
    db.add(resume)
    db.commit()

    return RedirectResponse(url="/resumes/", status_code=303)


@router.get("/{resume_id}/download")
async def download_resume(request: Request, resume_id: int, db: Session = Depends(get_db)):
    """Download a resume file."""
    user = get_current_user(request)

    resume = db.query(Resume).filter(
        Resume.id == resume_id,
        Resume.user_id == user.id
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    if not os.path.exists(resume.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        resume.file_path,
        filename=resume.filename,
        media_type="application/octet-stream"
    )


@router.post("/{resume_id}/default")
async def set_default(request: Request, resume_id: int, db: Session = Depends(get_db)):
    """Set a resume as default."""
    user = get_current_user(request)

    resume = db.query(Resume).filter(
        Resume.id == resume_id,
        Resume.user_id == user.id
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    # Unset other defaults for this user
    db.query(Resume).filter(
        Resume.user_id == user.id,
        Resume.is_default == True
    ).update({"is_default": False})

    # Set this one as default
    resume.is_default = True
    db.commit()

    return RedirectResponse(url="/resumes/", status_code=303)


@router.post("/{resume_id}/delete")
async def delete_resume(request: Request, resume_id: int, db: Session = Depends(get_db)):
    """Delete a resume."""
    user = get_current_user(request)

    resume = db.query(Resume).filter(
        Resume.id == resume_id,
        Resume.user_id == user.id
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    # Remove file
    if os.path.exists(resume.file_path):
        os.remove(resume.file_path)

    # Clear resume from user's applications only
    db.query(Application).filter(
        Application.resume_id == resume_id,
        Application.user_id == user.id
    ).update({"resume_id": None})

    # Delete record
    db.delete(resume)
    db.commit()

    return RedirectResponse(url="/resumes/", status_code=303)
