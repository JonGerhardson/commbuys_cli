---
name: commbuys
description: >
  Massachusetts COMMBUYS procurement data — search bids, blankets/contracts, vendors,
  purchase orders, download attachments, and analyze procurement data. Triggers on:
  MA procurement, COMMBUYS, bids, blankets, MBPOs, statewide contracts, vendors,
  purchase orders, POs, bid attachments, UNSPSC codes, OSD, procurement analysis.
---

# COMMBUYS — Massachusetts Procurement CLI & Analysis

## Overview

COMMBUYS is the official procurement portal for the Commonwealth of Massachusetts,
built on the Periscope/Unison Marketplace platform (now part of Proactis). It handles
the full procurement lifecycle: solicitations, bid responses, contract awards, and
purchase orders for all state agencies, higher education, and many municipalities.

There is **no public API**. The CLI tool (`commbuys.py`) interacts with the site by
simulating PrimeFaces AJAX requests against the JSF-based web interface.

**Portal**: https://www.commbuys.com/bso/

## CLI Commands

| Command | Description | Example |
|---------|-------------|---------|
| `bids` | Search bid solicitations | `python commbuys.py bids --search "construction" --open` |
| `bid-detail` | Get full details for a bid | `python commbuys.py bid-detail BD-25-1020-DCRFS-DC367-116264` |
| `blankets` | Search contracts/MBPOs | `python commbuys.py blankets --search "IT services"` |
| `vendors` | Search registered vendors | `python commbuys.py vendors --search "Staples"` |
| `po-detail` | Get purchase order details | `python commbuys.py po-detail PO-25-1080-OSD03-OSD03-36026` |
| `po-detail` | Get a release PO from a blanket | `python commbuys.py po-detail PO-19-1080-OSD03-SRC01-17283 --release 31` |
| `download` | Download a bid attachment | `python commbuys.py download BD-25-... 2095248 -o file.docx` |
| `info` | Show reference info | `python commbuys.py info urls` |

### Common Options

- `-s, --search TEXT` — search term
- `--org TEXT` — filter by organization name (resolved against dropdown)
- `--vendor TEXT` — vendor name (blankets only)
- `--open` — open bids only (bids only)
- `-x, --exclude TEXT` — exclude records matching term
- `-n, --limit N` — max records (default 100)
- `-f, --format {table,vertical,csv,json}` — output format
- `-o, --output FILE` — save output to file
- `--save-json` — save JSON with metadata to timestamped file
- `--url` — show browser URL for the query

### Search Examples

```bash
# Open bids containing "construction"
python commbuys.py bids --search "construction" --open

# Bids from a specific agency
python commbuys.py bids --org "Department of Transportation" --open

# Contracts by vendor
python commbuys.py blankets --vendor "Blue Tactical" --limit 5

# Export to CSV
python commbuys.py bids --search "software" --format csv -o results.csv

# Bid detail as JSON
python commbuys.py bid-detail BD-25-1020-DCRFS-DC367-116264 --format json

# Purchase order detail
python commbuys.py po-detail PO-25-1080-OSD03-OSD03-36026 --format json

# Release PO against a blanket (e.g., release 31 of an ITS60 blanket)
python commbuys.py po-detail PO-19-1080-OSD03-SRC01-17283 --release 31 --format json

# Download attachment (get IDs from bid-detail --format json first)
python commbuys.py download BD-25-1020-DCRFS-DC367-116264 2095248 -o "Bid Sheet.docx"
```

## PrimeFaces AJAX Architecture

COMMBUYS uses PrimeFaces (JSF component library) for its search pages. The CLI
must follow a 3-step AJAX flow to get results:

### Step 1: GET the search page
- Loads the JSF form HTML
- Extracts `javax.faces.ViewState` and `_csrf` tokens
- Finds the hidden `searchNew` reset button ID from inline `<script>` tags

### Step 2: POST the reset/searchNew button
- Sends a PrimeFaces partial AJAX POST with `Faces-Request: partial/ajax` header
- Targets the reset button to initialize the search form
- Extracts the updated `ViewState` from the AJAX XML response

### Step 3: POST the search button with form fields
- Sends form field values (description, org, vendor, openBids, etc.)
- PrimeFaces returns `<partial-response>` XML with `<![CDATA[...]]>` blocks
- The CDATA blocks contain the results table HTML

### Organization Dropdown Resolution

The `--org` filter must match values from the `<select>` dropdown, not free text.
The CLI resolves org names by:
1. Parsing `<option>` tags from the search page HTML
2. Trying exact match (case-insensitive)
3. Falling back to partial/substring match

### Form IDs by Command

| Search Type | Form ID | Search Button ID | Results Form ID |
|-------------|---------|------------------|-----------------|
| Bids | `bidSearchForm` | `bidSearchForm:btnBidSearch` | `bidSearchResultsForm` |
| Blankets | `contractBlanketSearchForm` | `contractBlanketSearchForm:btnPoSearch` | `contractBlanketSearchResultsForm` |
| Vendors | `vendorSearchForm` | `vendorSearchForm:btnVendorSearch` | `vendorSearchResultsForm` |

## Detail Endpoints

### Bid Detail (`bidDetail.sdo`)
- URL: `https://www.commbuys.com/bso/external/bidDetail.sdo`
- Params: `docId=BID_ID&external=true&parentUrl=close`
- Returns: Full HTML page with bid metadata, items, UNSPSC codes, attachments

### PO Detail (`poSummary.sda`)
- URL: `https://www.commbuys.com/bso/external/purchaseorder/poSummary.sda`
- Params: `docId=PO_ID&releaseNbr=N&external=true&parentUrl=close`
- `releaseNbr=0` returns the base blanket; higher numbers return specific release POs
- Returns: Full HTML page with PO metadata, vendor info, attachments
- **Important**: Many contracts are issued as release POs against statewide blankets
  (e.g., ITS60 Cloud Solutions). These releases won't appear in the blankets search —
  you must know the blanket PO number and release number to fetch them.

### Attachment Download (`bidDetail.sda`)
- URL: `https://www.commbuys.com/bso/external/bidDetail.sda`
- Method: POST with form fields: `docId`, `downloadFileNbr`, `mode=download`, `_csrf`
- Requires: Session cookies from first visiting the bid detail page
- Returns: Binary file with `Content-Disposition` header containing filename

## Key Concepts

### Bids (Bid Solicitations)
Procurement opportunities posted by state agencies. Each bid has:
- **Bid ID**: `BD-YY-XXXX-ORGCD-LOCCD-NNNNN` (YY=fiscal year, ORGCD=org code)
- **Status**: Open, Closed, Awarded, Cancelled
- **Type codes**: SS (Statewide Solicitation), DP (Departmental Purchase), RR (Request for Response)
- **Attachments**: RFRs, bid sheets, specifications, price files

### Blankets / MBPOs (Master Blanket Purchase Orders)
Awarded contracts that agencies can order against. These are the "contracts" in COMMBUYS.
- Linked to the originating bid via bid number
- Have start/end dates and dollar amounts
- Include vendor information

### Purchase Orders
Individual orders placed against blanket contracts or standalone purchases.
- **PO ID**: `PO-YY-XXXX-ORGCD-LOCCD-NNNNN`
- Have vendor, cost, UNSPSC codes, agency/department info
- May reference a master blanket

### Release POs (Blanket Releases)
Orders issued against a statewide blanket contract. These are critical to understand:
- A **blanket PO** (release 0) is the master contract — e.g., ITS60 Cloud Solutions
- **Release POs** (release 1, 2, 3, ...) are individual orders placed against that blanket
- Release POs often contain the actual contract details, signed agreements, and pricing
- **Release POs do NOT appear in blankets search** — you must use `po-detail --release N`
- The blankets search only returns the master blanket (release 0)
- To find a release PO, you typically need the blanket PO number + release number,
  which may come from bid detail pages, news articles, or third-party contract databases
- Example: The MA ChatGPT Enterprise contract is release 31 of the ITS60 solicitation-
  enabled blanket `PO-19-1080-OSD03-SRC01-17283`

### Vendors
Companies registered in COMMBUYS. Search returns name, address, contact info.

### UNSPSC Codes
United Nations Standard Products and Services Code — hierarchical classification
used to categorize procurement items (e.g., 43211500 = Computers).

### Statewide Contracts
Pre-negotiated contracts managed by OSD (Operational Services Division) that any
state agency can order from without running their own procurement. Common categories:
IT equipment, office supplies, vehicles, facilities services.

## Quick Pandas Pattern

```python
import json
import pandas as pd

# Load a saved JSON export
with open("bids_construction_20250213_143022.json") as f:
    data = json.load(f)

df = pd.DataFrame(data["data"])
print(f"Records: {len(df)}, exported: {data['query_timestamp']}")

# Filter and analyze
open_bids = df[df["status"] == "Open"]
by_org = df.groupby("organization").size().sort_values(ascending=False)
```

See `references/analysis_patterns.md` for comprehensive pandas workflows.

## Reference Files

| File | Contents |
|------|----------|
| `references/analysis_patterns.md` | Pandas analysis: bids, contracts, vendors, cross-source joins |
| `references/attachment_processing.md` | PDF/DOCX/XLSX extraction workflows for bid attachments |

## Dependencies

- **CLI tool** (`commbuys.py`): Python stdlib only — no pip installs needed
- **Analysis**: `pandas`, `matplotlib` (optional for charts)
- **Attachment processing**: `pdfplumber` (PDFs), `python-docx` (DOCX), `openpyxl` (XLSX)

Install analysis deps: `pip install pandas pdfplumber python-docx openpyxl matplotlib`

## Relationship to Other Skills

- **CTHru** (`cthru` skill): Where the money went — state spending, payroll, settlements
  via Socrata SODA API. Together with COMMBUYS: procurement process → resulting payments.
- **Federal Procurement** (`federal-procurement` skill): Federal contracts via FPDS/USAspending/SAM.gov.
  COMMBUYS is the Massachusetts state-level equivalent.

Cross-source analysis: Join COMMBUYS vendor names with CTHru vendor payments to see
which procurement contracts result in the largest expenditures.

## Source Code

- CLI: `/home/jon/Documents/commbuys_cli/commbuys.py`
- Project notes: `/home/jon/Documents/commbuys_cli/commbuys.md`
