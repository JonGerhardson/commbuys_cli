# COMMBUYS Attachment Processing

## Common Attachment Types

COMMBUYS bid attachments typically include:

| Type | Format | Contents |
|------|--------|----------|
| RFR (Request for Response) | PDF | Full solicitation document with requirements, scope, evaluation criteria |
| Bid Response Sheet | DOCX/XLSX | Template for vendors to fill in pricing and qualifications |
| Price File / Cost Table | XLSX | Line-item pricing with quantities, unit costs, totals |
| Specifications | PDF | Technical requirements, drawings, standards |
| Amendment / Addendum | PDF | Changes to the original solicitation |
| Award Letter | PDF | Contract award notification |
| Terms & Conditions | PDF | Standard Commonwealth procurement terms |

## Workflow: Bid Detail → Download → Extract → Analyze

```bash
# Step 1: Get bid details with attachment IDs
python commbuys.py bid-detail BD-25-1020-DCRFS-DC367-116264 --format json > bid.json

# Step 2: Download attachments (use IDs from the "attachments" field)
python commbuys.py download BD-25-1020-DCRFS-DC367-116264 2095248 -o "Bid Sheet.docx"
python commbuys.py download BD-25-1020-DCRFS-DC367-116264 2095249 -o "RFR.pdf"
python commbuys.py download BD-25-1020-DCRFS-DC367-116264 2095250 -o "Price File.xlsx"
```

```python
# Step 3: Extract and analyze (see sections below)
```

## PDF Text Extraction with pdfplumber

```python
import pdfplumber

def extract_pdf_text(path):
    """Extract all text from a PDF file."""
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)

text = extract_pdf_text("RFR.pdf")
print(text[:2000])
```

### Extracting Tables from PDFs

```python
def extract_pdf_tables(path):
    """Extract all tables from a PDF as lists of lists."""
    all_tables = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                all_tables.append({
                    "page": i + 1,
                    "rows": table,
                })
    return all_tables

tables = extract_pdf_tables("RFR.pdf")
for t in tables:
    print(f"Page {t['page']}: {len(t['rows'])} rows")
    for row in t["rows"][:3]:
        print(f"  {row}")
```

### Converting PDF Tables to DataFrames

```python
import pandas as pd

tables = extract_pdf_tables("Price File.pdf")
if tables:
    t = tables[0]
    # First row is usually headers
    df = pd.DataFrame(t["rows"][1:], columns=t["rows"][0])
    print(df.head())
```

## DOCX Extraction with python-docx

```python
from docx import Document

def extract_docx(path):
    """Extract paragraphs and tables from a DOCX file."""
    doc = Document(path)

    # Paragraphs
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

    # Tables
    tables = []
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(cells)
        tables.append(rows)

    return {"paragraphs": paragraphs, "tables": tables}

result = extract_docx("Bid Sheet.docx")
print(f"Paragraphs: {len(result['paragraphs'])}")
print(f"Tables: {len(result['tables'])}")

# Show first table
if result["tables"]:
    for row in result["tables"][0][:5]:
        print(row)
```

### Extracting Form Fields from DOCX

Bid response sheets often have table-based forms:

```python
def extract_form_fields(path):
    """Extract label-value pairs from DOCX tables."""
    doc = Document(path)
    fields = {}
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if len(cells) >= 2 and cells[0]:
                # Assume first cell is label, second is value
                fields[cells[0].rstrip(":")] = cells[1]
    return fields

fields = extract_form_fields("Bid Sheet.docx")
for k, v in fields.items():
    print(f"  {k}: {v}")
```

## XLSX Price File Parsing

```python
import pandas as pd

# Basic read
df = pd.read_excel("Price File.xlsx")
print(df.columns.tolist())
print(df.head())

# If the header row isn't the first row
df = pd.read_excel("Price File.xlsx", header=2)  # 0-indexed

# Multiple sheets
xls = pd.ExcelFile("Price File.xlsx")
print(f"Sheets: {xls.sheet_names}")
for sheet in xls.sheet_names:
    df = pd.read_excel(xls, sheet_name=sheet)
    print(f"\n--- {sheet} ({len(df)} rows) ---")
    print(df.head())
```

### Common Price File Patterns

```python
# Clean currency columns
df["unit_price"] = (
    df["Unit Price"]
    .astype(str)
    .str.replace(r"[$,]", "", regex=True)
    .astype(float, errors="ignore")
)

# Calculate extended prices
df["extended"] = df["unit_price"] * df["Quantity"]
print(f"Total: ${df['extended'].sum():,.2f}")

# Summary by category
by_category = df.groupby("Category")["extended"].sum().sort_values(ascending=False)
```

## Batch Processing Multiple Attachments

```python
import json
import os

# Load bid detail
with open("bid.json") as f:
    bid = json.load(f)

# bid-detail output is a list with one record
detail = bid if isinstance(bid, dict) else bid[0]

# Download and process all attachments
for att in detail.get("attachments", []):
    att_id = att["id"]
    name = att["name"]
    ext = os.path.splitext(name)[1].lower()

    # Download
    os.system(f'python commbuys.py download {detail["bid_number"]} {att_id} -o "{name}"')

    # Process based on type
    if ext == ".pdf":
        text = extract_pdf_text(name)
        print(f"\n--- {name} ({len(text)} chars) ---")
        print(text[:500])
    elif ext == ".docx":
        result = extract_docx(name)
        print(f"\n--- {name} ({len(result['paragraphs'])} paragraphs) ---")
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(name)
        print(f"\n--- {name} ({len(df)} rows, {len(df.columns)} cols) ---")
        print(df.head())
```
