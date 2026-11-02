"""FastAPI application entry point."""

from fastapi import FastAPI, HTTPException, status

from app.db import check_database

app = FastAPI(title="Vendor Onboarding Automation", version="0.1.0")


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
