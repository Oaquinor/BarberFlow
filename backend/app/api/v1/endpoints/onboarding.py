"""
Onboarding API endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from datetime import datetime

from app.core import get_db
from app.schemas.onboarding import (
    OnboardingComplete,
    BarbershopProfile,
    DashboardLayoutResponse,
    ContextualMessage,
    OnboardingStep1,
    OnboardingStep3,
    OnboardingStep4,
    OnboardingStep5,
    OnboardingStep6,
    OnboardingStep7,
    OnboardingStep8,
    OnboardingStep9
)
from app.services.onboarding_service import OnboardingService


router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/complete", response_model=BarbershopProfile)
def complete_onboarding(
    data: OnboardingComplete,
    barbershop_id: int = 1,  # TODO: Get from auth
    db: Session = Depends(get_db)
):
    """
    Complete onboarding process with all barbershop personalization data.
    """
    try:
        barbershop = OnboardingService.complete_onboarding(db, barbershop_id, data)
        return BarbershopProfile.from_orm(barbershop)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/profile", response_model=BarbershopProfile)
def get_barbershop_profile(
    barbershop_id: int = 1,  # TODO: Get from auth
    db: Session = Depends(get_db)
):
    """
    Get barbershop profile including personalization settings.
    """
    profile = OnboardingService.get_barbershop_profile(db, barbershop_id)

    if not profile:
        raise HTTPException(status_code=404, detail="Barbershop not found")

    return profile


@router.get("/dashboard-layout", response_model=DashboardLayoutResponse)
def get_dashboard_layout(
    barbershop_id: int = 1,  # TODO: Get from auth
    db: Session = Depends(get_db)
):
    """
    Get dashboard layout adapted to barbershop's primary goal.
    """
    return OnboardingService.get_dashboard_layout(db, barbershop_id)


@router.get("/greeting", response_model=ContextualMessage)
def get_contextual_greeting(
    barbershop_id: int = 1,  # TODO: Get from auth
    db: Session = Depends(get_db)
):
    """
    Get contextual greeting message based on time and barbershop.
    """
    current_hour = datetime.now().hour
    return OnboardingService.get_contextual_greeting(db, barbershop_id, current_hour)


@router.post("/motivational-message", response_model=Optional[ContextualMessage])
def get_motivational_message(
    context: dict,
    barbershop_id: int = 1,  # TODO: Get from auth
    db: Session = Depends(get_db)
):
    """
    Get motivational message based on performance context.

    Example context:
    {
        "achievement_type": "perfect_week"
    }
    """
    return OnboardingService.get_motivational_message(db, barbershop_id, context)


@router.post("/upload-logo")
async def upload_logo(
    file: UploadFile = File(...),
    barbershop_id: int = 1,  # TODO: Get from auth
    db: Session = Depends(get_db)
):
    """
    Upload barbershop logo.

    Accepts: PNG, JPG, JPEG
    Max size: 5MB
    """
    # Validate file type
    if file.content_type not in ["image/png", "image/jpeg", "image/jpg"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only PNG and JPG allowed."
        )

    # TODO: Implement actual file upload to storage (S3, local, etc.)
    # For now, return mock URL
    logo_url = f"/uploads/barbershops/{barbershop_id}/logo_{file.filename}"

    # Update barbershop
    try:
        barbershop = OnboardingService.update_barbershop_logo(db, barbershop_id, logo_url)
        return {
            "success": True,
            "logo_url": logo_url,
            "message": "Logo uploaded successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/brand-colors")
def update_brand_colors(
    data: OnboardingStep3,
    barbershop_id: int = 1,  # TODO: Get from auth
    db: Session = Depends(get_db)
):
    """
    Update barbershop brand colors.
    """
    try:
        barbershop = OnboardingService.update_brand_colors(
            db,
            barbershop_id,
            data.primary_color,
            data.secondary_color
        )
        return {
            "success": True,
            "primary_color": barbershop.primary_color,
            "secondary_color": barbershop.secondary_color,
            "message": "Colors updated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/step/1")
def onboarding_step_1(
    data: OnboardingStep1,
    barbershop_id: int = 1,
    db: Session = Depends(get_db)
):
    """Save step 1: Barbershop name"""
    from app.models.barbershop import Barbershop

    barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()
    if not barbershop:
        raise HTTPException(status_code=404, detail="Barbershop not found")

    barbershop.name = data.barbershop_name
    db.commit()

    return {"success": True, "message": "Step 1 completed"}


@router.post("/step/3")
def onboarding_step_3(
    data: OnboardingStep3,
    barbershop_id: int = 1,
    db: Session = Depends(get_db)
):
    """Save step 3: Brand colors"""
    return update_brand_colors(data, barbershop_id, db)


@router.post("/step/4")
def onboarding_step_4(
    data: OnboardingStep4,
    barbershop_id: int = 1,
    db: Session = Depends(get_db)
):
    """Save step 4: Style"""
    from app.models.barbershop import Barbershop

    barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()
    if not barbershop:
        raise HTTPException(status_code=404, detail="Barbershop not found")

    barbershop.style = data.style
    db.commit()

    return {"success": True, "message": "Step 4 completed"}


@router.post("/step/5")
def onboarding_step_5(
    data: OnboardingStep5,
    barbershop_id: int = 1,
    db: Session = Depends(get_db)
):
    """Save step 5: Primary goal"""
    from app.models.barbershop import Barbershop

    barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()
    if not barbershop:
        raise HTTPException(status_code=404, detail="Barbershop not found")

    barbershop.primary_goal = data.primary_goal
    db.commit()

    return {"success": True, "message": "Step 5 completed"}


@router.post("/step/6")
def onboarding_step_6(
    data: OnboardingStep6,
    barbershop_id: int = 1,
    db: Session = Depends(get_db)
):
    """Save step 6: Team size"""
    from app.models.barbershop import Barbershop

    barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()
    if not barbershop:
        raise HTTPException(status_code=404, detail="Barbershop not found")

    barbershop.team_size = data.team_size
    db.commit()

    return {"success": True, "message": "Step 6 completed"}


@router.post("/step/7")
def onboarding_step_7(
    data: OnboardingStep7,
    barbershop_id: int = 1,
    db: Session = Depends(get_db)
):
    """Save step 7: Average service duration"""
    from app.models.barbershop import Barbershop

    barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()
    if not barbershop:
        raise HTTPException(status_code=404, detail="Barbershop not found")

    barbershop.avg_service_duration = data.avg_service_duration
    db.commit()

    return {"success": True, "message": "Step 7 completed"}


@router.post("/step/8")
def onboarding_step_8(
    data: OnboardingStep8,
    barbershop_id: int = 1,
    db: Session = Depends(get_db)
):
    """Save step 8: Business hours"""
    from app.models.barbershop import Barbershop
    from datetime import time

    barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()
    if not barbershop:
        raise HTTPException(status_code=404, detail="Barbershop not found")

    opening_parts = data.opening_time.split(':')
    closing_parts = data.closing_time.split(':')
    barbershop.opening_time = time(int(opening_parts[0]), int(opening_parts[1]))
    barbershop.closing_time = time(int(closing_parts[0]), int(closing_parts[1]))
    db.commit()

    return {"success": True, "message": "Step 8 completed"}


@router.post("/step/9")
def onboarding_step_9(
    data: OnboardingStep9,
    barbershop_id: int = 1,
    db: Session = Depends(get_db)
):
    """Save step 9: Personality"""
    from app.models.barbershop import Barbershop

    barbershop = db.query(Barbershop).filter(Barbershop.id == barbershop_id).first()
    if not barbershop:
        raise HTTPException(status_code=404, detail="Barbershop not found")

    barbershop.personality = data.personality
    db.commit()

    return {"success": True, "message": "Step 9 completed"}
