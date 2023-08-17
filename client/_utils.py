from datetime import date
from datetime import datetime as dt
from itertools import chain
from typing import Dict
from typing import List

from _constants import CIK_LENGTH, DATE_FORMAT_TOKENS
from _types import FormsDownloadMetadata, SubmissionsType


def validate_cik(cik: str) -> str:
    cik = str(cik).strip().zfill(10)

    if not is_cik(cik):
        raise ValueError(
            "Invalid CIK. Please enter an valid SEC CIK at most 10 digits long."
        )

    return cik


def is_cik(cik: str) -> bool:
    try:
        int(cik)
        return 1 <= len(cik) <= 10
    except ValueError:
        return False


def merge_submission_dicts(to_merge: List[SubmissionsType]) -> SubmissionsType:
    """Merge dictionaries with same keys."""
    merged = {}
    for k in to_merge[0].keys():
        merged[k] = list(chain.from_iterable(d[k] for d in to_merge))
    return merged


def validate_and_return_cik(
        ticker_or_cik: str, ticker_to_cik_mapping: Dict[str, str]
) -> str:
    ticker_or_cik = str(ticker_or_cik).strip().upper()

    # Check for blank tickers or CIKs
    if not ticker_or_cik:
        raise ValueError("Invalid ticker or CIK. Please enter a non-blank value.")

    # Detect CIKs and ensure that they are properly zero-padded
    if is_cik(ticker_or_cik):
        if len(ticker_or_cik) > CIK_LENGTH:
            raise ValueError("Invalid CIK. CIKs must be at most 10 digits long.")
        # SEC Edgar APIs require zero-padded CIKs, so we must pad CIK with 0s
        # to ensure that it is exactly 10 digits long
        cik = ticker_or_cik.zfill(CIK_LENGTH)
        # make sure it exists in the mapping
        if cik not in ticker_to_cik_mapping.values():
            raise ValueError(
                "Invalid CIK. Not present in the CIK to ticker mapping."
            )
        return cik

    cik = ticker_to_cik_mapping.get(ticker_or_cik)

    if cik is None:
        raise ValueError(
            "Ticker is invalid and cannot be mapped to a CIK. "
            "Please enter a valid ticker or CIK."
        )

    return cik


def validate_and_parse_date(date_format: str) -> date:
    error_msg_base = "Please enter a date string of the form YYYY-MM-DD."

    if not isinstance(date_format, str):
        raise TypeError(error_msg_base)

    try:
        return dt.strptime(date_format, DATE_FORMAT_TOKENS).date()
    except ValueError as exc:
        # Re-raise with custom error message
        raise ValueError(f"Incorrect date format. {error_msg_base}") from exc


def within_requested_date_range(
        download_metadata: FormsDownloadMetadata,
        filing_date: str,
) -> bool:
    target_date = dt.strptime(filing_date, DATE_FORMAT_TOKENS).date()
    return download_metadata.after <= target_date <= download_metadata.before

def get_valid_after_date(after, after_date):
    if after is None:
        return after_date

    after_date = validate_and_parse_date(after)
    return max(after_date, after_date)