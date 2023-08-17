"""Unofficial SEC EDGAR API wrapper."""
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Optional, Union, List

import feedparser
import numpy as np
import pandas as pd
import requests

from Modules.EDGAR.client._DownloadFormManager import DownloadFormManager
from _BaseClient import BaseClient
from _constants import (
    SUPPORTED_FORMS, DEFAULT_AFTER_DATE, DEFAULT_BEFORE_DATE,
    ROOT_FACTS_SAVE_FOLDER_NAME, ROOT_FORMS_SAVE_FOLDER_NAME,
    HOST_WWW_SEC, STANDARD_HEADERS, URL_XBRL_COMPANY_CONCEPTS, URL_XBRL_FRAMES, URL_XBRL_COMPANY_FACTS, URL_SUBMISSIONS,
    URL_PAGINATED_SUBMISSIONS, URL_XBRL_COMPANY_SUBMISSIONS_ZIP, URL_XBRL_COMPANY_FACTS_ZIP
)
from _types import FormsDownloadMetadata, DownloadPath, JSONType
from _utils import merge_submission_dicts, validate_and_return_cik, validate_and_parse_date, get_valid_after_date
from logger import setup_logger

logger = setup_logger(name="EdgarClient")


class EdgarClient(BaseClient, DownloadFormManager):
    """An :class:`EdgarClient` object.

    Header Defaults to the following:
        {
            **STANDARD_HEADERS, # {"Accept-Encoding": "gzip, deflate", }
            "User-Agent": user_agent, # "<Sample Company Name> <Sample Company Email>"
            "Host": HOST_DATA_SEC, # "data.sec.gov"
        }

    """

    def __init__(
            self,
            company_name: str,
            email_address: str,
            download_folder: Optional[DownloadPath] = None,
    ):
        """
        Constructs an Edgar-Client object with user-agent and download folder.

        Args:
            company_name (str): The company name to use in the user-agent string.
            email_address (str): The email address to use in the user-agent string.
            download_folder (Optional[DownloadPath], default=None): The folder to download files to. If not specified, the current directory is used.
        """

        # TODO: add validation for email
        self.user_agent = f"{company_name} {email_address}"
        if not self.user_agent:  # todo - check company, email etc... are valid
            raise ValueError(
                "Please enter a valid user-agent string of the form "
                "'<Sample Company Name> <Sample Company Email>'. "
                "This is required by the SEC to identify your requests "
                "for rate-limiting purposes."
            )
        super().__init__(self.user_agent)

        if download_folder is None:
            self.parent_download_folder = Path.cwd()
        elif isinstance(download_folder, Path):
            self.parent_download_folder = download_folder
        else:
            self.parent_download_folder = Path(download_folder).expanduser().resolve()

        self.supported_forms = SUPPORTED_FORMS
        self.facts_save_folder = self.parent_download_folder / ROOT_FACTS_SAVE_FOLDER_NAME
        self.forms_save_folder = self.parent_download_folder / ROOT_FORMS_SAVE_FOLDER_NAME
        self.ticker_to_cik_mapping, self.cik_to_ticker_mapping, self.cik_to_name = \
            self.get_ticker_cik_name_mapping()

    def get_submissions_by_company(self, ticker_or_cik: str, *, handle_pagination: bool = True) -> JSONType:
        """Get submissions for a specified CIK. Requests data from the
        data.sec.gov/submissions API endpoint. Full API documentation:
        https://www.sec.gov/edgar/sec-api-documentation.

        :param cik: CIK to obtain submissions for.
        :param handle_pagination: whether to automatically handle API pagination,
            defaults to True. By default, 1000 submissions are included and the
            response specified the next set of filenames to request to get the next
            batch of submissions (each page contains 1000 submissions). If this is
            set to True, requests to the paginated resources will be completed
            automatically and the results will be concatenated to the recent filings key.
            If a raw response is preferred for manual pagination handling, set this
            value to false.
        :return: JSON response from the data.sec.gov/submissions/ API endpoint
            for the specified CIK.
        """
        cik = validate_and_return_cik(ticker_or_cik, self.ticker_to_cik_mapping)
        submissions_uri = URL_SUBMISSIONS.format(cik=cik)
        submissions = self._rate_limited_get(submissions_uri).json()
        filings = submissions["filings"]
        paginated_submissions = filings["files"]

        # Handle pagination for a large number of requests
        if handle_pagination and paginated_submissions:
            to_merge = [filings["recent"]]
            for submission in paginated_submissions:
                filename = submission["name"]
                api_endpoint = URL_PAGINATED_SUBMISSIONS.format(paginated_file_name=filename)
                resp = self._rate_limited_get(api_endpoint).json()
                to_merge.append(resp)

            # Merge all paginated submissions from files key into recent
            # and clear files list.
            filings["recent"] = merge_submission_dicts(to_merge)
            filings["files"] = []

        return submissions

    def get_concept_by_company(
            self,
            ticker_or_cik: str,
            taxonomy: str,
            tag: str,
    ) -> JSONType:
        """Get company concepts for a specified CIK. Requests data from the
        data.sec.gov/api/xbrl/companyconcept/ API endpoint. Returns all
        the XBRL disclosures for a single company (CIK) and concept (taxonomy and
        tag), with a separate array of facts for each unit of measure that the
        company has chosen to disclose (e.g. net profits reported in U.S. dollars
        and in Canadian dollars). Full API documentation:
        https://www.sec.gov/edgar/sec-api-documentation.

        :param cik: CIK to obtain company concepts for.
        :param taxonomy: reporting taxonomy (e.g. us-gaap, ifrs-full, dei, srt).
            More info: https://www.sec.gov/info/edgar/edgartaxonomies.shtml.
        :param tag: reporting tag (e.g. AccountsPayableCurrent).
        :return: JSON response from the data.sec.gov/api/xbrl/companyconcept/
            API endpoint for the specified CIK.
        """
        return self._rate_limited_get(URL_XBRL_COMPANY_CONCEPTS.format(
            cik=validate_and_return_cik(ticker_or_cik, self.ticker_to_cik_mapping),
            taxonomy=taxonomy,
            tag=tag,
        )).json()

    def get_facts_by_company(self, ticker_or_cik: str) -> JSONType:
        """Get all company concepts for a specified CIK. Requests data from the
        data.sec.gov/api/xbrl/companyfacts/ API endpoint. Full API documentation:
        https://www.sec.gov/edgar/sec-api-documentation.

        :param cik: CIK to obtain company concepts for.
        :return: JSON response from the data.sec.gov/api/xbrl/companyfacts/
            API endpoint for the specified CIK.
        """
        return self._rate_limited_get(URL_XBRL_COMPANY_FACTS.format(
            cik=validate_and_return_cik(ticker_or_cik, self.ticker_to_cik_mapping),
        )).json()

    def get_frames(
            self,
            taxonomy: str,
            tag: str,
            unit: str,
            year: str,
            quarter: Union[int, str, None] = None,
            instantaneous: bool = True,
    ) -> JSONType:
        """Get all aggregated company facts for a specified taxonomy and tag in the specified
        calendar period. Requests data from the data.sec.gov/api/xbrl/frames/ API endpoint.
        Supports for annual, quarterly and instantaneous data. Example:
        us-gaap / AccountsPayableCurrent / USD / CY2019Q1I.
        Full API documentation: https://www.sec.gov/edgar/sec-api-documentation.

        :param taxonomy: reporting taxonomy (e.g. us-gaap, ifrs-full, dei, srt).
            More info: https://www.sec.gov/info/edgar/edgartaxonomies.shtml.
        :param tag: reporting tag (e.g. AccountsPayableCurrent).
        :param unit: unit of measure specified in the XBRL (e.g. USD).
        :param year: calendar period year.
        :param quarter: calendar period quarter, optional. Defaults to whole year.
        :param instantaneous: whether to request instantaneous data, defaults to True.
        :return: JSON response from the data.sec.gov/api/xbrl/frames/ API endpoint.
        """
        _quarter = (
            f"Q{quarter}" if quarter is not None and 1 <= int(quarter) <= 4 else ""
        )
        _instantaneous = "I" if instantaneous else ""
        period = f"CY{year}{_quarter}{_instantaneous}"
        return self._rate_limited_get(URL_XBRL_FRAMES.format(
            taxonomy=taxonomy,
            tag=tag,
            unit=unit,
            period=period,
        )).json()

    def download_forms_by_company(  # change to plural to reflect the fact we're dealing with multiple forms
            self,
            ticker_or_cik: str,
            form_types: List[str],  # change to a list of forms
            *,
            limit: Optional[int] = None,
            after: Optional[str] = None,
            before: Optional[str] = None,
            include_amends: bool = False,
            download_details: bool = True,
    ) -> int:
        """
        Fetches and saves SEC filings.

        Args:
            form_types (List[str]): The form types to download.
            ticker_or_cik (str): The ticker or CIK to download filings for.
            limit (Optional[int], default=None): The maximum number of filings to download. If not specified, all available filings are downloaded.
            after (Optional[str], default=None): The earliest date for filings. If not specified, downloads filings available since 1994.
            before (Optional[str], default=None): The latest date for filings. If not specified, downloads filings up to today's date.
            include_amends (bool, default=False): Whether to include amended filings.
            download_details (bool, default=True): Whether to download filing details.

        Returns:
            int: The number of downloaded filings.

        Raises:
            ValueError: If a form is not supported, the limit is less than 1, or the after date is later than the before date.
        """
        # TODO: add validation and defaulting
        # TODO: can we rely on class default values rather than manually checking None?
        cik = validate_and_return_cik(ticker_or_cik, self.ticker_to_cik_mapping)
        ticker = self.cik_to_ticker_mapping.get(cik, None)

        limit = sys.maxsize if limit is None else int(limit)
        if limit < 1: raise ValueError("Invalid limit. Please enter a number greater than 1.")

        after_date = get_valid_after_date(after, after_date=DEFAULT_AFTER_DATE)
        before_date = DEFAULT_BEFORE_DATE if before is None else validate_and_parse_date(before)

        if after_date > before_date: raise ValueError("After date cannot be greater than the before date.")

        unsupported_forms = [form for form in form_types if form not in SUPPORTED_FORMS]
        if unsupported_forms:
            form_options = ", ".join(SUPPORTED_FORMS)
            raise ValueError(
                f"The following forms aren't supported: {', '.join(unsupported_forms)}. Please choose from the following: {form_options}.")

        num_downloaded = self.fetch_and_save_filings(
            FormsDownloadMetadata(
                self.parent_download_folder,
                form_types,  # pass the list of forms
                cik,
                ticker,
                limit,
                after_date,
                before_date,
                include_amends,
                download_details,
            ))

        return num_downloaded

    def download_facts_for_companies(self, tickers_or_ciks: List[str], skip_if_exists=True):
        # todo can do this by downloading zip file and extracting them rather than looping through to download
        ticker_facts_saved = []
        ticker_facts_skipped = []

        self.facts_save_folder.mkdir(parents=True, exist_ok=True)

        for ticker_or_cik in tickers_or_ciks:
            try:
                cik = validate_and_return_cik(ticker_or_cik, self.ticker_to_cik_mapping)
                ticker_name = self.cik_to_ticker_mapping.get(cik)
                save_json_path = f'{self.facts_save_folder}/{ticker_name}-facts-{datetime.now().strftime("%Y-%m-%d")}.json'
            except Exception as e:
                logger.error(f"Skipping {ticker_or_cik} because of error: {e}")
                ticker_facts_skipped.append(ticker_or_cik)
                continue
            if skip_if_exists and os.path.exists(save_json_path):
                logger.info(f"Skipping {ticker_name} because it already exists")
                continue
            try:
                values = self.get_facts_by_company(ticker_name)
            except Exception as e:
                logger.error(f"Skipping {ticker_name}  while downloading facts because of error: {e}")
                ticker_facts_skipped.append(ticker_name)
                continue
            try:
                with open(save_json_path, 'w') as outfile:
                    json.dump(values, outfile)
                logger.info(f"Saved {ticker_name} facts")
                ticker_facts_saved.append(ticker_name)
            except Exception as e:
                logger.error(f"Skipping {ticker_name}  while saving facts because of error: {e}")
                ticker_facts_skipped.append(ticker_name)
                continue
        return ticker_facts_saved, ticker_facts_skipped

    def download_forms_for_companies(self,
                                     tickers_or_ciks: List[str], form_types: List[str],
                                     *,
                                     limit_per_form: Optional[int] = None,
                                     after: Optional[str] = None,
                                     before: Optional[str] = None,
                                     include_amends: bool = False,
                                     download_details: bool = True,
                                     ):

        forms_saved = []
        forms_skipped = []
        for ticker_or_cik in tickers_or_ciks:
            try:
                cik = validate_and_return_cik(ticker_or_cik, self.ticker_to_cik_mapping)
                ticker_name = self.cik_to_ticker_mapping.get(cik)
                logger.info(f"Downloading forms for {ticker_name}")
            except Exception as e:
                logger.error(f"Skipping {ticker_or_cik} because it is not in the ticker to cik mapping: {e}")
                continue

            unsupported_forms = [form for form in form_types if form not in self.supported_forms]
            if unsupported_forms:
                logger.info(
                    f"Skipping forms {', '.join(unsupported_forms)} for equity {ticker_name} because they are not supported")
                continue
            try:
                n_saved_filings = self.download_forms(ticker_name, form_types,  # pass the list of forms
                                                      after=after, before=before,
                                                      limit=limit_per_form, include_amends=include_amends,
                                                      download_details=download_details
                                                      )
                logger.info(f"Saved {n_saved_filings} filings for {ticker_name}-{', '.join(form_types)}")
                forms_saved.extend([f'{ticker_name}-{form_type}' for form_type in form_types])
            except Exception as e:
                logger.error(
                    f"Skipping forms {', '.join(form_types)} for ticker {ticker_name} during download because of error: {e}")
                forms_skipped.extend([f'{ticker_name}-{form_type}' for form_type in form_types])
                continue
        return forms_saved, forms_skipped

    def subscribe_to_rss_feed(self, interval, callback_func=None):
        # todo if only_pass_entries_by_id is true the starting default value per id should also look back in the saved for the same id
        # todo allow to subscribe to specific form types or companies

        sec_rss_feed_url = f"https://{HOST_WWW_SEC}/cgi-bin/browse-edgar?action=getcurrent&type=&company=&dateb=&owner=include&start=0&output=atom&count=100"

        if callback_func is None:
            def _default_process_entry(entry):
                # Do something with the entry
                logger.info("Processing new entry:")
                for field, value in entry.items():
                    logger.info(f"{field}: {value}")
                logger.info("-------------")

            callback_func = _default_process_entry
        last_entry = None
        while True:
            try:

                # fixme this is essensially the same as in baseclient except the host
                response = requests.get(sec_rss_feed_url, headers={
                    "User-Agent": self.user_agent,
                    "Host": HOST_WWW_SEC,
                    **STANDARD_HEADERS,
                })
                feed = feedparser.parse(response.content)
                # fixme ^^^^

                if not feed.entries:
                    logger.warning("No entries found in the RSS feed.")
                    time.sleep(interval)
                    continue
                new_entries = []
                for entry in feed.entries:
                    if last_entry is not None and entry.id == last_entry.id: break
                    new_entries.append(entry)
                if new_entries:
                    last_entry = new_entries[0]
                    for entry in new_entries:
                        callback_func(entry)
            except Exception as e:
                logger.error("Error:", e)
            finally:
                time.sleep(interval)

    def subscribe_rss_feeds(self, feed_urls, callback_func=None, interval=10):
        # todo more control over the rss endpoint filter
        if callback_func is None:
            def _default_process_entry(entry):
                logger.info("Processing new entry:")
                for field, value in entry.items():
                    logger.info(f"{field}: {value}")
                logger.info("-------------")

            callback_func = _default_process_entry

        last_entries = {url: None for url in feed_urls}  # Store last entry for each feed

        while True:
            for url in feed_urls:
                try:
                    response = requests.get(url, headers={
                        "User-Agent": self.user_agent,
                        "Host": HOST_WWW_SEC,
                        **STANDARD_HEADERS,
                    })
                    feed = feedparser.parse(response.content)

                    if not feed.entries:
                        logger.warning(f"No entries found in the RSS feed: {url}")
                        continue

                    new_entries = []
                    for entry in feed.entries:
                        if last_entries[url] is not None and entry.id == last_entries[url].id:
                            break
                        new_entries.append(entry)
                    if new_entries:
                        last_entries[url] = new_entries[0]  # Update the last entry
                        for entry in new_entries:
                            callback_func(entry)

                except Exception as e:
                    logger.error("Error:", e)
            time.sleep(interval)

    def download_facts_of_all_companies_zip(self) -> str:
        """Download all company concepts for a specified CIK. Requests data from the
        data.sec.gov/archives/edgar/daily-index/xbrl/ API endpoint. Full API documentation:
        https://www.sec.gov/edgar/sec-api-documentation.

        :param ticker_or_cik: Ticker or CIK to obtain company concepts for.
        :param save_path: The path to save the downloaded zip file.
        :return: The path of the downloaded zip file.
        """
        response = self._rate_limited_get(URL_XBRL_COMPANY_FACTS_ZIP, host=HOST_WWW_SEC)
        self.facts_save_folder.mkdir(parents=True, exist_ok=True)
        file_path = os.path.join(self.facts_save_folder,
                                 f'all_companies_facts-{datetime.now().strftime("%Y-%m-%d")}.zip')

        with open(file_path, 'wb') as f:
            f.write(response.content)

        return file_path

    def download_submissions_of_all_companies_zip(self) -> str:
        """Download all company concepts for a specified CIK. Requests data from the
        data.sec.gov/archives/edgar/daily-index/xbrl/ API endpoint. Full API documentation:
        https://www.sec.gov/edgar/sec-api-documentation.

        :param ticker_or_cik: Ticker or CIK to obtain company concepts for.
        :param save_path: The path to save the downloaded zip file.
        :return: The path of the downloaded zip file.
        """
        response = self._rate_limited_get(URL_XBRL_COMPANY_SUBMISSIONS_ZIP, host=HOST_WWW_SEC)
        self.facts_save_folder.mkdir(parents=True, exist_ok=True)

        file_path = os.path.join(self.facts_save_folder,
                                 f'all_companies_submissions-{datetime.now().strftime("%Y-%m-%d")}.zip')

        with open(file_path, 'wb') as f:
            f.write(response.content)

        return file_path

    @staticmethod
    def _parse_open_json(args):
        filename, file_path_to_latest_zip, ticker_to_cik_mapping, cik_to_ticker_mapping, facts_save_folder = args
        dataframes = []

        with zipfile.ZipFile(file_path_to_latest_zip, 'r') as z:
            with z.open(filename) as f:
                try:
                    data = json.load(f)
                    cik = validate_and_return_cik(data['cik'], ticker_to_cik_mapping)
                    ticker = cik_to_ticker_mapping[cik]
                    date = re.search(r'\d{4}-\d{2}-\d{2}', file_path_to_latest_zip.name).group(0)
                    output_file_path = f'{facts_save_folder}/{ticker}_facts-{date}.pkl'
                    if os.path.exists(output_file_path):
                        logger.info(f'File already exists: {output_file_path}')
                        return
                    logger.info(f'Parsing {data["entityName"]} facts')
                    taxonomies = data['facts']

                    for taxonomy_name in taxonomies.keys():
                        logger.info(f'    Taxonomy {taxonomy_name}')
                        for tag_name in taxonomies[taxonomy_name].keys():
                            units = taxonomies[taxonomy_name][tag_name]["units"].keys()
                            logger.info(f'      Tag {tag_name}')
                            for unit in units:
                                # Create a DataFrame from the data list
                                events_df = pd.DataFrame(taxonomies[taxonomy_name][tag_name]["units"][unit])
                                logger.info(f'            Keys -> {list(events_df.keys())}')
                                # Add multi-index before concatenating to the main DataFrame
                                events_df.columns = pd.MultiIndex.from_product(
                                    [[taxonomy_name], [unit], [tag_name], events_df.columns])
                                # Append the data to the dataframes list
                                dataframes.append(events_df)

                    # Concatenate all dataframes together
                    multi_df = pd.concat(dataframes, axis=1)
                    multi_df.to_pickle(output_file_path)
                except Exception as e:
                    logger.error(f'Error parsing {filename}: {e}')
                    return

    @property
    def get_path_to_latest_facts_zip(self):
        return max(self.facts_save_folder.glob('*.zip'), key=os.path.getctime)

    def parse_all_facts_in_latest_zip(self, number_of_cores=cpu_count() - 6):
        """Parse all facts from the downloaded zip file and store them in a database."""
        file_path_to_latest_zip = self.get_path_to_latest_facts_zip
        with zipfile.ZipFile(file_path_to_latest_zip, 'r') as z:
            json_files = [(filename, file_path_to_latest_zip, self.ticker_to_cik_mapping, self.cik_to_ticker_mapping,
                           self.facts_save_folder) for filename in z.namelist() if filename.endswith('.json')]
            with Pool(number_of_cores) as p:
                p.map(self._parse_open_json, json_files)

    def parse_facts_json(self, json_dict):
        dataframes = []

        logger.info(f'Parsing {json_dict["entityName"]} facts')
        taxonomies = json_dict['facts']
        ALLOWED_DATA_COLUMNS = ['start', 'end', 'val', 'accn', 'fy', 'fp', 'form', 'filed', 'frame']
        for taxonomy_name in taxonomies.keys():
            for tag_name in taxonomies[taxonomy_name].keys():
                units = taxonomies[taxonomy_name][tag_name]["units"].keys()

                for unit in units:
                    # Create a DataFrame from the data list
                    events_df = pd.DataFrame(taxonomies[taxonomy_name][tag_name]["units"][unit])
                    # events_df = events_df.dropna(axis=1, how='all')
                    if not set(ALLOWED_DATA_COLUMNS).issubset(set(events_df.columns)):
                        # Which columns are missing?
                        missing_columns = set(ALLOWED_DATA_COLUMNS) - set(events_df.columns)

                        # Make sure missing columns are only start and frame nothing else, else raise critical error
                        # . missing_columns can be {'start'} or {'frame'} or {'start', 'frame'} or set()
                        if not missing_columns.issubset({'start', 'frame'}):
                            logger.critical(f'Columns {missing_columns} are missing from {tag_name}')
                            exit()
                        # Add the missing columns as missing nan columns
                        for missing_column in missing_columns:
                            events_df[missing_column] = np.nan

                    # Add multi-index before concatenating to the main DataFrame
                    events_df.columns = pd.MultiIndex.from_product(
                        [[taxonomy_name], [tag_name], [unit], events_df.columns])

                    # Append the data to the dataframes list
                    dataframes.append(events_df)

        # Concatenate all dataframes together
        multi_df = pd.concat(dataframes, axis=1)
        return multi_df.sort_index()

    def query_fact_from_zip(self, ticker_or_cik: str,
                            # tag: str = None, dates: List[str] = None,
                            return_raw_json=False):

        # Validate the ticker or CIK to CIK
        cik = validate_and_return_cik(ticker_or_cik, self.ticker_to_cik_mapping)
        ticker_name = self.cik_to_ticker_mapping.get(cik)

        # Construct the filename of the json file
        filename = f'CIK{cik}.json'

        # Get the path to the latest zip file downloaded
        file_path_to_latest_zip = self.get_path_to_latest_facts_zip
        updated_date = re.search(r'\d{4}-\d{2}-\d{2}', file_path_to_latest_zip.name).group(0)
        logger.info(f'Latest zip file found: {file_path_to_latest_zip.name} with updated date {updated_date}')

        # Go inside the zip file
        with zipfile.ZipFile(file_path_to_latest_zip, 'r') as z:
            # Checking if the file exists in the zip file
            if filename not in z.namelist():
                logger.error(f'File {filename} not found in the zip file')
                return

            # Get the list of files in the zip file
            with z.open(filename) as f:
                json_dict = json.load(f)
                if return_raw_json:
                    return json_dict
                multiindex_df = self.parse_facts_json(json_dict)


            print(multiindex_df[('us-gaap', 'NetIncomeLoss', 'USD')])

            exit()

            # TODO Lets query the data
            # logger.info(f'Querying {ticker_name} facts in {filename}')

            return multiindex_df


if __name__ == "__main__":
    DOWNLOAD_FOLDER = "/home/ruben/PycharmProjects/Genie-Trader/Data/raw_data/SEC"

    # Create an EdgarClient instance
    edgar_client = EdgarClient(company_name="Carbonyl LLC", email_address="ruben@carbonyl.org",
                               download_folder=DOWNLOAD_FOLDER)
    # edgar_client.download_facts_of_all_companies_zip()
    # edgar_client.parse_all_facts_in_latest_zip()
    df = edgar_client.query_fact_from_zip(ticker_or_cik="AAPL",
                                          return_raw_json=False
                                          )
    pd.set_option('display.max_columns', None)
    print(df["us-gaap"]["AccountsPayable"])
    exit()
    # Provide the list of feed urls
    feed_urls = [
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=&company=&dateb=&owner=include&start=0&output=atom&count=100"
        "https://www.sec.gov/rss/litigation/litreleases.xml",
        "https://www.sec.gov/rss/litigation/admin.xml",
        "http://www.sec.gov/rss/litigation/suspensions.xml",
        "https://www.sec.gov/rss/divisions/corpfin/cfnew.xml",
        "http://www.sec.gov/rss/divisions/investment/imnews.xml",
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent",
        # ... other feed urls
    ]
    edgar_client.subscribe_rss_feeds(feed_urls=feed_urls, callback_func=None, interval=2)

    # # Subscribe to the RSS feed
    # edgar_client.subscribe_to_rss_feed(interval=2)
