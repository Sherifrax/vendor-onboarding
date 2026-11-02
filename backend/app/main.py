"""FastAPI application entry point."""

from fastapi import FastAPI, HTTPException, status

from app.ai import get_extractor
from app.config import get_settings
from app.db import SessionLocal, check_database
from app.mail import ConsoleMailer
from app.schemas import IncomingEmail, IntakeResponse
from app.services.intake import process_email

app = FastAPI(title="Vendor Onboarding Automation", version="0.1.0")
app.state.extractor = get_extractor(get_settings())
app.state.mailer = ConsoleMailer()


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Return liveness plus a real PostgreSQL connectivity check."""

    try:
        await check_database()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "db": "unavailable"},
        ) from error
    return {"status": "ok", "db": "ok"}


@app.post("/intake/email", response_model=IntakeResponse, tags=["intake"])
async def intake_email(email: IncomingEmail) -> IntakeResponse:
    """Run extract → identify/upsert → validate for one untrusted manual email."""

    async with SessionLocal.begin() as session:
        result = await process_email(session, email, app.state.extractor, app.state.mailer)
    return IntakeResponse(tracking_id=result.tracking_id, outcome=result.outcome)
