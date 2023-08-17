from weakref import finalize

import requests
from pyrate_limiter import Duration, Limiter, RequestRate
from requests import Response
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from EdgarAPIError import EdgarAPIError
from _constants import BACKOFF_FACTOR, MAX_REQUESTS_PER_SECOND, MAX_RETRIES, HOST_DATA_SEC, STANDARD_HEADERS
from logger import setup_logger

logger = setup_logger(__name__)

# Rate limiter
rate = RequestRate(MAX_REQUESTS_PER_SECOND, Duration.SECOND)
limiter = Limiter(rate)

# Specify max number of request retries
# https://stackoverflow.com/a/35504626/3820660
retries = Retry(
    total=MAX_RETRIES,
    backoff_factor=BACKOFF_FACTOR,
    status_forcelist=[403, 500, 502, 503, 504],
)


class BaseClient:
    def __init__(self, user_agent: str):

        self._session = requests.Session()
        self._session.headers.update(
            {
                **STANDARD_HEADERS,
                "User-Agent": user_agent,
                "Host": HOST_DATA_SEC,
            }
        )
        logger.debug(f'{self._session.headers = }')

        self._session.mount("http://", HTTPAdapter(max_retries=retries))
        self._session.mount("https://", HTTPAdapter(max_retries=retries))

        # Close the session when this object is garbage collected
        # or the program exits.
        # Source: https://stackoverflow.com/a/67312839/3820660
        finalize(self, self._session.close)

    # @limiter.ratelimit("sec_global_rate_limit",delay=True)
    @limiter.ratelimit(delay=True)
    def _rate_limited_get(self, url: str, headers: dict = None, host=None) -> Response:
        """Make a rate-limited GET request.

        SEC limits users to a maximum of 10 requests per second.
        Source: https://www.sec.gov/developer
        """
        # Merge session headers with provided headers, if any
        session_headers_copy = self._session.headers.copy()
        if headers is not None:
            session_headers_copy.update(headers)
        elif host is not None:
            session_headers_copy.update({"Host": host})

        resp = self._session.get(url, headers=session_headers_copy)
        try:
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise EdgarAPIError(
                exception=e,
                status_code=resp.status_code,
                url=resp.url,
            )
        return resp
