# COMMBUYS CLI

A command-line tool for querying Massachusetts procurement data from the [COMMBUYS Procurement Portal](https://www.commbuys.com).

## Overview

COMMBUYS CLI provides programmatic access to Massachusetts state procurement data — bid solicitations, contracts (blankets/MBPOs), and registered vendors — via web scraping of the public COMMBUYS interface. It supports filtering, multiple output formats, and automatic JSON export with source URLs.

This is the **procurement counterpart** to [cthru_cli](https://github.com/jongerhardson/cthru_cli):
- **CTHru** = where the money went (spending, payroll, settlements)
- **COMMBUYS** = how contracts are solicited and awarded (procurement)

## Quickstart

```bash
git clone https://github.com/JonGerhardson/commbuys_cli && cd commbuys_cli
```

The CLI tool is pure python. The associated coding agent skill needs the following packages to parse the procurement documents for you. 

```
pip install pandas pdfplumber python-docx openpyxl
```

**Example query:**
```bash
python commbuys.py bids --search "fire hose" --open
```

**Example: Get bid details:**
```bash
python commbuys.py bid-detail BD-25-1020-DCRFS-DC367-116264
```

**Example detail output:**
```
  bid_number        : BD-25-1020-DCRFS-DC367-116264
  description       : PSE01 - Mercedes Fire Hoses
  bid_opening_date  : 05/12/2025 05:00:00 PM
  purchaser         : KARIM GLASGOW
  organization      : Department of Conservation and Recreation
  department        : DCRFS - DCR Forestry / STIP
  fiscal_year       : 25
  type_code         : SS - Statewide Solicitation
  bid_type          : OPEN
  purchase_method   : Open Market
  bulletin          : DCR Fire Control is soliciting bids under the PSE01
                      Public Safety Equipment State Contract for the following
                      Mercedes "Fire Boss" fire hose...
  portal_url        : https://www.commbuys.com/bso/external/bidDetail.sdo?...
```

## Usage

```
usage: commbuys [-h] {bids,bid-detail,blankets,vendors,info} ...

Query Massachusetts procurement data from COMMBUYS

positional arguments:
  {bids,bid-detail,blankets,vendors,info}
                        Command to run
    bids                Search bid solicitations
    bid-detail          Get detailed info for a specific bid
    blankets            Search contracts / blanket purchase orders
    vendors             Search registered vendors
    info                Show information about COMMBUYS data and URLs

options:
  -h, --help            show this help message and exit

Examples:
  commbuys bids --search "construction" --open
  commbuys bids --org "Department of Transportation" --limit 50
  commbuys bid-detail BD-25-1020-DCRFS-DC367-116264
  commbuys blankets --search "IT services"
  commbuys vendors --search "Acme"
  commbuys bids --search "software" --format csv -o results.csv
  commbuys bids --search "consulting" --save-json
```

## Setup

### Requirements

- Python 3.7+
- No external dependencies (uses only standard library)
- No API key required — uses public COMMBUYS web interface

### Installation

To install globally, run `bash install.sh` from this directory. Then use `commbuys` from anywhere and see the README with `man commbuys`.

## Available Commands

| Command | Description |
|---------|-------------|
| `bids` | Search bid solicitations (RFRs, RFPs, etc.) |
| `bid-detail` | Get full details for a specific bid by ID |
| `blankets` | Search contracts / Master Blanket Purchase Orders |
| `vendors` | Search registered vendors |
| `info` | Reference information about COMMBUYS data |

## Query Options

### Common Options (all search commands)

| Option | Description |
|--------|-------------|
| `-s, --search TEXT` | Search term for description/name |
| `-x, --exclude TEXT` | Exclude records matching term |
| `-n, --limit N` | Number of records to return (default: 100) |
| `-f, --format` | Output format: `table`, `vertical`, `csv`, or `json` |
| `-o, --output FILE` | Save output to file |
| `--url` | Show link to view data in browser |
| `--save-json` | Save raw JSON with metadata to timestamped file |

### Bids-Specific Options

| Option | Description |
|--------|-------------|
| `--org NAME` | Filter by organization name |
| `--open` | Show only currently open bids |

### Blankets-Specific Options

| Option | Description |
|--------|-------------|
| `--org NAME` | Filter by organization name |

### Bid Detail Options

| Option | Description |
|--------|-------------|
| `doc_id` | Required. The bid document ID |

## Examples

### Search Bids

```bash
# Find open construction bids
python commbuys.py bids --search "construction" --open

# Search DOT bids
python commbuys.py bids --org "Department of Transportation" --open

# Search and exclude a term
python commbuys.py bids --search "equipment" --exclude "office"

# Export to CSV
python commbuys.py bids --search "software" --format csv -o software_bids.csv

# Save JSON with metadata
python commbuys.py bids --search "consulting" --save-json
```

### Get Bid Details

```bash
# Full details for a specific bid
python commbuys.py bid-detail BD-25-1020-DCRFS-DC367-116264

# As JSON
python commbuys.py bid-detail BD-25-1020-DCRFS-DC367-116264 --format json

# Save to file
python commbuys.py bid-detail BD-25-1020-DCRFS-DC367-116264 -o bid_info.txt
```

### Search Contracts

```bash
# Search active contracts
python commbuys.py blankets --search "IT services"

# Filter by organization
python commbuys.py blankets --search "office supplies" --org "Operational Services"
```

### Search Vendors

```bash
# Find vendors by name
python commbuys.py vendors --search "Acme"

# Export vendor list
python commbuys.py vendors --search "technology" --format csv -o tech_vendors.csv
```

### Reference Information

```bash
# Show useful URLs
python commbuys.py info urls

# Search tips
python commbuys.py info search-tips

# Major organizations
python commbuys.py info organizations

# Bid ID format explanation
python commbuys.py info bid-format
```

## Understanding Bid IDs

COMMBUYS bid document IDs follow the pattern:

```
BD-YY-XXXX-ORGCD-LOCCD-NNNNN
```

| Part | Meaning | Example |
|------|---------|---------|
| `BD` | Document type (Bid) | `BD` |
| `YY` | Fiscal year | `25` (FY2025) |
| `XXXX` | Category/contract code | `1020` |
| `ORGCD` | Organization code | `DCRFS` (DCR Fire Services) |
| `LOCCD` | Location/dept code | `DC367` |
| `NNNNN` | Sequential number | `116264` |

## JSON Output Format

When using `--save-json`, the output includes metadata:

```json
{
  "portal_url": "https://www.commbuys.com/bso/",
  "search_url": "https://www.commbuys.com/bso/view/search/external/advancedSearchBid.xhtml",
  "query_timestamp": "2026-02-13T14:30:00.000000",
  "record_count": 15,
  "search_term": "construction",
  "data": [
    { "bid_number": "BD-25-...", "description": "...", ... },
    ...
  ]
}
```

## How It Works

COMMBUYS is built on the Periscope S2G platform and does **not** offer a public REST API (unlike CTHru's Socrata SODA API). This tool:

1. Makes HTTP requests to COMMBUYS public search pages
2. Parses HTML responses to extract structured data
3. Applies client-side filtering as needed
4. Formats output for the terminal

### Key COMMBUYS URLs

| Resource | URL |
|----------|-----|
| Portal | https://www.commbuys.com/bso/ |
| Open Bids | https://www.commbuys.com/bso/view/search/external/advancedSearchBid.xhtml?openBids=true |
| Bid Search | https://www.commbuys.com/bso/view/search/external/advancedSearchBid.xhtml |
| Bid Detail | https://www.commbuys.com/bso/external/bidDetail.sdo?docId=BID_ID |
| Mass.gov Info | https://www.mass.gov/learn-about-commbuys-resources |

## Comparison with CTHru CLI

| Feature | CTHru CLI | COMMBUYS CLI |
|---------|-----------|--------------|
| **Data** | Spending, payroll, settlements, revenue | Bids, contracts, vendors |
| **API** | Socrata SODA API (REST/JSON) | Web scraping (HTML parsing) |
| **Auth** | API key required | No auth needed |
| **Data freshness** | Near real-time | Depends on page caching |
| **Query flexibility** | Full SQL-like filtering | Keyword search + client filtering |
| **Use case** | "Where did the money go?" | "How are contracts awarded?" |

Together, these tools give you both sides of Massachusetts state procurement and spending.

## Tips

### Rate Limiting
COMMBUYS may throttle or block requests if you make too many in quick succession. The tool includes automatic retry with exponential backoff, but if you hit persistent errors, wait a few minutes before trying again.

### Search Quality
COMMBUYS search works best with specific terms. Broad searches may return too many results. Use `--org` to narrow down by agency when possible.

### Accessing Full Documents
Bid solicitations often include attached documents (RFRs, specifications, bid sheets). Use `bid-detail` to see attachment info, then visit the portal URL to download them.

## Troubleshooting

### "Access denied" / HTTP 403
COMMBUYS may temporarily block automated access. Wait a few minutes and try again, or access the portal directly in your browser.

### No Results Found
- Try broader search terms
- Check spelling — COMMBUYS search is somewhat literal
- Use `--open` only if you want currently accepting bids; omit it for all bids
- Visit the COMMBUYS portal directly to verify data availability

### Timeout Errors
- Try more specific searches to reduce result size
- Default timeout is 60 seconds
- Check your internet connection

## Data Sources

Data comes from the Massachusetts COMMBUYS procurement portal, managed by the Operational Services Division (OSD):

- **Portal**: https://www.commbuys.com
- **Info**: https://www.mass.gov/learn-about-commbuys-resources
- **OSD**: https://www.mass.gov/orgs/operational-services-division
- **Powered by**: Periscope S2G (Unison Marketplace)

## Output Formats

- `table` (default): Readable ASCII table with truncated columns
- `vertical`: Key-value card view, great for bid details
- `csv`: Standard CSV output (RFC 4180 compliant)
- `json`: Raw JSON array

## Features & Design

- **No dependencies**: Uses only Python standard library
- **Retry logic**: Automatic retry with exponential backoff for transient errors
- **Cookie handling**: Maintains session cookies for multi-request operations
- **Input sanitization**: Search terms are URL-encoded before submission
- **Proper CSV**: Uses Python's csv module for correct output
- **Flexible output**: Table, vertical, CSV, and JSON formats
- **Metadata export**: `--save-json` includes query context and timestamps

## License

BSD-4-Clause 
