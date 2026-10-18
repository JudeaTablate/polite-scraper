from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

BASE_URL = "https://books.toscrape.com/"
FIRST_CATALOGUE = urljoin(BASE_URL, "catalogue/page-1.html")
USER_AGENT = "FlyRankInternship-A9/1.0 (educational scraper; https://github.com/YOUR_GITHUB_USERNAME/polite-scraper)"
REQUEST_TIMEOUT = 10
POLITE_DELAY_SECONDS = 0.5

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_DIR = ROOT / "output"


class BookRecord(BaseModel):
    """Normalized, validated record stored in books.json."""
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    product_url: str = Field(min_length=1)
    price_text: str = Field(min_length=1)
    price_gbp: float = Field(ge=0)
    availability_text: str = Field(min_length=1)
    rating_text: str | None
    description: str | None
    source_page: str = Field(min_length=1)
    fetched_at: str = Field(min_length=1)

    @field_validator("product_url", "source_page")
    @classmethod
    def must_be_https_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("URL must be an absolute HTTPS URL")
        return value

    @field_validator("fetched_at")
    @classmethod
    def must_be_iso_datetime(cls, value: str) -> str:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class PoliteScraper:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.last_request_at = 0.0
        self.pages_fetched = 0
        self.cache_hits = 0
        self.failed_pages = 0
        self.fetch_errors: list[dict[str, Any]] = []

    @staticmethod
    def _cache_path(url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        return CACHE_DIR / f"{digest}.html"

    def fetch_html(self, url: str, *, retry_once: bool = True) -> tuple[str, str]:
        """Return (HTML, source) where source is FETCH or CACHE HIT."""
        cache_path = self._cache_path(url)
        if cache_path.exists():
            self.cache_hits += 1
            return cache_path.read_text(encoding="utf-8"), "CACHE HIT"

        attempts = 2 if retry_once else 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            wait_for = POLITE_DELAY_SECONDS - (time.monotonic() - self.last_request_at)
            if self.last_request_at and wait_for > 0:
                time.sleep(wait_for)

            try:
                response = self.session.get(url, timeout=REQUEST_TIMEOUT)
                self.last_request_at = time.monotonic()
                self.pages_fetched += 1

                if response.status_code == 200:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(response.text, encoding="utf-8")
                    return response.text, "FETCH"

                # Do not retry forbidden or missing pages. Retry once only for server errors.
                if response.status_code in (403, 404):
                    raise requests.HTTPError(
                        f"HTTP {response.status_code}; not retrying this status",
                        response=response,
                    )
                if 500 <= response.status_code <= 599 and attempt + 1 < attempts:
                    time.sleep(1)
                    continue
                response.raise_for_status()
                raise requests.HTTPError(f"Unexpected HTTP status {response.status_code}")

            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(1)
                    continue
                break
            except requests.HTTPError as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status and 500 <= status <= 599 and attempt + 1 < attempts:
                    time.sleep(1)
                    continue
                break

        raise RuntimeError(f"Could not fetch {url}: {last_error}")

    def check_robots(self) -> dict[str, Any]:
        """Fetch robots.txt once on request and report its outcome."""
        robots_url = urljoin(BASE_URL, "robots.txt")
        try:
            response = self.session.get(robots_url, timeout=REQUEST_TIMEOUT)
            self.last_request_at = time.monotonic()
            result = {
                "url": robots_url,
                "status_code": response.status_code,
                "result": "robots.txt retrieved" if response.status_code == 200
                          else f"robots.txt returned HTTP {response.status_code}",
                "note": "A missing robots file is not permission by itself.",
            }
            print(json.dumps(result, indent=2))
            return result
        except requests.RequestException as exc:
            result = {
                "url": robots_url,
                "result": "request failed",
                "detail": str(exc),
                "note": "A missing or unreachable robots file is not permission by itself.",
            }
            print(json.dumps(result, indent=2))
            return result

    @staticmethod
    def soup(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    def discover_books(self) -> list[dict[str, str]]:
        """Follow the site's own next links, stopping after three catalogue pages."""
        current_url = FIRST_CATALOGUE
        discovered: list[dict[str, str]] = []
        seen_catalogues: set[str] = set()

        for page_number in range(1, 4):
            if current_url in seen_catalogues:
                break
            seen_catalogues.add(current_url)

            html, source = self.fetch_html(current_url)
            print(f"{source}: catalogue page {page_number} ({len(html)} bytes)")
            soup = self.soup(html)

            for article in soup.select("article.product_pod"):
                link = article.select_one("h3 a")
                if not link or not link.get("href"):
                    continue
                product_url = urljoin(current_url, link["href"])
                discovered.append({
                    "product_url": product_url,
                    "source_page": current_url,
                })

            next_link = soup.select_one("li.next a")
            if page_number < 3 and next_link and next_link.get("href"):
                current_url = urljoin(current_url, next_link["href"])
            else:
                break

        # Canonical URL is the identity; preserve first occurrence and its source page.
        unique: dict[str, dict[str, str]] = {}
        for item in discovered:
            unique.setdefault(item["product_url"], item)
        print(f"catalogue_pages={len(seen_catalogues)} discovered={len(discovered)} unique_urls={len(unique)}")
        return list(unique.values())

    @staticmethod
    def _description(soup: BeautifulSoup) -> str | None:
        heading = soup.find(id="product_description")
        if not heading:
            return None
        paragraph = heading.find_next("p")
        if not paragraph:
            return None
        text = paragraph.get_text(" ", strip=True)
        return text or None

    @staticmethod
    def _rating_text(soup: BeautifulSoup) -> str | None:
        rating = soup.select_one("p.star-rating")
        if not rating:
            return None
        classes = rating.get("class", [])
        for word in ("One", "Two", "Three", "Four", "Five"):
            if word in classes:
                return word
        return None

    @staticmethod
    def _price_number(price_text: str) -> float:
        cleaned = re.sub(r"[^\d.,]", "", price_text).replace(",", "")
        try:
            value = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"Could not parse price from {price_text!r}") from exc
        if value < 0:
            raise ValueError("Price cannot be negative")
        return float(value)

    def extract_record(self, item: dict[str, str]) -> dict[str, Any]:
        product_url = item["product_url"]
        html, source = self.fetch_html(product_url)
        print(f"{source}: book page {product_url} ({len(html)} bytes)")
        soup = self.soup(html)

        product_area = soup.select_one("article.product_page")
        if product_area is None:
            raise ValueError("Could not find article.product_page")

        title_node = product_area.select_one("div.product_main h1")
        price_node = product_area.select_one("p.price_color")
        availability_node = product_area.select_one("p.instock.availability")

        if title_node is None:
            raise ValueError("Missing product title")
        if price_node is None:
            raise ValueError("Missing product price")
        if availability_node is None:
            raise ValueError("Missing availability")

        price_text = price_node.get_text(" ", strip=True)
        raw = {
            "title": title_node.get_text(" ", strip=True),
            "product_url": product_url,
            "price_text": price_text,
            "price_gbp": self._price_number(price_text),
            "availability_text": availability_node.get_text(" ", strip=True),
            "rating_text": self._rating_text(product_area),
            "description": self._description(soup),
            "source_page": item["source_page"],
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        return raw

    def run(self, inject_bad_url: bool = False) -> dict[str, Any]:
        started_at = datetime.now(timezone.utc)
        start_clock = time.monotonic()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        valid_records: dict[str, dict[str, Any]] = {}
        invalid_records: list[dict[str, Any]] = []

        try:
            books = self.discover_books()
        except Exception as exc:
            books = []
            self.fetch_errors.append({"url": FIRST_CATALOGUE, "reason": str(exc)})

        if inject_bad_url:
            books.append({
                "product_url": urljoin(BASE_URL, "catalogue/this-book-does-not-exist-999999/index.html"),
                "source_page": FIRST_CATALOGUE,
            })

        for item in books:
            url = item["product_url"]
            try:
                raw_record = self.extract_record(item)
                record = BookRecord.model_validate(raw_record)
                # URL is the canonical identity, so reruns and duplicate links cannot duplicate records.
                valid_records[record.product_url] = record.model_dump()
            except (Exception, ValidationError) as exc:
                self.failed_pages += 1
                invalid_records.append({
                    "product_url": url,
                    "reason": str(exc),
                    "source_page": item.get("source_page"),
                })
                print(f"SKIP: {url} — {exc}", file=sys.stderr)

        books_path = OUTPUT_DIR / "books.json"
        errors_path = OUTPUT_DIR / "errors.json"
        report_path = OUTPUT_DIR / "run-report.json"

        # Deterministic ordering makes reruns easy to compare.
        records = sorted(valid_records.values(), key=lambda row: row["product_url"])
        books_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        errors_path.write_text(json.dumps(invalid_records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        finished_at = datetime.now(timezone.utc)
        report = {
            "started_at": started_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "finished_at": finished_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "duration_seconds": round(time.monotonic() - start_clock, 2),
            "catalogue_pages_target": 3,
            "discovered_unique_urls": len({x["product_url"] for x in books if x["product_url"] != urljoin(BASE_URL, "catalogue/this-book-does-not-exist-999999/index.html")}),
            "pages_fetched": self.pages_fetched,
            "cache_hits": self.cache_hits,
            "valid_records": len(records),
            "invalid_records": len(invalid_records),
            "failed_pages": len(invalid_records),
            "outputs": {
                "books": "output/books.json",
                "errors": "output/errors.json",
                "report": "output/run-report.json",
            },
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("\nRun summary")
        print(json.dumps(report, indent=2))
        print(f"\nSaved {len(records)} valid records to {books_path}")
        print(f"Saved {len(invalid_records)} errors to {errors_path}")
        print(f"Saved run report to {report_path}")
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Polite Books to Scrape practice scraper")
    parser.add_argument("--check-robots", action="store_true", help="request robots.txt and print the result")
    parser.add_argument("--test-failure", action="store_true", help="add one deliberately broken URL to test failure handling")
    args = parser.parse_args()

    scraper = PoliteScraper()
    if args.check_robots:
        scraper.check_robots()
        return
    scraper.run(inject_bad_url=args.test_failure)


if __name__ == "__main__":
    main()
