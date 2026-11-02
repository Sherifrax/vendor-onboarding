"""FastAPI application entry point."""

from html import escape
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, status
from fastapi import Request as HttpRequest
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.ai import get_extractor
from app.config import get_settings
from app.db import SessionLocal, check_database
from app.mail import ConsoleMailer
from app.models import Request as VendorRequest
from app.schemas import IncomingEmail, IntakeResponse
from app.services.audit import log
from app.services.gate import run as run_gate
from app.services.intake import process_email
from app.services.tokens import consume, verify

app = FastAPI(title="Vendor Onboarding Automation", version="0.1.0")
app.state.extractor = get_extractor(get_settings())
app.state.mailer = ConsoleMailer()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


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


def _form_page(http_request: HttpRequest, title: str, token: str, fields: str) -> HTMLResponse:
    """Render deliberately small server-side action forms."""

    return templates.TemplateResponse(
        http_request,
        "action_form.html",
        {
            "title": title,
            "action": http_request.url.path,
            "token": token,
            "fields": fields,
        },
    )


async def _valid_token(token: str, purpose: str):
    async with SessionLocal() as session:
        action = await verify(session, token, purpose)
        if action is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invalid action link")
        return action


@app.get("/forms/manager/{token}", response_class=HTMLResponse, tags=["forms"])
async def manager_form(token: str, http_request: HttpRequest) -> HTMLResponse:
    """Show the single-use manager decision form without consuming its token."""

    await _valid_token(token, "manager_decision")
    return _form_page(
        http_request,
        "Sourcing manager decision",
        token,
        "<label>Decision <select name='decision'><option value='approve'>Approve</option>"
        "<option value='reject'>Reject</option><option value='more_info'>Request more information"
        "</option></select></label><label>Comments <textarea name='comments'></textarea></label>",
    )


@app.post("/forms/manager/{token}", response_class=HTMLResponse, tags=["forms"])
async def submit_manager_form(
    token: str,
    decision: Annotated[str, Form()],
    comments: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Consume a manager token, persist its decision, and invoke the final gate."""

    if decision not in {"approve", "reject", "more_info"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid decision"
        )
    async with SessionLocal.begin() as session:
        action = await consume(session, token, "manager_decision")
        if action is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invalid action link")
        request = await session.get(VendorRequest, action.tracking_id)
        assert request is not None
        if decision == "approve":
            request.financial_clearance = "cleared_by_human_review"
            request.status = "manager_approved"
            await log(
                session, request.tracking_id, "manager", "approved", "PASS", comments, "manager"
            )
            result = await run_gate(session, request.tracking_id, app.state.mailer)
        elif decision == "reject":
            request.financial_clearance = "rejected_by_sourcing_manager"
            request.status = "manager_rejected"
            await log(
                session, request.tracking_id, "manager", "rejected", "HOLD", comments, "manager"
            )
            result = await run_gate(session, request.tracking_id, app.state.mailer)
        else:
            request.financial_clearance = "more_information_requested"
            request.status = "needs_info"
            await log(
                session,
                request.tracking_id,
                "manager",
                "more_information_requested",
                "WAIT",
                comments,
                "manager",
            )
            from app.mail import send

            await send(
                session,
                app.state.mailer,
                request.requestor_email or "",
                "Vendor request: more information needed",
                f"The sourcing manager requested more information: {comments}",
                "manager_more_info",
                request.tracking_id,
            )
            result = None
    outcome = result.outcome if result else "MORE_INFO"
    return HTMLResponse(f"<p>Decision recorded: {escape(outcome)}</p>")


@app.get("/forms/duplicate/{token}", response_class=HTMLResponse, tags=["forms"])
async def duplicate_form(token: str, http_request: HttpRequest) -> HTMLResponse:
    """Show the master-data duplicate decision form."""

    await _valid_token(token, "duplicate_review")
    return _form_page(
        http_request,
        "Master data duplicate review",
        token,
        "<label>Decision <select name='decision'>"
        "<option value='not_duplicate'>Not a duplicate</option>"
        "<option value='duplicate'>Duplicate confirmed</option></select></label>"
        "<label>Notes <textarea name='comments'></textarea></label>",
    )


@app.post("/forms/duplicate/{token}", response_class=HTMLResponse, tags=["forms"])
async def submit_duplicate_form(
    token: str,
    decision: Annotated[str, Form()],
    comments: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Consume a duplicate token, save its outcome, then invoke the final gate."""

    if decision not in {"not_duplicate", "duplicate"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid decision"
        )
    async with SessionLocal.begin() as session:
        action = await consume(session, token, "duplicate_review")
        if action is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invalid action link")
        request = await session.get(VendorRequest, action.tracking_id)
        assert request is not None
        if decision == "not_duplicate":
            request.duplicate_clearance = "cleared_by_human_review"
            status_name, gate_decision = "cleared_by_human_review", "PASS"
        else:
            request.duplicate_clearance = "blocked_duplicate_confirmed"
            status_name, gate_decision = "blocked_duplicate_confirmed", "HOLD"
        await log(
            session,
            request.tracking_id,
            "duplicate_review",
            status_name,
            gate_decision,
            comments,
            "master_data",
        )
        result = await run_gate(session, request.tracking_id, app.state.mailer)
    return HTMLResponse(f"<p>Decision recorded: {escape(result.outcome)}</p>")


@app.get("/forms/documents/{token}", response_class=HTMLResponse, tags=["forms"])
async def document_form(token: str, http_request: HttpRequest) -> HTMLResponse:
    """Validate the upload link; Phase 5 adds file inputs and storage."""

    action = await _valid_token(token, "document_upload")
    document_types = action.payload.get("document_types", [])
    return templates.TemplateResponse(
        http_request, "document_form.html", {"document_types": document_types}
    )


@app.post("/gate/{tracking_id}", tags=["gate"])
async def gate(tracking_id: str) -> dict[str, str | None]:
    """Run the idempotent internal final gate against freshly-read request state."""

    async with SessionLocal.begin() as session:
        result = await run_gate(session, tracking_id, app.state.mailer)
    return {"outcome": result.outcome, "reason": result.reason}
