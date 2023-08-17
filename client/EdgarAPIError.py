class EdgarAPIError(Exception):
    """SEC EDGAR API error."""

    def __init__(self, exception, status_code=None, url=None):
        self.status_code = status_code
        self.url = url
        message = f"An error occurred with the SEC EDGAR API: {exception}"
        super().__init__(f'{message}. URL: {url}. Status code: {status_code}')
