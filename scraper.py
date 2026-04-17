import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Configuration 

DASHBOARD_URL = (
    "https://us-east-1.quicksight.aws.amazon.com/sn/account/"
    "vault-network-inteview/dashboards/"
    "3b1cdcb4-3d00-4612-9ff3-4940982b2e99"
)
USERNAME = "candidate@vaultsportshq.com"
PASSWORD = "Vault!nterview1"
OUTPUT_FILE = "output.json"

# Columns: 0=code, 1=date, 2=state, 3=ftds, 4=registrations
NUM_COLS = 5

# Scroll tuning for scraping table data
SCROLL_STEP = 150  
SETTLE_TIME = 1.0  
MAX_STALE = 10   

# Login 

async def login(page):
    # two-step QuickSight login.
    print("Navigating to dashboard...")
    await page.goto(DASHBOARD_URL, timeout=30000)

    try:
        await page.wait_for_selector("#username-input", timeout=20000)
    except PlaywrightTimeoutError:
        raise RuntimeError(
            "Login form did not appear, check the dashboard URL."
        )

    await page.fill("#username-input", USERNAME)
    await page.click("#username-submit-button")

    try:
        await page.wait_for_selector("#password-input input", timeout=15000)
    except PlaywrightTimeoutError:
        raise RuntimeError(
            "Password field did not appear, check the username."
        )

    await page.fill("#password-input input", PASSWORD)

    submit = (
        await page.query_selector("#password-submit-button")
        or await page.query_selector('button[type="submit"]')
    )
    if not submit:
        raise RuntimeError("Could not find the login submit button.")

    await submit.click()
    print("Login submitted")

# Modal

async def dismiss_welcome_modal(page):
    # Close the AWS welcome if it appears after login.
    try:
        btn = await page.wait_for_selector(
            '[data-automation-id="welcome-modal-close-btn"]', timeout=10000
        )
        await btn.click()
        print("Dismissed welcome modal")
    except PlaywrightTimeoutError:
        pass  

# Table detection

async def wait_for_table(page):
    # Wait until the QuickSight table and its first data cells are in the DOM.
    print("Waiting for table to render...")
    try:
        await page.wait_for_selector(".sn-table", state="attached", timeout=30000)
        await page.wait_for_selector(
            ".cell[data-row-path][data-col-path]", state="attached", timeout=30000
        )
    except PlaywrightTimeoutError:
        raise RuntimeError(
            "Table did not render within 30s. "
            "Login may have failed, or the dashboard selectors have changed."
        )
    print("Table found")

# Extraction 

async def extract_all_rows(page):
    # Scroll through the virtualized QuickSight grid and collect data.
    rows = {}
    stale_count = 0
    scroll_pos = 0

    max_scroll = await page.evaluate("""
        () => {
            const c = document.querySelector('.grid-container');
            return c ? c.scrollHeight - c.clientHeight : 0;
        }
    """)
    if max_scroll <= 0:
        raise RuntimeError(
            "Could not determine grid scroll height. "
            "The .grid-container element may be missing."
        )

    print("Extracting rows...")

    while stale_count < MAX_STALE:
        cells = await page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('.cell[data-row-path][data-col-path]').forEach(el => {
                    results.push({
                        row: parseInt(el.getAttribute('data-row-path'), 10),
                        col: parseInt(el.getAttribute('data-col-path'), 10),
                        val: el.getAttribute('title') || '',
                    });
                });
                return results;
            }
        """)

        before = len(rows)
        for cell in cells:
            r, c, v = cell["row"], cell["col"], cell["val"]
            if r not in rows:
                rows[r] = {}
            rows[r][c] = v

        gained = len(rows) - before
        if gained > 0:
            stale_count = 0
        else:
            stale_count += 1

        if scroll_pos >= max_scroll:
            print("Reached end of grid")
            break

        scroll_pos = min(scroll_pos + SCROLL_STEP, max_scroll)
        await page.evaluate(f"() => {{ document.querySelector('.grid-container').scrollTop = {scroll_pos}; }}")
        await asyncio.sleep(SETTLE_TIME)

    if stale_count >= MAX_STALE:
        print(f"Stopped after {MAX_STALE} scrolls with no new rows")

    print(f"Done — {len(rows)} unique rows collected")
    return rows


# Post-processing

def parse_date(raw):
    """Normalize QuickSight display dates (e.g. 'Dec 1, 2024') to YYYY-MM-DD."""
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {raw!r}")


def build_output(raw_rows):
    # Convert raw row dict into the required output format.
    output = []
    skipped = 0

    for row_idx in sorted(raw_rows.keys()):
        row = raw_rows[row_idx]

        if not all(c in row for c in range(NUM_COLS)):
            skipped += 1
            continue

        try:
            output.append({
                "date":          parse_date(row[1]),
                "code":          row[0],
                "registrations": int(row[4]),
                "ftds":          int(row[3]),
                "state":         row[2],
            })
        except (ValueError, KeyError) as e:
            print(f"Skipping row {row_idx}: {e}")
            skipped += 1

    if skipped:
        print(f"{skipped} rows were skipped due to missing or unparseable data")

    return output

# Main 

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await login(page)
            await dismiss_welcome_modal(page)
            await wait_for_table(page)
            raw_rows = await extract_all_rows(page)
        except RuntimeError as e:
            print(f"\n{e}")
            raise
        finally:
            await browser.close()

    if not raw_rows:
        raise RuntimeError("No rows were extracted. Check login credentials and dashboard URL.")

    output = build_output(raw_rows)

    if not output:
        raise RuntimeError("All rows were skipped during post-processing. Check the table structure.")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{len(output)} rows written to {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())