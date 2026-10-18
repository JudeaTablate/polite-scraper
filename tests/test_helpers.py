"""Small offline tests for price normalization and schema validation."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from main import BookRecord, PoliteScraper  # noqa: E402


class ScraperHelperTests(unittest.TestCase):
    def test_price_normalization(self):
        self.assertEqual(PoliteScraper._price_number("£51.77"), 51.77)

    def test_missing_description_can_be_null(self):
        record = BookRecord(
            title="Example Book",
            product_url="https://books.toscrape.com/catalogue/example/index.html",
            price_text="£10.00",
            price_gbp=10.0,
            availability_text="In stock",
            rating_text=None,
            description=None,
            source_page="https://books.toscrape.com/catalogue/page-1.html",
            fetched_at="2026-10-18T00:00:00Z",
        )
        self.assertIsNone(record.description)

    def test_rejects_non_https_product_url(self):
        with self.assertRaises(ValueError):
            BookRecord(
                title="Example Book",
                product_url="http://example.com/book",
                price_text="£10.00",
                price_gbp=10.0,
                availability_text="In stock",
                rating_text=None,
                description=None,
                source_page="https://books.toscrape.com/catalogue/page-1.html",
                fetched_at="2026-10-18T00:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
