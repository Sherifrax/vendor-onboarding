"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, Header, HTTPException, status
from fastapi import Request as HttpRequest
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile

from app.ai import DocumentClassifier, FakeAI, get_extractor
from app.config import get_settings
from app.db import SessionLocal, check_database
from app.errors import record_error
from app.mail import ConsoleMailer
from app.models import Document
from app.models import Request as VendorRequest
from app.scheduler import start_scheduler
from app.schemas import IncomingEmail, IntakeResponse
from app.services.audit import log
from app.services.documents import MAX_DOCUMENT_BYTES, review, upload
from app.services.gate import run as run_gate
from app.services.intake import derive_thread_id, process_email
from app.services.jobs import run_reminders_job
from app.services.tokens import consume, verify
from app.storage import get_storage

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Run the optional local scheduler only for the application's lifetime."""

    application.state.scheduler = start_scheduler(settings, application.state.mailer)
    yield
    scheduler = application.state.scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Vendor Onboarding Automation", version="0.1.0", lifespan=lifespan)
app.state.extractor = get_extractor(settings)
app.state.document_classifier: DocumentClassifier = (
    app.state.extractor if settings.document_ai_mode == "live" else FakeAI()
)
app.state.mailer = ConsoleMailer()
app.state.storage = get_storage(settings)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.exception_handler(Exception)
async def workflow_exception_handler(http_request: HttpRequest, error: Exception) -> JSONResponse:
    """Fail softly with a generic response after independently alerting and auditing."""

    await record_error(getattr(http_request.state, "tracking_id", None), error, app.state.mailer)
    return JSONResponse(status_code=500, content={"detail": "workflow error"})


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
async def intake_email(email: IncomingEmail, http_request: HttpRequest) -> IntakeResponse:
    """Run extract → identify/upsert → validate for one untrusted manual email."""

    http_request.state.tracking_id = f"VR-{derive_thread_id(email)}"
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
    """Render one private upload input for each required document type."""

    action = await _valid_token(token, "document_upload")
    document_types = action.payload.get("document_types", [])
    return templates.TemplateResponse(
        http_request,
        "document_form.html",
        {"action": http_request.url.path, "document_types": document_types},
    )


@app.post("/forms/documents/{token}", response_class=HTMLResponse, tags=["forms"])
async def submit_document_form(token: str, http_request: HttpRequest) -> HTMLResponse:
    """Validate private uploads and route them to hold or human review."""

    async with SessionLocal.begin() as session:
        action = await verify(session, token, "document_upload")
        if action is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invalid action link")
        form = await http_request.form()
        document_types = [str(item) for item in action.payload.get("document_types", [])]
        files: dict[str, tuple[str, bytes]] = {}
        for index, document_type in enumerate(document_types):
            upload_file = form.get(f"file_{index}")
            if isinstance(upload_file, UploadFile) and upload_file.filename:
                content = await upload_file.read(MAX_DOCUMENT_BYTES + 1)
                files[document_type] = (upload_file.filename, content)
        request = await session.get(VendorRequest, action.tracking_id)
        assert request is not None
        if request.documents_clearance != "pending_upload":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="documents are not awaiting upload"
            )
        outcome = await upload(
            session,
            request,
            files,
            document_types,
            app.state.document_classifier,
            app.state.storage,
            app.state.mailer,
        )
    return HTMLResponse(f"<p>Document upload result: {escape(outcome)}</p>")


@app.get("/forms/review/{token}", response_class=HTMLResponse, tags=["forms"])
async def review_form(token: str, http_request: HttpRequest) -> HTMLResponse:
    """Show the human document-review form without consuming its action token."""

    await _valid_token(token, "document_review")
    return _form_page(
        http_request,
        "Document review",
        token,
        "<label>Decision <select name='decision'><option value='accept_all'>Accept all</option>"
        "<option value='reject'>Reject</option></select></label>"
        "<label>Notes <textarea name='notes'></textarea></label>",
    )


@app.post("/forms/review/{token}", response_class=HTMLResponse, tags=["forms"])
async def submit_review_form(
    token: str,
    decision: Annotated[str, Form()],
    notes: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Consume a reviewer action, update all referenced documents, then run the gate."""

    if decision not in {"accept_all", "reject"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid decision"
        )
    async with SessionLocal.begin() as session:
        action = await consume(session, token, "document_review")
        if action is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invalid action link")
        document_ids = [int(item) for item in action.payload.get("document_ids", [])]
        outcome = await review(
            session, action.tracking_id, document_ids, decision, notes, app.state.mailer
        )
    return HTMLResponse(f"<p>Document review recorded: {escape(outcome)}</p>")


@app.get("/documents/download/{token}", tags=["documents"])
async def download_document(token: str) -> Response:
    """Serve a local private file only after a short-lived download token validates."""

    async with SessionLocal() as session:
        action = await verify(session, token, "document_download")
        if action is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="invalid download link"
            )
        document_id = action.payload.get("document_id")
        document = await session.get(Document, document_id)
        if document is None or document.tracking_id != action.tracking_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
        content = await app.state.storage.get(document.storage_key)
        return Response(
            content=content,
            media_type=document.mime,
            headers={"Content-Disposition": f'attachment; filename="{document.original_filename}"'},
        )


@app.post("/gate/{tracking_id}", tags=["gate"])
async def gate(tracking_id: str) -> dict[str, str | None]:
    """Run the idempotent internal final gate against freshly-read request state."""

    async with SessionLocal.begin() as session:
        result = await run_gate(session, tracking_id, app.state.mailer)
    return {"outcome": result.outcome, "reason": result.reason}


@app.post("/jobs/reminders", tags=["jobs"])
async def reminders_job(
    x_admin_token: Annotated[str | None, Header()] = None,
) -> dict[str, int]:
    """Run document reminders only for callers holding the configured admin token."""

    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin token required")
    result = await run_reminders_job(app.state.mailer)
    return {
        "first_reminders": result.first_reminders,
        "second_reminders": result.second_reminders,
        "escalations": result.escalations,
    }
