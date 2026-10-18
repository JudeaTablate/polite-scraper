# The Polite Scraper — FlyRank Internship W5 / A9

A small Python scraping pipeline for the **Books to Scrape** practice sandbox. It discovers books from the first three catalogue pages, extracts product details, normalizes prices, validates records with Pydantic, caches downloaded HTML, and writes JSON outputs and a run report.

## Target classification (Stage 0)

- **Target:** https://books.toscrape.com/
- **Purpose:** educational scraping practice; Books to Scrape is a public sandbox designed for this activity.
- **Scope:** only the first three catalogue pages and the book pages linked from those pages (expected 60 unique books).
- **Fields:** title, product URL, original price text, numeric GBP price, availability, rating, description, source catalogue page, and fetch timestamp.
- **Robots check:** run `python src/main.py --check-robots` The request to https://books.toscrape.com/robots.txt returned HTTP 404 during my check on October 18, 2026. The robots.txt file was not found at that URL. A missing robots file is not permission by itself, so I also checked the site's description and confirmed that Books to Scrape is a practice sandbox before proceeding.
- **Scope promise:** I will not reuse this code on another site without checking its rules and terms first.

## Requirements

- Python 3.10+
- Free packages listed in `requirements.txt`

## Setup and run

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python src/main.py --check-robots
python src/main.py
```

If PowerShell blocks activation, you can run `.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.venv\Scripts\python.exe src/main.py` without activating the environment.

Run the scraper a second time with `python src/main.py`. Cached pages should print `CACHE HIT`; the program should not create duplicate records.

To test failure handling locally, run:

```powershell
python src/main.py --test-failure
```

This adds one intentionally nonexistent product URL. The run should finish, preserve valid books, and record the failed URL in `output/errors.json` and `output/run-report.json`. If the page is cached from a previous run, delete only that URL's corresponding cache file or use a fresh cache directory before testing.

## Outputs

- `output/books.json`: schema-validated records only.
- `output/errors.json`: failed/invalid pages and the reason.
- `output/run-report.json`: timestamps, duration, fetch/cache counts, valid/invalid counts, and failed-page count.
- `cache/`: local HTML cache; excluded from Git.

## Record schema

Each output record contains:

| Field | Type | Meaning |
|---|---|---|
| `title` | string | Book title |
| `product_url` | absolute HTTPS URL | Canonical identity for deduplication |
| `price_text` | string | Original text, e.g. `£51.77` |
| `price_gbp` | number | Normalized numeric price, e.g. `51.77` |
| `availability_text` | string | Availability shown on the product page |
| `rating_text` | string or `null` | Rating word, when present |
| `description` | string or `null` | Description, or null if absent |
| `source_page` | absolute HTTPS URL | Catalogue page from which the book was discovered |
| `fetched_at` | ISO-8601 string | UTC timestamp for the extracted record |

## Politeness and reliability

- Sends a clear User-Agent identifying this educational scraper.
- Uses a 10-second request timeout.
- Waits at least 500 ms between real requests in a run.
- Checks HTTP status codes and retries a timeout, connection error, or server error once.
- Does not retry HTTP 403 or 404.
- Caches successful HTML responses and reads cached HTML on reruns.
- Follows the site's `next` link and stops after three catalogue pages.
- Deduplicates by absolute product URL.
- Validates records before writing them to `books.json`; failed records go to `errors.json`.
- Does not use a browser because the required product information is already present in the HTML returned by the server.

## Ethics note

Use an official API when one exists. Never bypass logins, paywalls, access controls, or blocks. Collect only what is needed, identify your client honestly, respect the site's rules, and keep request rates low.

## Honest limitation

The scraper depends on the current HTML structure and CSS selectors. If the practice site changes its markup, selectors may need to be updated. The cache is local to this project and is not a shared production cache.

## Sample run evidence

Paste a real excerpt from your own `output/run-report.json` here after running the scraper. Do not invent counts or report results that have not been observed.

## Git commit plan

Use one meaningful commit per stage, for at least seven commits:

1. `Stage 0: classify scraping target`
2. `Stage 1: fetch and cache HTML`
3. `Stage 2: discover three catalogue pages`
4. `Stage 3: extract book details`
5. `Stage 4: validate normalized records`
6. `Stage 5: survive failures and report run`
7. `Stage 6: publish scraper evidence`

These should reflect actual incremental work; do not create fake commits after the fact merely to inflate the count.
