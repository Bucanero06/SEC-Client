# EdgarClient 
(TESTS ARE OUT OF DATE AND WILL BE UPDATED SOON, REFACTORING MERGER)

**EdgarClient** provides a lightweight, unofficial Python API wrapper for
the [SEC EDGAR REST API](https://www.sec.gov/edgar/sec-api-documentation).

It also provides a method for downloading [company filings](https://en.wikipedia.org/wiki/SEC_filing) from
the [SEC EDGAR database](https://www.sec.gov/edgar/searchedgar/companysearch.html). Searches can be conducted either
by [stock ticker](https://en.wikipedia.org/wiki/Ticker_symbol)
or [Central Index Key (CIK)](https://en.wikipedia.org/wiki/Central_Index_Key). You can use
the [SEC CIK lookup tool](https://www.sec.gov/edgar/searchedgar/cik.htm) if you cannot find an appropriate ticker.

## Features

- Full support for [all SEC EDGAR REST API endpoints](#wrapper-functions-and-corresponding-api-endpoints)
- Automatic pagination handling for filing submissions data
- Automatic rate-limiting to 10 requests per second to conform
  with [SEC fair access rules](https://www.sec.gov/developer)
- Advanced downloading get method with retry handling and directory creation
- Full support for PEP 484-style type hints and the [mypy type checker](https://mypy.readthedocs.io/en/stable/)
- Support for Python 3.6+

## Quick Start

(**DETAILS ARE ABOUT TO CHANGE DUE TO REFACTORING to accommodate optional
download_facts_for_companies & download_forms_for_companies methods
**)

### Lightweight Methods Usage

```python
# Specify user-agent string to pass to SEC to identify
# requests for rate-limiting purposes
>> > edgar_client = EdgarClient(company_name="<Sample Company Name>",
                                email_address="<Admin Contact>@<Sample Company Domain>",
                                download_folder=None,  # Defaults to current working directory
                                )

# Get submissions for Apple with the additional paginated files
# appended to the recent filings to prevent the need for extra
# manual pagination handling
>> > edgar_client.get_submissions_by_company(ticker_or_cik="320193", handle_pagination: bool = True)
{
  "cik": "320193",
  "entityType": "operating",
  "sic": "3571",
  "sicDescription": "Electronic Computers",
  "insiderTransactionForOwnerExists": 0,
  "insiderTransactionForIssuerExists": 1,
  "name": "Apple Inc.",
  "tickers": [
    "AAPL"
  ],
  "exchanges": [
    "Nasdaq"
  ],
  ...
    "filings": {
  "recent": {
    "accessionNumber": [...],
    "filingDate": [...],
    "reportDate": [...],
    "acceptanceDateTime": [...],
    "act": [...],
    "form": [...],
    "fileNumber": [...],
    "filmNumber": [...],
    "items": [...],
    "size": [...],
    "isXBRL": [...],
    "isInlineXBRL": [...],
    "primaryDocument": [...],
    "primaryDocDescription": [...]
  },
  # The extra paginated submission data has already been
  # appended to the lists in the above "recent" key entries
  "files": []
}
}

# Get company concept for Apple
>> > edgar_client.get_concept_by_company(ticker_or_cik="320193", taxonomy="us-gaap", tag="AccountsPayableCurrent")
{
  "cik": 320193,
  "taxonomy": "us-gaap",
  "tag": "AccountsPayableCurrent",
  "label": "Accounts Payable, Current",
  "description": ...,
  "entityName": "Apple Inc.",
  "units": {
    "USD": [...]
  }
}

# Get company facts for Apple
>> > edgar_client.get_facts_by_company(ticker_or_cik="320193")
{
  "cik": 320193,
  "entityName": "Apple Inc.",
  "facts": {
    "dei": {
      "EntityCommonStockSharesOutstanding": {
        "label": "Entity Common Stock, Shares Outstanding",
        "description": ...,
        "units": {
          "shares": [...]
        }
      },
      "EntityPublicFloat": {
        "label": "Entity Public Float",
        "description": ...,
        "units": {
          "USD": [...]
        }
      }
    },
    "us-gaap": {
      "AccountsPayable": {
        "label": "Accounts Payable (Deprecated 2009-01-31)",
        "description": ...,
        "units": {
          "USD": [...]
        }
      },
      "AccountsPayableCurrent": {
        "label": "Accounts Payable, Current",
        "description": ...,
        "units": {
          "USD": [...]
        }
      },
      ...
    }
  }
}

# Get one fact for each reporting entity in specified
# calendar period (Q1 2019)
>> > edgar_client.get_frames(taxonomy="us-gaap", tag="AccountsPayableCurrent", unit="USD", year="2019", quarter=1)
{
  "taxonomy": "us-gaap",
  "tag": "AccountsPayableCurrent",
  "ccp": "CY2019Q1I",
  "uom": "USD",
  "label": "Accounts Payable, Current",
  "description": ...,
  "pts": 3388,
  "data": [
    {
      "accn": "0001555538-19-000006",
      "cik": 1555538,
      "entityName": "SUNCOKE ENERGY PARTNERS, L.P.",
      "loc": "US-IL",
      "end": "2019-03-31",
      "val": 78300000
    },
    {
      "accn": "0000011199-19-000012",
      "cik": 11199,
      "entityName": "BEMIS CO INC",
      "loc": "US-WI",
      "end": "2019-03-31",
      "val": 465700000
    },
    ...
  ]
}
```

### Download Usage

```python
# Get all '10-K', '10-Q', '8-K', '4' filings for Apple (ticker: AAPL)
edgar_client.download_forms_by_company(
    ticker_or_cik='AAPL',  # str - ticker or CIK
    form_types=['10-K', '10-Q', '8-K', '4'],  # List[str] - list of forms
    limit=None,  # Optional[int] - limit the number of forms to download (default: sys.maxsize)
    after=None,  # Optional[str] - only download forms after this date (default: date(1994, 1, 1))
    before=None,  # Optional[str] - only download forms before this date (default: date.today())
    include_amends=False,  # bool - include amended forms (default: False)
    download_details=True,  # bool - download the form details  (default: True)
)

edgar_client.download_facts_for_companies(
    tickers_or_ciks=['AAPL', 'MSFT'],  # List[str] - list of tickers or CIKs
    skip_if_exists=True,  # bool - skip downloading if the file already exists (default: True)
)

edgar_client.download_forms_for_companies(
    tickers_or_ciks=['AAPL', 'MSFT'],  # List[str] - list of tickers or CIKs
    form_types=['10-K', '10-Q', '8-K', '4'],  # List[str] - list of forms
    limit_per_form=None,  # Optional[int] - limit the number of forms to download (default: sys.maxsize)
    after=None,  # Optional[str] - only download forms after this date (default: date(1994, 1, 1))
    before=None,  # Optional[str] - only download forms before this date (default: date.today())
    include_amends=False,  # bool - include amended forms (default: False)
    download_details=True,  # bool - download the form details  (default: True)
)

edgar_client.download_facts_of_all_companies_zip()

edgar_client.download_submissions_of_all_companies_zip()

edgar_client.subscribe_rss_feeds(
    feed_urls,  # List[str] - list of RSS feed URLs
    callback_func=None,  # Optional[Callable] - callback function to call when a new filing is found
    interval=10
)  # Optional[int] - interval in seconds to check for new filings (default: 10)

```

More details on each endpoint can be found on the official SEC API
documentation: [sec.gov/edgar/sec-api-documentation](https://www.sec.gov/edgar/sec-api-documentation).

## Supported SEC Filing Types

This package supports downloading all SEC filing types (6-K, 8-K, 10-K, DEF 14A, S-1, and many others). You can learn
more about the different SEC filing
types [here](https://www.investopedia.com/articles/fundamental-analysis/08/sec-forms.asp). Below is an exhaustive list
of all filings types that can be downloaded by this package:

- 1
- 1-A
- 1-A POS
- 1-A-W
- 1-E
- 1-E AD
- 1-K
- 1-SA
- 1-U
- 1-Z
- 1-Z-W
- 10-12B
- 10-12G
- 10-D
- 10-K
- 10-KT
- 10-Q
- 10-QT
- 11-K
- 11-KT
- 13F-HR
- 13F-NT
- 13FCONP
- 144
- 15-12B
- 15-12G
- 15-15D
- 15F-12B
- 15F-12G
- 15F-15D
- 18-12B
- 18-K
- 19B-4E
- 2-A
- 2-AF
- 2-E
- 20-F
- 20FR12B
- 20FR12G
- 24F-2NT
- 25
- 25-NSE
- 253G1
- 253G2
- 253G3
- 253G4
- 3
- 305B2
- 34-12H
- 4
- 40-17F1
- 40-17F2
- 40-17G
- 40-17GCS
- 40-202A
- 40-203A
- 40-206A
- 40-24B2
- 40-33
- 40-6B
- 40-8B25
- 40-8F-2
- 40-APP
- 40-F
- 40-OIP
- 40FR12B
- 40FR12G
- 424A
- 424B1
- 424B2
- 424B3
- 424B4
- 424B5
- 424B7
- 424B8
- 424H
- 425
- 485APOS
- 485BPOS
- 485BXT
- 486APOS
- 486BPOS
- 486BXT
- 487
- 497
- 497AD
- 497H2
- 497J
- 497K
- 5
- 6-K
- 6B NTC
- 6B ORDR
- 8-A12B
- 8-A12G
- 8-K
- 8-K12B
- 8-K12G3
- 8-K15D5
- 8-M
- 8F-2 NTC
- 8F-2 ORDR
- 9-M
- ABS-15G
- ABS-EE
- ADN-MTL
- ADV-E
- ADV-H-C
- ADV-H-T
- ADV-NR
- ANNLRPT
- APP NTC
- APP ORDR
- APP WD
- APP WDG
- ARS
- ATS-N
- ATS-N-C
- ATS-N/UA
- AW
- AW WD
- C
- C-AR
- C-AR-W
- C-TR
- C-TR-W
- C-U
- C-U-W
- C-W
- CB
- CERT
- CERTARCA
- CERTBATS
- CERTCBO
- CERTNAS
- CERTNYS
- CERTPAC
- CFPORTAL
- CFPORTAL-W
- CORRESP
- CT ORDER
- D
- DEF 14A
- DEF 14C
- DEFA14A
- DEFA14C
- DEFC14A
- DEFC14C
- DEFM14A
- DEFM14C
- DEFN14A
- DEFR14A
- DEFR14C
- DEL AM
- DFAN14A
- DFRN14A
- DOS
- DOSLTR
- DRS
- DRSLTR
- DSTRBRPT
- EFFECT
- F-1
- F-10
- F-10EF
- F-10POS
- F-1MEF
- F-3
- F-3ASR
- F-3D
- F-3DPOS
- F-3MEF
- F-4
- F-4 POS
- F-4MEF
- F-6
- F-6 POS
- F-6EF
- F-7
- F-7 POS
- F-8
- F-8 POS
- F-80
- F-80POS
- F-9
- F-9 POS
- F-N
- F-X
- FOCUSN
- FWP
- G-405
- G-405N
- G-FIN
- G-FINW
- IRANNOTICE
- MA
- MA-A
- MA-I
- MA-W
- MSD
- MSDCO
- MSDW
- N-1
- N-14
- N-14 8C
- N-14MEF
- N-18F1
- N-1A
- N-2
- N-23C-2
- N-23C3A
- N-23C3B
- N-23C3C
- N-2MEF
- N-30B-2
- N-30D
- N-4
- N-5
- N-54A
- N-54C
- N-6
- N-6F
- N-8A
- N-8B-2
- N-8F
- N-8F NTC
- N-8F ORDR
- N-CEN
- N-CR
- N-CSR
- N-CSRS
- N-MFP
- N-MFP1
- N-MFP2
- N-PX
- N-Q
- NO ACT
- NPORT-EX
- NPORT-NP
- NPORT-P
- NRSRO-CE
- NRSRO-UPD
- NSAR-A
- NSAR-AT
- NSAR-B
- NSAR-BT
- NSAR-U
- NT 10-D
- NT 10-K
- NT 10-Q
- NT 11-K
- NT 20-F
- NT N-CEN
- NT N-MFP
- NT N-MFP1
- NT N-MFP2
- NT NPORT-EX
- NT NPORT-P
- NT-NCEN
- NT-NCSR
- NT-NSAR
- NTFNCEN
- NTFNCSR
- NTFNSAR
- NTN 10D
- NTN 10K
- NTN 10Q
- NTN 20F
- OIP NTC
- OIP ORDR
- POS 8C
- POS AM
- POS AMI
- POS EX
- POS462B
- POS462C
- POSASR
- PRE 14A
- PRE 14C
- PREC14A
- PREC14C
- PREM14A
- PREM14C
- PREN14A
- PRER14A
- PRER14C
- PRRN14A
- PX14A6G
- PX14A6N
- QRTLYRPT
- QUALIF
- REG-NR
- REVOKED
- RW
- RW WD
- S-1
- S-11
- S-11MEF
- S-1MEF
- S-20
- S-3
- S-3ASR
- S-3D
- S-3DPOS
- S-3MEF
- S-4
- S-4 POS
- S-4EF
- S-4MEF
- S-6
- S-8
- S-8 POS
- S-B
- S-BMEF
- SC 13D
- SC 13E1
- SC 13E3
- SC 13G
- SC 14D9
- SC 14F1
- SC 14N
- SC TO-C
- SC TO-I
- SC TO-T
- SC13E4F
- SC14D1F
- SC14D9C
- SC14D9F
- SD
- SDR
- SE
- SEC ACTION
- SEC STAFF ACTION
- SEC STAFF LETTER
- SF-1
- SF-3
- SL
- SP 15D2
- STOP ORDER
- SUPPL
- T-3
- TA-1
- TA-2
- TA-W
- TACO
- TH
- TTW
- UNDER
- UPLOAD
- WDL-REQ
- X-17A-5