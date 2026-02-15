#!/usr/bin/env python3
"""
COMMBUYS CLI - Command-line tool for querying Massachusetts procurement data
from the COMMBUYS procurement portal (commbuys.com).

Supports searching bids, contracts (blankets), and vendors via the public
COMMBUYS web interface. No API key required.

Usage:
    python commbuys.py bids --search "construction" --open
    python commbuys.py bids --org "Department of Transportation" --open
    python commbuys.py blankets --search "IT services"
    python commbuys.py bid-detail BD-25-1020-DCRFS-DC367-116264
    python commbuys.py po-detail PO-25-1080-OSD03-OSD03-36026
    python commbuys.py po-detail PO-19-1080-OSD03-SRC01-17283 --release 31
    python commbuys.py download BD-25-1020-DCRFS-DC367-116264 2095248 -o file.docx
    python commbuys.py vendors --search "Acme"
"""

import argparse
import csv
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.cookiejar import CookieJar

# ─── Constants ────────────────────────────────────────────────────────────────

BASE_URL = "https://www.commbuys.com/bso"
BID_SEARCH_PAGE = f"{BASE_URL}/view/search/external/advancedSearchBid.xhtml"
BLANKET_SEARCH_PAGE = f"{BASE_URL}/view/search/external/advancedSearchContractBlanket.xhtml"
VENDOR_SEARCH_PAGE = f"{BASE_URL}/view/search/external/advancedSearchVendor.xhtml"
BID_DETAIL_URL = f"{BASE_URL}/external/bidDetail.sdo"
BID_DETAIL_DOWNLOAD_URL = f"{BASE_URL}/external/bidDetail.sda"
BLANKET_DETAIL_URL = f"{BASE_URL}/external/purchaseOrderDetail.sdo"
PO_DETAIL_URL = f"{BASE_URL}/external/purchaseorder/poSummary.sda"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

MAX_RETRIES = 3
TIMEOUT = 60

# ─── HTTP Client ──────────────────────────────────────────────────────────────


class CommbuysClient:
    """HTTP client for COMMBUYS with cookie handling and retry logic."""

    def __init__(self):
        self.cookie_jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )

    def _make_request(self, url, data=None, method="GET"):
        """Make an HTTP request with retries and exponential backoff."""
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        if data and isinstance(data, dict):
            data = urllib.parse.urlencode(data).encode("utf-8")

        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                response = self.opener.open(req, timeout=TIMEOUT)
                content = response.read()
                # Try utf-8 first, fall back to latin-1
                try:
                    return content.decode("utf-8")
                except UnicodeDecodeError:
                    return content.decode("latin-1")
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"  Retrying in {wait}s (HTTP {e.code})...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise
            except urllib.error.URLError as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"  Retrying in {wait}s ({e.reason})...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise

    def get(self, url, params=None):
        """Make a GET request."""
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return self._make_request(url)

    def post(self, url, data=None):
        """Make a POST request."""
        return self._make_request(url, data=data, method="POST")

    def download_file(self, url, data=None):
        """Make a POST request and return binary response with filename.

        Returns (bytes, filename) where filename is extracted from
        Content-Disposition header, or None if not present.
        """
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
        }

        if data and isinstance(data, dict):
            data = urllib.parse.urlencode(data).encode("utf-8")

        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                response = self.opener.open(req, timeout=TIMEOUT)
                content = response.read()

                # Extract filename from Content-Disposition header
                filename = None
                cd = response.headers.get("Content-Disposition", "")
                fn_match = re.search(r'filename="?([^";\r\n]+)"?', cd)
                if fn_match:
                    filename = fn_match.group(1).strip()

                return content, filename
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"  Retrying in {wait}s (HTTP {e.code})...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise
            except urllib.error.URLError as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"  Retrying in {wait}s ({e.reason})...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise

    def _extract_tokens(self, html_text):
        """Extract ViewState and _csrf tokens from page HTML."""
        tokens = {}
        vs_match = re.search(
            r'name=["\']javax\.faces\.ViewState["\'][^>]*value=["\']([^"\']+)',
            html_text,
        )
        if not vs_match:
            vs_match = re.search(
                r'value=["\']([^"\']+)["\'][^>]*name=["\']javax\.faces\.ViewState',
                html_text,
            )
        if vs_match:
            tokens["javax.faces.ViewState"] = vs_match.group(1)

        csrf_match = re.search(
            r'name=["\']_csrf["\'][^>]*value=["\']([^"\']+)', html_text
        )
        if not csrf_match:
            csrf_match = re.search(
                r'value=["\']([^"\']+)["\'][^>]*name=["\']_csrf', html_text
            )
        if csrf_match:
            tokens["_csrf"] = csrf_match.group(1)

        return tokens

    def _find_reset_button(self, html_text, form_id):
        """Find the hidden reset/searchNew button ID from page JavaScript.

        PrimeFaces generates script tags like:
          <script id="formId:j_idtNNN" type="text/javascript">
          searchNew = function() {return PrimeFaces.ab({s:"formId:j_idtNNN",...});}
          </script>
        """
        # Pattern: searchNew = function() { ... PrimeFaces.ab({s:"formId:j_idtNNN" ...
        pattern = rf'searchNew\s*=\s*function\s*\(\)\s*\{{[^}}]*?s:\s*["\']({re.escape(form_id)}:[^"\']+)["\']'
        match = re.search(pattern, html_text, re.DOTALL)
        if match:
            return match.group(1)
        return None

    def _ajax_post(self, url, data):
        """POST with PrimeFaces AJAX headers."""
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/xml, text/xml, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.5",
            "Faces-Request": "partial/ajax",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        encoded = urllib.parse.urlencode(data).encode("utf-8")

        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
                response = self.opener.open(req, timeout=TIMEOUT)
                content = response.read()
                try:
                    return content.decode("utf-8")
                except UnicodeDecodeError:
                    return content.decode("latin-1")
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"  Retrying in {wait}s (HTTP {e.code})...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise
            except urllib.error.URLError as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"  Retrying in {wait}s ({e.reason})...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise

    def _parse_ajax_response(self, xml_text):
        """Extract CDATA HTML blocks from PrimeFaces partial-response XML."""
        # PrimeFaces returns XML like:
        # <partial-response><changes><update id="..."><![CDATA[...HTML...]]></update>...
        cdata_blocks = re.findall(r'<!\[CDATA\[(.*?)\]\]>', xml_text, re.DOTALL)
        return "\n".join(cdata_blocks)

    def _resolve_org_code(self, page_html, form_id, org_text):
        """Look up an organization dropdown value from display text.

        Returns the option value if a match is found, otherwise returns
        the original text (in case the server accepts it).
        """
        field_name = f"{form_id}:organization"
        select_match = re.search(
            rf'<select[^>]*name="{re.escape(field_name)}"[^>]*>(.*?)</select>',
            page_html,
            re.DOTALL,
        )
        if not select_match:
            return org_text

        options = re.findall(
            r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>',
            select_match.group(1),
        )
        term = org_text.lower()
        for val, text in options:
            if term == text.strip().lower():
                return val
        # Partial match
        for val, text in options:
            if term in text.strip().lower():
                return val
        return org_text

    def ajax_search(self, page_url, form_id, search_button_id, form_fields,
                    results_form_id=None):
        """Orchestrate a PrimeFaces AJAX search.

        Steps:
          1. GET the search page → extract tokens, find reset button
          2. POST the reset/searchNew button → extract updated ViewState
          3. POST the search button with form fields → return result HTML
        """
        # Step 1: GET the page
        page_html = self.get(page_url)
        tokens = self._extract_tokens(page_html)
        if "javax.faces.ViewState" not in tokens:
            raise RuntimeError("Could not extract ViewState from search page")

        # Resolve organization dropdown codes from display text
        org_field = f"{form_id}:organization"
        if org_field in form_fields:
            form_fields[org_field] = self._resolve_org_code(
                page_html, form_id, form_fields[org_field]
            )

        reset_button_id = self._find_reset_button(page_html, form_id)

        # Step 2: POST reset/searchNew button (if found)
        if reset_button_id:
            reset_data = {
                "javax.faces.partial.ajax": "true",
                "javax.faces.source": reset_button_id,
                "javax.faces.partial.execute": "@all",
                "javax.faces.partial.render": form_id,
                reset_button_id: reset_button_id,
                form_id: form_id,
                "javax.faces.ViewState": tokens["javax.faces.ViewState"],
            }
            if "_csrf" in tokens:
                reset_data["_csrf"] = tokens["_csrf"]

            reset_response = self._ajax_post(page_url, reset_data)
            # Extract updated ViewState from response
            vs_match = re.search(
                r'<update\s+id=["\']javax\.faces\.ViewState["\']>\s*<!\[CDATA\[([^\]]+)\]\]>',
                reset_response,
            )
            if vs_match:
                tokens["javax.faces.ViewState"] = vs_match.group(1)

        # Step 3: POST search button with form fields
        render_target = results_form_id if results_form_id else form_id
        search_data = {
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": search_button_id,
            "javax.faces.partial.execute": "@all",
            "javax.faces.partial.render": render_target,
            search_button_id: search_button_id,
            form_id: form_id,
            "javax.faces.ViewState": tokens["javax.faces.ViewState"],
        }
        if "_csrf" in tokens:
            search_data["_csrf"] = tokens["_csrf"]

        # Add form fields
        for key, value in form_fields.items():
            search_data[key] = value

        search_response = self._ajax_post(page_url, search_data)
        return self._parse_ajax_response(search_response)


# ─── HTML Parser ──────────────────────────────────────────────────────────────


def strip_tags(text):
    """Remove HTML tags from text."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = html.unescape(clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def extract_table_rows(html_text, table_id=None, table_class=None):
    """Extract rows from an HTML table, returning list of lists."""
    # Find the target table
    if table_id:
        pattern = rf'<table[^>]*id=["\']?{re.escape(table_id)}["\']?[^>]*>(.*?)</table>'
    elif table_class:
        pattern = rf'<table[^>]*class=["\'][^"\']*{re.escape(table_class)}[^"\']*["\'][^>]*>(.*?)</table>'
    else:
        pattern = r"<table[^>]*>(.*?)</table>"

    match = re.search(pattern, html_text, re.DOTALL | re.IGNORECASE)
    if not match:
        return [], []

    table_html = match.group(1)

    # Extract header
    headers = []
    thead_match = re.search(r"<thead[^>]*>(.*?)</thead>", table_html, re.DOTALL | re.IGNORECASE)
    if thead_match:
        th_cells = re.findall(r"<th[^>]*>(.*?)</th>", thead_match.group(1), re.DOTALL | re.IGNORECASE)
        headers = [strip_tags(cell) for cell in th_cells]

    # Extract rows
    rows = []
    tbody_match = re.search(r"<tbody[^>]*>(.*?)</tbody>", table_html, re.DOTALL | re.IGNORECASE)
    row_html = tbody_match.group(1) if tbody_match else table_html

    tr_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", row_html, re.DOTALL | re.IGNORECASE)
    for tr in tr_matches:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL | re.IGNORECASE)
        if cells:
            row = [strip_tags(cell) for cell in cells]
            rows.append(row)
        elif not headers:
            # Maybe header row with th
            th_cells = re.findall(r"<th[^>]*>(.*?)</th>", tr, re.DOTALL | re.IGNORECASE)
            if th_cells:
                headers = [strip_tags(cell) for cell in th_cells]

    return headers, rows


def parse_bid_search_results(html_text):
    """Parse bid search results from COMMBUYS AJAX response HTML.

    The AJAX response contains table rows with cells in this order:
    [bid_number, bid_number_dup, organization, ?, ?, buyer, description,
     opening_date, ?, ?, status, ?]  (12 cells per row)
    """
    results = []

    row_blocks = re.findall(
        r'<tr[^>]*data-ri="[^"]*"[^>]*>(.*?)</tr>',
        html_text,
        re.DOTALL | re.IGNORECASE,
    )

    for block in row_blocks:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", block, re.DOTALL | re.IGNORECASE)
        if len(cells) < 6:
            continue

        cell_texts = [strip_tags(cell) for cell in cells]
        result = {"bid_number": cell_texts[0]}

        if len(cells) >= 12:
            # Full AJAX result row: 12 cells
            result["organization"] = cell_texts[2]
            result["buyer"] = cell_texts[5]
            result["description"] = cell_texts[6]
            result["open_date"] = cell_texts[7]
            result["status"] = cell_texts[10]
        elif len(cells) >= 6:
            result["description"] = cell_texts[1]
            result["organization"] = cell_texts[2]
            result["open_date"] = cell_texts[4]

        results.append(result)

    return results


def parse_bid_detail(html_text):
    """Parse a bid detail page into a structured dict."""
    detail = {}

    # Extract key-value pairs from the detail table
    # Pattern: "Label:" followed by value in next cell
    field_patterns = {
        "bid_number": r"Bid Number:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "description": r"Description:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "bid_opening_date": r"Bid Opening Date:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "purchaser": r"Purchaser:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "organization": r"Organization:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "department": r"Department:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "location": r"Location:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "fiscal_year": r"Fiscal Year:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "type_code": r"Type Code:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "alternate_id": r"Alternate Id:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "required_date": r"Required Date:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "available_date": r"Available Date\s*:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "info_contact": r"Info Contact:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "bid_type": r"Bid Type:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "purchase_method": r"Purchase Method:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "allow_electronic_quote": r"Allow Electronic Quote:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "informal_bid_flag": r"Informal Bid Flag:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "sbpp_eligible": r"SBPP.*?Eligible\?.*?</td>\s*<td[^>]*>(.*?)</td>",
    }

    for field, pattern in field_patterns.items():
        match = re.search(pattern, html_text, re.DOTALL | re.IGNORECASE)
        if match:
            detail[field] = strip_tags(match.group(1))

    # Extract bulletin description
    bulletin_match = re.search(
        r"Bulletin Desc:\s*</td>\s*<td[^>]*>(.*?)</td>",
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    if bulletin_match:
        detail["bulletin"] = strip_tags(bulletin_match.group(1))

    # Extract ship-to address
    ship_match = re.search(
        r"Ship-to Address:\s*</td>\s*<td[^>]*>(.*?)</td>",
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    if ship_match:
        detail["ship_to_address"] = strip_tags(ship_match.group(1))

    # Extract bill-to address
    bill_match = re.search(
        r"Bill-to Address:\s*</td>\s*<td[^>]*>(.*?)</td>",
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    if bill_match:
        detail["bill_to_address"] = strip_tags(bill_match.group(1))

    # Extract file attachments
    attachments = re.findall(
        r"downloadFile\('(\d+)'\).*?>(.*?)</a>",
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    if attachments:
        detail["attachments"] = [
            {"id": att[0], "name": strip_tags(att[1])} for att in attachments
        ]

    # Extract item information
    items = []
    item_matches = re.findall(
        r"Item #\s*(\d+).*?<td[^>]*>(.*?)</td>.*?U N S P S C Code:\s*</td>\s*<td[^>]*>(.*?)</td>",
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    for item in item_matches:
        items.append(
            {
                "item_number": item[0],
                "description": strip_tags(item[1]),
                "unspsc_code": strip_tags(item[2]),
            }
        )
    if items:
        detail["items"] = items

    return detail


def parse_po_detail(html_text):
    """Parse a purchase order detail page into a structured dict."""
    detail = {}

    field_patterns = {
        "po_number": r"Purchase Order Number:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "release_number": r"Release Number:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "short_description": r"Short Description:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "status": r"Status:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "purchaser": r"Purchaser:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "receipt_method": r"Receipt Method:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "fiscal_year": r"Fiscal Year:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "po_type": r"PO Type:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "organization": r"Organization:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "department": r"Department:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "location": r"Location:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "type_code": r"Type Code:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "alternate_id": r"Alternate Id:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "entered_date": r"Entered Date:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "days_aro": r"Days ARO:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "release_type": r"Release Type:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "contact_instructions": r"Contact Instructions:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "actual_cost": r"Actual Cost:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "print_format": r"Print Format:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "master_blanket_begin_date": r"Master Blanket Begin Date:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "master_blanket_end_date": r"Master Blanket End Date:\s*</td>\s*<td[^>]*>(.*?)</td>",
        "cooperative_purchasing": r"Cooperative Purchasing Allowed:\s*</td>\s*<td[^>]*>(.*?)</td>",
    }

    for field, pattern in field_patterns.items():
        match = re.search(pattern, html_text, re.DOTALL | re.IGNORECASE)
        if match:
            detail[field] = strip_tags(match.group(1))

    # Extract vendor info block
    vendor_match = re.search(
        r"Vendor:?\s*</td>\s*<td[^>]*>(.*?)</td>",
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    if vendor_match:
        detail["vendor"] = strip_tags(vendor_match.group(1))

    # Extract UNSPSC codes
    unspsc_matches = re.findall(
        r"U\s*N\s*S\s*P\s*S\s*C\s*Code:\s*</td>\s*<td[^>]*>(.*?)</td>",
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    if unspsc_matches:
        detail["unspsc_codes"] = [strip_tags(m) for m in unspsc_matches]

    # Extract file attachments (agency and vendor)
    attachments = re.findall(
        r"downloadFile\('(\d+)'\).*?>(.*?)</a>",
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    if attachments:
        detail["attachments"] = [
            {"id": att[0], "name": strip_tags(att[1])} for att in attachments
        ]

    return detail


def parse_blanket_search_results(html_text):
    """Parse blanket/contract search results from AJAX response HTML.

    Blanket result rows have 12 cells:
    [po_number, po_number_dup, bid_number, bid_number_dup, description,
     vendor, contract_type, amount, organization, status, start_date, end_date]
    """
    results = []

    row_blocks = re.findall(
        r'<tr[^>]*data-ri="[^"]*"[^>]*>(.*?)</tr>',
        html_text,
        re.DOTALL | re.IGNORECASE,
    )

    for block in row_blocks:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", block, re.DOTALL | re.IGNORECASE)
        if len(cells) < 5:
            continue

        cell_texts = [strip_tags(cell) for cell in cells]

        result = {"contract_number": cell_texts[0]}

        if len(cells) >= 12:
            # Full AJAX row: 12 cells
            result["bid_number"] = cell_texts[2]
            result["description"] = cell_texts[4]
            result["vendor"] = cell_texts[5]
            result["type"] = cell_texts[6]
            result["amount"] = cell_texts[7]
            result["organization"] = cell_texts[8]
            result["status"] = cell_texts[9]
            result["start_date"] = cell_texts[10]
            result["end_date"] = cell_texts[11]
        elif len(cells) >= 5:
            result["description"] = cell_texts[4]

        results.append(result)

    return results


def parse_vendor_search_results(html_text):
    """Parse vendor search results from AJAX response HTML.

    Vendor result rows have cells:
    [vendor_id_link, vendor_id_hidden, vendor_name, address, city, state,
     zip, contact_name, phone]  (9 cells per row)
    """
    results = []

    row_blocks = re.findall(
        r'<tr[^>]*data-ri="[^"]*"[^>]*>(.*?)</tr>',
        html_text,
        re.DOTALL | re.IGNORECASE,
    )

    for block in row_blocks:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", block, re.DOTALL | re.IGNORECASE)
        if len(cells) < 3:
            continue

        cell_texts = [strip_tags(cell) for cell in cells]

        # Extract vendor ID from link
        vendor_id_match = re.search(r"vendorId=([^&\"']+)", block, re.IGNORECASE)

        result = {}
        if vendor_id_match:
            result["vendor_id"] = vendor_id_match.group(1)

        if len(cells) >= 9:
            # Full AJAX row: 9 cells
            result["vendor_name"] = cell_texts[2]
            result["address"] = cell_texts[3]
            result["city"] = cell_texts[4]
            result["state"] = cell_texts[5]
            result["zip"] = cell_texts[6]
            result["contact"] = cell_texts[7]
            result["phone"] = cell_texts[8]
        elif len(cells) >= 3:
            result["vendor_name"] = cell_texts[2] if cell_texts[2] else cell_texts[0]

        # Skip rows without a vendor name
        if result.get("vendor_name"):
            results.append(result)

    return results


# ─── Search Functions ─────────────────────────────────────────────────────────


def search_bids(client, args):
    """Search for bid solicitations via PrimeFaces AJAX."""
    form_fields = {}

    if getattr(args, "search", None):
        form_fields["bidSearchForm:desc"] = args.search
    if getattr(args, "org", None):
        form_fields["bidSearchForm:organization"] = args.org
    if getattr(args, "open", False):
        form_fields["bidSearchForm:openBids"] = "true"

    result_html = client.ajax_search(
        page_url=BID_SEARCH_PAGE,
        form_id="bidSearchForm",
        search_button_id="bidSearchForm:btnBidSearch",
        form_fields=form_fields,
        results_form_id="bidSearchResultsForm",
    )

    results = parse_bid_search_results(result_html)

    if getattr(args, "exclude", None):
        term = args.exclude.lower()
        results = [
            r
            for r in results
            if term not in json.dumps(r).lower()
        ]

    limit = getattr(args, "limit", 100) or 100
    results = results[:limit]

    return results


def get_bid_detail(client, doc_id):
    """Fetch and parse a single bid's detail page."""
    params = {
        "docId": doc_id,
        "external": "true",
        "parentUrl": "close",
    }

    html_text = client.get(BID_DETAIL_URL, params)
    detail = parse_bid_detail(html_text)

    if not detail.get("bid_number"):
        detail["bid_number"] = doc_id

    detail["portal_url"] = (
        f"{BID_DETAIL_URL}?docId={urllib.parse.quote(doc_id)}"
        f"&external=true&parentUrl=close"
    )

    return detail


def search_blankets(client, args):
    """Search for blankets (contracts) via PrimeFaces AJAX."""
    form_fields = {}

    if getattr(args, "search", None):
        form_fields["contractBlanketSearchForm:desc"] = args.search
    if getattr(args, "org", None):
        form_fields["contractBlanketSearchForm:organization"] = args.org
    if getattr(args, "vendor", None):
        form_fields["contractBlanketSearchForm:vendorName"] = args.vendor

    result_html = client.ajax_search(
        page_url=BLANKET_SEARCH_PAGE,
        form_id="contractBlanketSearchForm",
        search_button_id="contractBlanketSearchForm:btnPoSearch",
        form_fields=form_fields,
        results_form_id="contractBlanketSearchResultsForm",
    )

    results = parse_blanket_search_results(result_html)

    if getattr(args, "exclude", None):
        term = args.exclude.lower()
        results = [r for r in results if term not in json.dumps(r).lower()]

    limit = getattr(args, "limit", 100) or 100
    results = results[:limit]

    return results


def search_vendors(client, args):
    """Search for vendors via PrimeFaces AJAX."""
    form_fields = {}

    if getattr(args, "search", None):
        form_fields["vendorSearchForm:vendorName"] = args.search

    result_html = client.ajax_search(
        page_url=VENDOR_SEARCH_PAGE,
        form_id="vendorSearchForm",
        search_button_id="vendorSearchForm:btnVendorSearch",
        form_fields=form_fields,
        results_form_id="vendorSearchResultsForm",
    )

    results = parse_vendor_search_results(result_html)

    if getattr(args, "exclude", None):
        term = args.exclude.lower()
        results = [r for r in results if term not in json.dumps(r).lower()]

    limit = getattr(args, "limit", 100) or 100
    results = results[:limit]

    return results


def get_po_detail(client, doc_id, release=0):
    """Fetch and parse a single purchase order's detail page.

    Args:
        client: CommbuysClient instance
        doc_id: PO document ID (e.g., PO-25-1080-OSD03-OSD03-36026)
        release: Release number for blanket POs (default 0 for base blanket)
    """
    release_str = str(release)
    params = {
        "docId": doc_id,
        "releaseNbr": release_str,
        "external": "true",
        "parentUrl": "close",
    }

    html_text = client.get(PO_DETAIL_URL, params)
    detail = parse_po_detail(html_text)

    if not detail.get("po_number"):
        detail["po_number"] = doc_id

    detail["portal_url"] = (
        f"{PO_DETAIL_URL}?docId={urllib.parse.quote(doc_id)}"
        f"&releaseNbr={release_str}&external=true&parentUrl=close"
    )

    return detail


def download_attachment(client, doc_id, attachment_id, output_path=None):
    """Download a file attachment from a bid detail page.

    Steps:
      1. GET the bid detail page to establish session and get CSRF token
      2. POST to bidDetail.sda with download form fields
      3. Save binary content to output path
    """
    # Step 1: GET bid detail page for session + CSRF
    params = {
        "docId": doc_id,
        "external": "true",
        "parentUrl": "close",
    }
    page_html = client.get(BID_DETAIL_URL, params)
    tokens = client._extract_tokens(page_html)

    # Step 2: POST download request
    form_data = {
        "docId": doc_id,
        "downloadFileNbr": attachment_id,
        "mode": "download",
    }
    if "_csrf" in tokens:
        form_data["_csrf"] = tokens["_csrf"]

    content, server_filename = client.download_file(BID_DETAIL_DOWNLOAD_URL, form_data)

    # Determine output filename
    if not output_path:
        output_path = server_filename or f"attachment_{attachment_id}"

    with open(output_path, "wb") as f:
        f.write(content)

    return output_path, len(content)


# ─── Output Formatting ────────────────────────────────────────────────────────


def format_table(records, fields=None):
    """Format records as an ASCII table."""
    if not records:
        return "No records found."

    if not fields:
        # Collect all fields from all records
        fields = []
        for r in records:
            for k in r.keys():
                if k not in fields and k != "attachments" and k != "items":
                    fields.append(k)

    # Calculate column widths
    widths = {}
    for field in fields:
        widths[field] = len(field)
        for record in records:
            val = str(record.get(field, ""))
            # Truncate long values for table display
            if len(val) > 60:
                val = val[:57] + "..."
            widths[field] = max(widths[field], len(val))

    # Cap max width
    for field in widths:
        widths[field] = min(widths[field], 60)

    # Build header
    header = " | ".join(f"{field:<{widths[field]}}" for field in fields)
    separator = "-+-".join("-" * widths[field] for field in fields)

    lines = [header, separator]

    for record in records:
        row_vals = []
        for field in fields:
            val = str(record.get(field, ""))
            if len(val) > 60:
                val = val[:57] + "..."
            row_vals.append(f"{val:<{widths[field]}}")
        lines.append(" | ".join(row_vals))

    lines.append(f"\n--- {len(records)} records ---")

    return "\n".join(lines)


def format_vertical(records):
    """Format records as vertical key-value pairs (card view)."""
    if not records:
        return "No records found."

    output = []
    for i, record in enumerate(records):
        if i > 0:
            output.append("─" * 60)

        max_key_len = max(len(k) for k in record.keys()) if record else 0

        for key, value in record.items():
            if key == "attachments" and isinstance(value, list):
                output.append(f"  {key:<{max_key_len}} : ")
                for att in value:
                    output.append(f"  {'':>{max_key_len}}   - {att.get('name', '')} (ID: {att.get('id', '')})")
            elif key == "items" and isinstance(value, list):
                output.append(f"  {key:<{max_key_len}} : ")
                for item in value:
                    output.append(f"  {'':>{max_key_len}}   - Item #{item.get('item_number', '')}: {item.get('description', '')[:80]}")
                    if item.get("unspsc_code"):
                        output.append(f"  {'':>{max_key_len}}     UNSPSC: {item['unspsc_code']}")
            else:
                val_str = str(value)
                if len(val_str) > 100:
                    # Wrap long values
                    words = val_str.split()
                    lines_list = []
                    current_line = ""
                    for word in words:
                        if len(current_line) + len(word) + 1 > 80:
                            lines_list.append(current_line)
                            current_line = word
                        else:
                            current_line = f"{current_line} {word}" if current_line else word
                    if current_line:
                        lines_list.append(current_line)

                    output.append(f"  {key:<{max_key_len}} : {lines_list[0]}")
                    for line in lines_list[1:]:
                        output.append(f"  {'':>{max_key_len}}   {line}")
                else:
                    output.append(f"  {key:<{max_key_len}} : {val_str}")

    output.append(f"\n--- {len(records)} records ---")
    return "\n".join(output)


def format_csv_output(records, fields=None):
    """Format records as CSV."""
    if not records:
        return ""

    if not fields:
        fields = []
        for r in records:
            for k in r.keys():
                if k not in fields:
                    fields.append(k)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        # Flatten complex fields
        flat = {}
        for k, v in record.items():
            if isinstance(v, (list, dict)):
                flat[k] = json.dumps(v)
            else:
                flat[k] = v
        writer.writerow(flat)

    return output.getvalue()


def format_json_output(records):
    """Format records as JSON."""
    return json.dumps(records, indent=2, default=str)


def output_results(records, args, record_type="records"):
    """Output results in the requested format."""
    fmt = getattr(args, "format", "table") or "table"

    if fmt == "table":
        text = format_table(records)
    elif fmt == "vertical":
        text = format_vertical(records)
    elif fmt == "csv":
        text = format_csv_output(records)
    elif fmt == "json":
        text = format_json_output(records)
    else:
        text = format_table(records)

    # Output to file or stdout
    output_file = getattr(args, "output", None)
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Output saved to {output_file}")
    else:
        print(text)

    # Save JSON with metadata
    if getattr(args, "save_json", False):
        search_term = getattr(args, "search", "") or ""
        org_term = getattr(args, "org", "") or ""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{record_type}"
        if search_term:
            safe_search = re.sub(r"[^\w]", "_", search_term)[:30]
            filename += f"_{safe_search}"
        if org_term:
            safe_org = re.sub(r"[^\w]", "_", org_term)[:30]
            filename += f"_{safe_org}"
        filename += f"_{timestamp}.json"

        metadata = {
            "portal_url": "https://www.commbuys.com/bso/",
            "search_url": BID_SEARCH_PAGE,
            "query_timestamp": datetime.now().isoformat(),
            "record_count": len(records),
            "search_term": search_term,
            "data": records,
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=str)
        print(f"JSON saved to {filename}")

    # Show URL if requested
    if getattr(args, "url", False):
        params = {}
        if getattr(args, "search", None):
            params["q"] = args.search
        if getattr(args, "open", False):
            params["openBids"] = "true"
        portal_url = f"{BID_SEARCH_PAGE}?{urllib.parse.urlencode(params)}" if params else BID_SEARCH_PAGE
        print(f"\nView in browser: {portal_url}")


# ─── CLI Setup ────────────────────────────────────────────────────────────────


def build_parser():
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="commbuys",
        description="Query Massachusetts procurement data from COMMBUYS",
        epilog="""Examples:
  commbuys bids --search "construction" --open
  commbuys bids --org "Department of Transportation" --limit 50
  commbuys bid-detail BD-25-1020-DCRFS-DC367-116264
  commbuys po-detail PO-25-1080-OSD03-OSD03-36026
  commbuys blankets --search "IT services"
  commbuys vendors --search "Acme"
  commbuys download BD-25-1020-DCRFS-DC367-116264 2095248 -o file.docx
  commbuys bids --search "software" --format csv -o results.csv
  commbuys bids --search "consulting" --save-json""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # --- bids command ---
    bid_parser = subparsers.add_parser("bids", help="Search bid solicitations")
    bid_parser.add_argument("-s", "--search", help="Search term for bid description")
    bid_parser.add_argument("--org", help="Filter by organization name")
    bid_parser.add_argument("--open", action="store_true", help="Show only open bids")
    bid_parser.add_argument("-x", "--exclude", help="Exclude records matching term")
    bid_parser.add_argument("-n", "--limit", type=int, default=100, help="Max records (default: 100)")
    bid_parser.add_argument("-f", "--format", choices=["table", "vertical", "csv", "json"], default="table")
    bid_parser.add_argument("-o", "--output", help="Save output to file")
    bid_parser.add_argument("--url", action="store_true", help="Show browser URL")
    bid_parser.add_argument("--save-json", action="store_true", help="Save raw JSON with metadata")

    # --- bid-detail command ---
    detail_parser = subparsers.add_parser("bid-detail", help="Get detailed info for a specific bid")
    detail_parser.add_argument("doc_id", help="Bid document ID (e.g., BD-25-1020-DCRFS-DC367-116264)")
    detail_parser.add_argument("-f", "--format", choices=["vertical", "json", "table"], default="vertical")
    detail_parser.add_argument("-o", "--output", help="Save output to file")
    detail_parser.add_argument("--save-json", action="store_true", help="Save raw JSON with metadata")
    detail_parser.add_argument("--url", action="store_true", help="Show browser URL")

    # --- blankets command ---
    blanket_parser = subparsers.add_parser("blankets", help="Search contracts / blanket purchase orders")
    blanket_parser.add_argument("-s", "--search", help="Search term")
    blanket_parser.add_argument("--org", help="Filter by organization name")
    blanket_parser.add_argument("--vendor", help="Search by vendor name")
    blanket_parser.add_argument("-x", "--exclude", help="Exclude records matching term")
    blanket_parser.add_argument("-n", "--limit", type=int, default=100, help="Max records (default: 100)")
    blanket_parser.add_argument("-f", "--format", choices=["table", "vertical", "csv", "json"], default="table")
    blanket_parser.add_argument("-o", "--output", help="Save output to file")
    blanket_parser.add_argument("--url", action="store_true", help="Show browser URL")
    blanket_parser.add_argument("--save-json", action="store_true", help="Save raw JSON with metadata")

    # --- vendors command ---
    vendor_parser = subparsers.add_parser("vendors", help="Search registered vendors")
    vendor_parser.add_argument("-s", "--search", help="Search term for vendor name")
    vendor_parser.add_argument("-x", "--exclude", help="Exclude records matching term")
    vendor_parser.add_argument("-n", "--limit", type=int, default=100, help="Max records (default: 100)")
    vendor_parser.add_argument("-f", "--format", choices=["table", "vertical", "csv", "json"], default="table")
    vendor_parser.add_argument("-o", "--output", help="Save output to file")
    vendor_parser.add_argument("--url", action="store_true", help="Show browser URL")
    vendor_parser.add_argument("--save-json", action="store_true", help="Save raw JSON with metadata")

    # --- po-detail command ---
    po_parser = subparsers.add_parser("po-detail", help="Get detailed info for a purchase order")
    po_parser.add_argument("doc_id", help="PO document ID (e.g., PO-25-1080-OSD03-OSD03-36026)")
    po_parser.add_argument("-r", "--release", type=int, default=0,
                           help="Release number for blanket POs (default: 0 for base blanket)")
    po_parser.add_argument("-f", "--format", choices=["vertical", "json", "table"], default="vertical")
    po_parser.add_argument("-o", "--output", help="Save output to file")
    po_parser.add_argument("--save-json", action="store_true", help="Save raw JSON with metadata")
    po_parser.add_argument("--url", action="store_true", help="Show browser URL")

    # --- download command ---
    dl_parser = subparsers.add_parser("download", help="Download a bid attachment file")
    dl_parser.add_argument("doc_id", help="Bid document ID (e.g., BD-25-1020-DCRFS-DC367-116264)")
    dl_parser.add_argument("attachment_id", help="Attachment file number ID")
    dl_parser.add_argument("-o", "--output", help="Output file path (default: server filename)")

    # --- info command ---
    info_parser = subparsers.add_parser("info", help="Show information about COMMBUYS data and URLs")
    info_parser.add_argument(
        "topic",
        nargs="?",
        choices=["urls", "search-tips", "organizations", "bid-format"],
        default="urls",
        help="Topic to show info about",
    )

    return parser


# ─── Info Command ─────────────────────────────────────────────────────────────


def show_info(topic):
    """Display helpful information about COMMBUYS."""
    if topic == "urls":
        print("""COMMBUYS URLs and Endpoints:

  Portal:           https://www.commbuys.com/bso/
  Open Bids:        https://www.commbuys.com/bso/view/search/external/advancedSearchBid.xhtml?openBids=true
  Search Bids:      https://www.commbuys.com/bso/view/search/external/advancedSearchBid.xhtml?q=SEARCH_TERM&currentDocType=bids
  Bid Detail:       https://www.commbuys.com/bso/external/bidDetail.sdo?docId=BID_ID&external=true&parentUrl=close
  Search Blankets:  https://www.commbuys.com/bso/view/search/external/advancedSearchBid.xhtml?currentDocType=blankets

  Mass.gov Info:    https://www.mass.gov/learn-about-commbuys-resources
  OSD Website:      https://www.mass.gov/orgs/operational-services-division""")

    elif topic == "search-tips":
        print("""COMMBUYS Search Tips:

  1. Use specific keywords - COMMBUYS searches across descriptions and item details
  2. Organization names must match the COMMBUYS listing (use --org to filter)
  3. Bid IDs follow the pattern: BD-YY-XXXX-ORGCD-LOCCD-NNNNN
     - YY = fiscal year (e.g., 25 = FY2025)
     - ORGCD = organization code
     - LOCCD = location code
     - NNNNN = sequential number
  4. Use --open flag to see only bids that are currently accepting responses
  5. Blankets (contracts) are Master Blanket Purchase Orders (MBPOs)
  6. UNSPSC codes categorize items - search by commodity type for best results""")

    elif topic == "organizations":
        print("""Major COMMBUYS Organizations (partial list):

  Executive Departments:
    Department of Transportation (DOT)
    Department of Public Health
    Department of Conservation and Recreation
    Department of Correction
    Department of Children and Families
    Department of Environmental Protection
    Department of Elementary and Secondary Education
    Executive Office of Health and Human Services

  Central Procurement:
    Operational Services Division (OSD)
    Division of Capital Asset Management and Maintenance (DCAMM)
    Department of State Purchasing

  Higher Education:
    University of Massachusetts System
    Bridgewater State University, Fitchburg State University, etc.
    Community Colleges (15 institutions)

  Other:
    Massachusetts Bay Transportation Authority (MBTA)
    Massachusetts Port Authority (Massport)
    Trial Court
    Various Housing Authorities, School Districts, Municipalities

  Use the advanced search at commbuys.com for a full list.""")

    elif topic == "bid-format":
        print("""COMMBUYS Bid Document ID Format:

  Pattern: BD-YY-XXXX-ORGCD-LOCCD-NNNNN

  BD     = Document type prefix (Bid)
  YY     = Fiscal year (e.g., 25 = FY2025)
  XXXX   = Category/contract code
  ORGCD  = Organization code (e.g., DCRFS, OSD04, DOT01)
  LOCCD  = Location/department code
  NNNNN  = Sequential document number

  Examples:
    BD-25-1020-DCRFS-DC367-116264   (DCR Fire Services)
    BD-17-1080-OSD04-OSD04-9185     (OSD Statewide Contract)
    BD-23-1602-CHAMD-CHAMD-102978   (DCAMM)

  Type Codes:
    SS = Statewide Solicitation
    DP = Departmental Purchase
    RR = Request for Response""")


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "info":
        show_info(args.topic)
        return

    # Initialize client
    client = CommbuysClient()

    try:
        if args.command == "bids":
            results = search_bids(client, args)
            output_results(results, args, "bids")

        elif args.command == "bid-detail":
            detail = get_bid_detail(client, args.doc_id)
            output_results([detail], args, "bid_detail")

        elif args.command == "blankets":
            results = search_blankets(client, args)
            output_results(results, args, "blankets")

        elif args.command == "vendors":
            results = search_vendors(client, args)
            output_results(results, args, "vendors")

        elif args.command == "po-detail":
            detail = get_po_detail(client, args.doc_id, release=args.release)
            output_results([detail], args, "po_detail")

        elif args.command == "download":
            print(f"Downloading attachment {args.attachment_id} from {args.doc_id}...",
                  file=sys.stderr)
            filepath, size = download_attachment(
                client, args.doc_id, args.attachment_id, args.output
            )
            print(f"Saved to {filepath} ({size:,} bytes)")

    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        if e.code == 403:
            print("Access denied. COMMBUYS may be blocking automated requests.", file=sys.stderr)
            print("Try again later or access directly: https://www.commbuys.com/bso/", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        print("Check your internet connection and try again.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
