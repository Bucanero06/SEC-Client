from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from Modules.EDGAR.client._BaseClient import BaseClient
from Modules.EDGAR.client.logger import setup_logger
from _constants import (
    AMENDS_SUFFIX,
    CIK_LENGTH,
    PRIMARY_DOC_FILENAME_STEM,
    ROOT_FORMS_SAVE_FOLDER_NAME,
    URL_FILING,
    URL_SUBMISSIONS, FORM_FULL_SUBMISSION_FILENAME, HOST_WWW_SEC, URL_CIK_MAPPING,
    URL_PAGINATED_SUBMISSIONS,
)
from _types import FormsDownloadMetadata, FormToDownload
from _utils import within_requested_date_range

logger = setup_logger(__name__)


def get_forms_save_location(download_metadata: FormsDownloadMetadata,
                            form: str,
                            accession_number: str,
                            save_filename: str,
                            ) -> Path:
    return (
            download_metadata.download_folder
            / ROOT_FORMS_SAVE_FOLDER_NAME
            / f'{download_metadata.ticker}-{download_metadata.cik}'
            / form
            / accession_number
            / save_filename
    )


def save_form_document(filing_contents: Any,
                       download_metadata: FormsDownloadMetadata,
                       form_meta_data: FormToDownload,
                       save_filename: str,
                       ) -> None:
    # Create all parent directories as needed and write content to file
    save_path = get_forms_save_location(download_metadata, form_meta_data.form, form_meta_data.accession_number,
                                        save_filename)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    # TODO: resolve URLs so that images show up in HTML files?
    save_path.write_bytes(filing_contents)


def get_to_download(cik: str, acc_num: str, form: str, doc: str) -> FormToDownload:
    cik = cik.strip("0")
    acc_num_no_dash = acc_num.replace("-", "")
    raw_filing_uri = URL_FILING.format(cik=cik, acc_num_no_dash=acc_num_no_dash, document=f"{acc_num}.txt")
    primary_doc_uri = URL_FILING.format(cik=cik, acc_num_no_dash=acc_num_no_dash, document=doc)
    primary_doc_suffix = Path(doc).suffix.replace("htm", "html")
    return FormToDownload(form, raw_filing_uri, primary_doc_uri, acc_num, primary_doc_suffix)


class DownloadFormManager(BaseClient):
    def __init__(self, user_agent: str):
        super().__init__(user_agent)
        self.user_agent = user_agent

    def aggregate_forms_to_download(self,
                                    download_metadata: FormsDownloadMetadata
                                    ) -> List[FormToDownload]:
        filings_to_download: List[FormToDownload] = []
        fetched_count = 0
        filings_available = True
        submissions_uri = URL_SUBMISSIONS.format(cik=download_metadata.cik)
        additional_submissions = None

        while fetched_count < download_metadata.limit and filings_available:
            resp_json = self._rate_limited_get(submissions_uri).json()
            # First API response is different from further API responses
            if additional_submissions is None:
                filings_json = resp_json["filings"]["recent"]
                additional_submissions = deque(resp_json["filings"]["files"])
            # On second page or more of API response (for companies with >1000 filings)
            else:
                filings_json = resp_json
            accession_numbers = filings_json["accessionNumber"]
            forms = filings_json["form"]

            documents = filings_json["primaryDocument"]
            filing_dates = filings_json["filingDate"]

            for acc_num, form, doc, f_date in zip(accession_numbers, forms, documents, filing_dates, strict=True):
                if (form not in download_metadata.forms or  # Change this to `not in`
                        (not download_metadata.include_amends and form.endswith(AMENDS_SUFFIX)) or
                        not within_requested_date_range(download_metadata, f_date)):
                    continue
                filings_to_download.append(get_to_download(download_metadata.cik, acc_num, form, doc))

                fetched_count += 1
                # We have reached the requested download limit, so exit early
                if fetched_count == download_metadata.limit: return filings_to_download

            if len(additional_submissions) == 0: break
            next_page = additional_submissions.popleft()["name"]
            submissions_uri = URL_PAGINATED_SUBMISSIONS.format(paginated_file_name=next_page)
        return filings_to_download

    def fetch_and_save_filings(self, download_metadata: FormsDownloadMetadata) -> int:
        # TODO: do not download files that already exist
        # TODO: add try/except around failed downloads and continue
        # todo i can probably split this into fetching raw data and/or html to serve for example and the actual writing to file in case we do not want to save
        successfully_downloaded = 0
        to_download = self.aggregate_forms_to_download(download_metadata)
        for td in to_download:
            logger.info(f"Downloading {td.form} for {download_metadata.ticker} on {td.accession_number}")
            raw_filing = self._rate_limited_get(td.raw_filing_uri, host=HOST_WWW_SEC).content
            save_form_document(raw_filing, download_metadata, td, FORM_FULL_SUBMISSION_FILENAME)
            if download_metadata.download_details:
                primary_doc = self._rate_limited_get(td.primary_doc_uri, host=HOST_WWW_SEC).content
                primary_doc_filename = f"{PRIMARY_DOC_FILENAME_STEM}{td.details_doc_suffix}"
                save_form_document(primary_doc, download_metadata, td, primary_doc_filename)
            successfully_downloaded += 1
        return successfully_downloaded

    def get_ticker_cik_name_mapping(self) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
        """Get the mapping from ticker to CIK and CIK to ticker."""
        ticker_metadata = self._rate_limited_get(URL_CIK_MAPPING, host=HOST_WWW_SEC).json()

        fields = ticker_metadata["fields"]
        ticker_data = ticker_metadata["data"]

        # Find index that corresponds with the CIK and ticker fields
        cik_idx, ticker_idx, name_idx = fields.index("cik"), fields.index("ticker"), fields.index("name")

        ticker_to_cik = {str(td[ticker_idx]).upper(): str(td[cik_idx]).zfill(CIK_LENGTH) for td in ticker_data}
        cik_to_ticker = {cik: ticker for ticker, cik in ticker_to_cik.items()}
        cik_to_name = {cik: name for name, cik in ticker_to_cik.items()}

        return ticker_to_cik, cik_to_ticker, cik_to_name

    def get_ticker_dataframe(self) -> pd.DataFrame:
        """Get the ticker metadata as a pandas DataFrame."""
        ticker_metadata = self._rate_limited_get(URL_CIK_MAPPING, host=HOST_WWW_SEC).json()
        fields = ticker_metadata["fields"]  # ['cik', 'name', 'ticker', 'exchange']
        ticker_data = ticker_metadata["data"]

        # Convert raw data into DataFrame
        df = pd.DataFrame(ticker_data, columns=fields)

        # Ensure data types
        df['cik'] = df['cik'].astype(str).str.zfill(CIK_LENGTH)
        df['ticker'] = df['ticker'].str.upper()

        return df
