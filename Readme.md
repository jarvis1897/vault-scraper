# Vault Network — Affiliate Dashboard Scraper

Scrapes affiliate performance data from a QuickSight dashboard and writes it to `output.json`.

## Requirements

- Python 3.8 or higher
- pip

## Installation

Install the Playwright Python package:

```bash
pip install playwright
```

Then install the Chromium browser that Playwright uses to automate the scrape:

```bash
playwright install chromium
```

## Running the script

```bash
python scraper.py
```

The script will log in to the dashboard, dismiss any welcome modals, and scroll through the full table. When finished, `output.json` is written to the current directory.

## Output format

```json
[
  {
    "date": "2024-12-01",
    "code": "AFF001",
    "registrations": 14,
    "ftds": 1,
    "state": "AL"
  }
]
```

## Approach

The dashboard is a JavaScript-rendered QuickSight table. A few things I had to work through:

- **No SDK access** — the credentials provided are reader-level web credentials, not IAM keys, so the boto3 QuickSight SDK wasn't an option. Browser automation was the only path.
- **No `<table>` element** — QuickSight renders its table as absolutely-positioned `div` elements. Each cell is a `div.cell` with `data-row-path`, `data-col-path`, and a `title` attribute holding the value.
- **Virtualized rendering** — only the rows currently visible in the viewport exist in the DOM. Scrolling `.grid-container` (the element with `overflow-y: auto`) incrementally forces the virtualizer to render new rows.
- **`overflow-y: hidden` trap** — `.fixed-grid-wrapper` accepts `scrollTop` writes but doesn't trigger re-rendering because its overflow is hidden. `.grid-container` is the correct scroll target.
- **Welcome modal** — a promo modal appears after login and blocks the dashboard. It's dismissed via `[data-automation-id="welcome-modal-close-btn"]`.
- **`state="attached"` vs `state="visible"`** — Playwright's default `wait_for_selector` waits for visibility, but the table sits behind hidden overflow ancestors and never becomes "visible" in Playwright's sense. `state="attached"` waits for DOM presence instead.
