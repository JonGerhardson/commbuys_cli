# COMMBUYS Data Analysis Patterns

## Loading COMMBUYS JSON Exports

The CLI's `--save-json` flag produces files with this structure:

```python
import json
import pandas as pd

with open("bids_construction_20250213_143022.json") as f:
    export = json.load(f)

# Metadata
print(export["portal_url"])       # https://www.commbuys.com/bso/
print(export["query_timestamp"])  # ISO timestamp
print(export["record_count"])     # number of records

# Data
df = pd.DataFrame(export["data"])
```

## Bid Analysis

### Filter by Status and Date

```python
# Parse dates
df["open_date"] = pd.to_datetime(df["open_date"], errors="coerce")

# Open bids only
open_bids = df[df["status"] == "Open"]

# Bids opened in the last 30 days
recent = df[df["open_date"] >= pd.Timestamp.now() - pd.Timedelta(days=30)]
```

### Bids by Organization

```python
by_org = df.groupby("organization").size().sort_values(ascending=False)
print(by_org.head(20))

# Top organizations with open bids
open_by_org = open_bids.groupby("organization").size().sort_values(ascending=False)
```

### Bid Volume Over Time

```python
df["month"] = df["open_date"].dt.to_period("M")
monthly = df.groupby("month").size()

# Plot
monthly.plot(kind="bar", title="Bids by Month", figsize=(12, 5))
```

### Search Within Results

```python
# Find bids mentioning specific terms
it_bids = df[df["description"].str.contains("software|IT|technology", case=False, na=False)]
```

## Contract (Blanket) Analysis

### Dollar Amounts

```python
# Clean amount strings
df["amount_clean"] = (
    df["amount"]
    .str.replace(r"[$,]", "", regex=True)
    .astype(float, errors="ignore")
)

# Top contracts by value
top = df.nlargest(20, "amount_clean")[["contract_number", "vendor", "amount", "description"]]

# Total by vendor
vendor_totals = df.groupby("vendor")["amount_clean"].sum().sort_values(ascending=False)
```

### Vendor Concentration

```python
# How many contracts per vendor
vendor_counts = df.groupby("vendor").size().sort_values(ascending=False)
print(f"Unique vendors: {df['vendor'].nunique()}")
print(f"Top 10 vendors hold: {vendor_counts.head(10).sum()} / {len(df)} contracts")
```

### Contract Expiration Tracking

```python
df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")

# Expiring in next 90 days
soon = df[
    (df["end_date"] >= pd.Timestamp.now()) &
    (df["end_date"] <= pd.Timestamp.now() + pd.Timedelta(days=90))
]
print(f"{len(soon)} contracts expiring in next 90 days")
```

### Contract Types

```python
type_dist = df["type"].value_counts()
print(type_dist)
```

## Vendor Analysis

### Geographic Distribution

```python
by_state = df.groupby("state").size().sort_values(ascending=False)
by_city = df[df["state"] == "MA"].groupby("city").size().sort_values(ascending=False)
```

### Vendor Participation

```python
# Vendors with contact info
has_contact = df[df["contact"].notna() & (df["contact"] != "")]
print(f"Vendors with contacts: {len(has_contact)} / {len(df)}")
```

## Cross-Source Joins (COMMBUYS + CTHru)

COMMBUYS shows procurement; CTHru shows spending. Join them for a complete picture.

### Match Vendors Across Systems

```python
# Load both datasets
commbuys_df = pd.DataFrame(commbuys_export["data"])
cthru_df = pd.read_json("cthru_vendor_payments.json")

# Fuzzy match on vendor name (exact match rarely works)
from difflib import get_close_matches

def find_cthru_vendor(commbuys_name, cthru_names, cutoff=0.7):
    matches = get_close_matches(commbuys_name, cthru_names, n=1, cutoff=cutoff)
    return matches[0] if matches else None

commbuys_df["cthru_vendor"] = commbuys_df["vendor"].apply(
    lambda x: find_cthru_vendor(x, cthru_df["vendor_name"].tolist())
)

# Join
merged = commbuys_df.merge(
    cthru_df, left_on="cthru_vendor", right_on="vendor_name", how="inner"
)
```

### Contract Value vs. Actual Spending

```python
# Compare awarded contract amounts to actual CTHru payments
comparison = merged.groupby("vendor").agg({
    "amount_clean": "sum",        # COMMBUYS contract value
    "payment_amount": "sum",      # CTHru actual payments
}).rename(columns={
    "amount_clean": "contract_value",
    "payment_amount": "actual_spend",
})
comparison["utilization"] = comparison["actual_spend"] / comparison["contract_value"]
print(comparison.sort_values("actual_spend", ascending=False).head(20))
```

## Exporting Analysis Results

```python
# To CSV
df.to_csv("analysis_results.csv", index=False)

# To Excel with multiple sheets
with pd.ExcelWriter("commbuys_analysis.xlsx") as writer:
    df.to_excel(writer, sheet_name="All Bids", index=False)
    by_org.to_excel(writer, sheet_name="By Organization")
    open_bids.to_excel(writer, sheet_name="Open Bids", index=False)

# To JSON (for further processing)
df.to_json("analysis.json", orient="records", indent=2)
```
