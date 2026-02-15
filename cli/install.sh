#!/bin/bash
# Install commbuys_cli globally

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/usr/local/bin"
MAN_DIR="/usr/local/share/man/man1"

# Check Python version
python3 -c "import sys; assert sys.version_info >= (3, 7), 'Python 3.7+ required'" 2>/dev/null || {
    echo "Error: Python 3.7+ is required"
    exit 1
}

echo "Installing commbuys CLI..."

# Install the script
sudo cp "$SCRIPT_DIR/commbuys.py" "$INSTALL_DIR/commbuys"
sudo chmod +x "$INSTALL_DIR/commbuys"

# Create man page
sudo mkdir -p "$MAN_DIR"
cat << 'MANEOF' | sudo tee "$MAN_DIR/commbuys.1" > /dev/null
.TH COMMBUYS 1 "2026" "commbuys_cli" "User Commands"
.SH NAME
commbuys \- query Massachusetts procurement data from COMMBUYS
.SH SYNOPSIS
.B commbuys
.I command
[options]
.SH DESCRIPTION
Command-line tool for querying Massachusetts state procurement data from the
COMMBUYS procurement portal (commbuys.com). Supports searching bids,
contracts (blankets), and vendors.
.SH COMMANDS
.TP
.B bids
Search bid solicitations
.TP
.B bid-detail \fIBID_ID\fR
Get detailed information for a specific bid
.TP
.B blankets
Search contracts / blanket purchase orders
.TP
.B vendors
Search registered vendors
.TP
.B info \fI[topic]\fR
Show information about COMMBUYS data and URLs
.SH OPTIONS
.TP
.B \-s, \-\-search TEXT
Search term
.TP
.B \-\-org NAME
Filter by organization name
.TP
.B \-\-open
Show only open bids (bids command only)
.TP
.B \-x, \-\-exclude TEXT
Exclude records matching term
.TP
.B \-n, \-\-limit N
Maximum records to return (default: 100)
.TP
.B \-f, \-\-format FORMAT
Output format: table, vertical, csv, json
.TP
.B \-o, \-\-output FILE
Save output to file
.TP
.B \-\-url
Show link to view in browser
.TP
.B \-\-save\-json
Save raw JSON with metadata
.SH EXAMPLES
.nf
commbuys bids --search "construction" --open
commbuys bid-detail BD-25-1020-DCRFS-DC367-116264
commbuys blankets --search "IT services"
commbuys vendors --search "Acme"
commbuys bids --search "software" --format csv -o results.csv
.fi
.SH DATA SOURCES
Data comes from the Massachusetts COMMBUYS procurement portal:
.br
Portal: https://www.commbuys.com
.br
Info: https://www.mass.gov/learn-about-commbuys-resources
.SH AUTHOR
Generated as a counterpart to cthru_cli
.SH LICENSE
MIT
MANEOF

sudo mandb -q 2>/dev/null || true

echo "Done! Run 'commbuys --help' to get started."
echo "View README with 'man commbuys'"
