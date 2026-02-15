# COMMBUYS CLI — Quick Reference

Full docs: `~/.claude/skills/commbuys/SKILL.md`

## Commands

| Command | Example |
|---------|---------|
| `bids` | `python commbuys.py bids --search "construction" --open` |
| `bid-detail` | `python commbuys.py bid-detail BD-25-1020-DCRFS-DC367-116264` |
| `blankets` | `python commbuys.py blankets --vendor "Blue Tactical"` |
| `vendors` | `python commbuys.py vendors --search "Staples"` |
| `po-detail` | `python commbuys.py po-detail PO-25-1080-OSD03-OSD03-36026` |
| `download` | `python commbuys.py download BD-25-... 2095248 -o file.docx` |
| `info` | `python commbuys.py info urls` |

## Common Options

`-f json|csv|table|vertical` / `-o FILE` / `--save-json` / `--org TEXT` / `-n LIMIT` / `--open`

## Notes

- Python stdlib only (no pip deps for CLI)
- Analysis: `pip install pandas pdfplumber python-docx openpyxl`
- No API — uses PrimeFaces AJAX against commbuys.com
- Related: CTHru (spending), federal-procurement (FPDS/USAspending)
