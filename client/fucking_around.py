
edgar_client.download_forms_by_company(
        ticker_or_cik='AAPL',  # str - ticker or CIK
        # form_types=['10-K', '10-Q', '8-K', '4', 'SC 13G'],  # List[str] - list of forms
        form_types=['10-K'],  # List[str] - list of forms
        limit=None,  # Optional[int] - limit the number of forms to download (default: sys.maxsize)
        after=None,  # Optional[str] - only download forms after this date (default: date(1994, 1, 1))
        before=None,  # Optional[str] - only download forms before this date (default: date.today())
        include_amends=False,  # bool - include amended forms (default: False)
        download_details=False,  # bool - download the form details e.g. html (default: True)
    )



# edgar_client.download_form(ticker_or_cik='AAPL', form_type='10-K')
# edgar_client.get_company_facts(ticker_or_cik='AAPL')
# edgar_client.get_company_concept(ticker_or_cik='AAPL', taxonomy='us-gaap', tag='AccountsPayableCurrent', )

# rss_feed_url = f"https://{HOST_WWW_SEC}/cgi-bin/browse-edgar?action=getcurrent&type=&company=&dateb=&owner=include&start=0&output=atom&count=100"
# edgar_client.subscribe_to_rss_feed(url=rss_feed_url, interval=5, callback_func=None)
exit()


import json
import zipfile

with zipfile.ZipFile('path_to_your_zipfile.zip', 'r') as z:
    for filename in z.namelist():
        if filename.endswith('.json'):
            with z.open(filename) as f:
                data = json.load(f)
                # Process the JSON data

exit()
TICKERS_TO_ANALYZE = ['AAPL']

# get tickers from directory and filenames {ticker}-facts.json
tickers = TICKERS_TO_ANALYZE or [f.replace('-facts.json', '') for f in
                                 os.listdir(f'{DOWNLOAD_FOLDER}/sec-edgar-facts') if
                                 f.endswith('-facts.json')]

# Initialize an empty DataFrame
multi_df = pd.DataFrame()

for ticker in tickers:
    with open(f'{DOWNLOAD_FOLDER}/sec-edgar-facts/{ticker}-facts.json') as f:
        company_facts = json.load(f)

    logger(f'Parsing {company_facts["entityName"]} facts')
    taxonomies = company_facts['facts']

    for taxonomy_name in taxonomies.keys():
        logger(f'    Taxonomy {taxonomy_name}')
        for tag_name in taxonomies[taxonomy_name].keys():
            units = taxonomies[taxonomy_name][tag_name]["units"].keys()

            logger(f'      Tag {tag_name}')
            # logger(f'        Label: {taxonomies[taxonomy_name][tag_name]["label"]}')
            # logger(f'        Description: {taxonomies[taxonomy_name][tag_name]["description"]}')
            # logger(f'        Units: {list(units)}')

            for unit in units:
                # Create a DataFrame from the data list
                events_df = pd.DataFrame(taxonomies[taxonomy_name][tag_name]["units"][unit])

                logger(f'            Keys -> {list(events_df.keys())}')

                # Add multi-index before concatenating to the main DataFrame
                events_df.columns = pd.MultiIndex.from_product(
                    [[taxonomy_name], [tag_name], [unit], events_df.columns])

                # Concatenate the data to the main DataFrame
                multi_df = pd.concat([multi_df, events_df], axis=1)

logger(multi_df.head())
