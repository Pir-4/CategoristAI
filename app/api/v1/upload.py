from uuid import UUID

import structlog
from fastapi import Depends, Request, UploadFile
from fastapi.routing import APIRouter

from app.api.dependencies import get_current_user
from app.core import AsyncSession, get_session, settings
from app.core.exceptions import AccountNotFoundError
from app.models import User
from app.schemas import (
    TransactionResponse,
    UploadCounters,
    UploadIssue,
    UploadResult,
)
from app.services.account_service import get_account_by_id, get_accounts
from app.services.csv_service import parse_transactions
from app.services.transaction_service import save_transactions

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _cap(issues: list[UploadIssue]) -> tuple[list[UploadIssue], bool]:
    """Bound the response size: a fully broken file would otherwise echo
    every row back to the client. The logs still hold everything."""
    limit = settings.upload.max_issues_in_response
    return issues[:limit], len(issues) > limit


@router.post("")
async def upload_batch(
    request: Request,
    upload_file: UploadFile,
    account_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UploadResult:
    structlog.contextvars.bind_contextvars(account_id=str(account_id))
    logger.info(
        "upload.received",
        filename=upload_file.filename,
        content_type=upload_file.content_type,
        size_bytes=upload_file.size,
    )

    current_account = await get_account_by_id(
        session=session, user=user, account_id=account_id
    )
    if not current_account:
        raise AccountNotFoundError(account_id=str(account_id))

    user_accounts = await get_accounts(session, user)
    outcome, total_rows = await parse_transactions(
        upload_file, current_account=current_account, accounts=user_accounts
    )
    report = await save_transactions(session, user, outcome.parsed)

    skipped, skipped_cut = _cap(outcome.skipped)
    failed, failed_cut = _cap(outcome.failed)
    duplicates, duplicates_cut = _cap(report.duplicates)

    counters = UploadCounters(
        total_rows=total_rows,
        parsed=len(outcome.parsed),
        saved=len(report.saved),
        duplicates=len(report.duplicates),
        skipped=len(outcome.skipped),
        failed=len(outcome.failed),
    )

    log_event = (
        logger.warning
        if outcome.failed or outcome.has_internal_errors
        else logger.info
    )
    log_event(
        "upload.completed",
        **counters.model_dump(),
        has_internal_errors=outcome.has_internal_errors,
    )

    return UploadResult(
        upload_id=getattr(request.state, "request_id", ""),
        account_id=current_account.id,
        counters=counters,
        has_internal_errors=outcome.has_internal_errors,
        issues_truncated=skipped_cut or failed_cut or duplicates_cut,
        transactions=[
            TransactionResponse.model_validate(tr) for tr in report.saved
        ],
        duplicates=duplicates,
        skipped=skipped,
        failed=failed,
    )
