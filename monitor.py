import asyncio
import csv
import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin

from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

PRODUCT_URL = os.getenv("PRODUCT_URL", "https://books.toscrape.com/").strip()
REGION = os.getenv("REGION_LABEL", "not-set").strip()
LOCALE = os.getenv("BROWSER_LOCALE", "en-GB").strip()
BROWSER_TIMEZONE = os.getenv("BROWSER_TIMEZONE", "Europe/London").strip()
CURRENCY = os.getenv("CURRENCY_CODE", "GBP").strip().upper() or None
DELIVERY_COUNTRY = os.getenv("DELIVERY_COUNTRY", "").strip() or None
ACCOUNT_STATE = os.getenv("ACCOUNT_STATE", "signed_out").strip()
OUTPUT_DIR = BASE_DIR / "output"
JSON_PATH = OUTPUT_DIR / "snapshots.json"
CSV_PATH = OUTPUT_DIR / "snapshots.csv"

# These selectors are for Books to Scrape's catalogue cards only.
CARD_SELECTOR = "article.product_pod"
TITLE_SELECTOR = "h3 a"
PRICE_SELECTOR = ".price_color"
AVAILABILITY_SELECTOR = ".availability"

CSV_FIELDS = [
    "record_type", "checked_at", "status", "error",
    "product_name", "product_url", "region", "locale",
    "browser_timezone", "delivery_country", "account_state",
    "proxy_exit_ip", "price_text", "price_amount",
    "currency", "availability_text", "availability_status",
    "comparison",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_price(raw_text: str) -> str | None:
    """Parse a decimal amount from the demo site's GBP-style price text."""
    match = re.search(r"\d[\d,]*(?:\.\d{1,2})?", raw_text)
    if not match:
        return None
    try:
        return format(Decimal(match.group(0).replace(",", "")), ".2f")
    except InvalidOperation:
        return None


def normalize_availability(raw_text: str) -> str:
    value = raw_text.casefold()
    if "in stock" in value:
        return "in_stock"
    if "out of stock" in value:
        return "out_of_stock"
    return "unknown"


def load_records() -> list[dict]:
    if not JSON_PATH.exists():
        return []
    try:
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_records(records: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def compare_with_previous(records: list[dict], current: dict) -> str:
    if current.get("status") != "success" or not current.get("price_amount"):
        return "not_compared"

    dimensions = (
        "product_url", "region", "locale", "browser_timezone",
        "delivery_country", "account_state", "currency",
    )
    previous = next(
        (
            item for item in reversed(records)
            if item.get("record_type") == "product"
            and item.get("status") == "success"
            and item.get("price_amount") is not None
            and all(item.get(key) == current.get(key) for key in dimensions)
        ),
        None,
    )
    if previous is None:
        return "baseline"

    old_price = Decimal(str(previous["price_amount"]))
    new_price = Decimal(str(current["price_amount"]))
    if new_price < old_price:
        return "price_decreased"
    if new_price > old_price:
        return "price_increased"
    return "no_change"


def base_record(record_type: str, status: str, **extra) -> dict:
    record = {
        "record_type": record_type,
        "checked_at": utc_now(),
        "status": status,
        "error": None,
        "product_name": None,
        "product_url": None,
        "region": REGION,
        "locale": LOCALE,
        "browser_timezone": BROWSER_TIMEZONE,
        "delivery_country": DELIVERY_COUNTRY,
        "account_state": ACCOUNT_STATE,
        "proxy_exit_ip": None,
        "price_text": None,
        "price_amount": None,
        "currency": CURRENCY,
        "availability_text": None,
        "availability_status": "unknown",
        "comparison": "not_compared",
    }
    record.update(extra)
    return record


async def main() -> None:
    if not PRODUCT_URL:
        raise ValueError("PRODUCT_URL must be set.")

    proxy_server = os.getenv("PROXY_SERVER", "").strip()
    proxy_username = os.getenv("PROXY_USERNAME", "").strip()
    proxy_password = os.getenv("PROXY_PASSWORD", "").strip()

    if bool(proxy_username) != bool(proxy_password):
        raise ValueError("Set both PROXY_USERNAME and PROXY_PASSWORD, or neither.")
    if (proxy_username or proxy_password) and not proxy_server:
        raise ValueError("Set PROXY_SERVER when proxy credentials are provided.")

    proxy = None
    if proxy_server:
        proxy = {"server": proxy_server}
        if proxy_username:
            proxy["username"] = proxy_username
            proxy["password"] = proxy_password

    records = load_records()
    run_record = base_record("run", "started")
    new_records = [run_record]

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(proxy=proxy)
        try:
            context = await browser.new_context(
                locale=LOCALE,
                timezone_id=BROWSER_TIMEZONE,
            )
            page = await context.new_page()
            exit_ip = None

            if proxy:
                try:
                    ip_response = await page.goto(
                        "https://api.ipify.org?format=json",
                        wait_until="domcontentloaded",
                        timeout=30_000,
                    )
                    if ip_response and ip_response.ok:
                        ip_data = json.loads(await page.locator("body").inner_text())
                        exit_ip = ip_data.get("ip")
                except Exception as exc:
                    # An IP-check failure is recorded but does not silently imply
                    # that the target site's request will also fail.
                    new_records.append(
                        base_record(
                            "diagnostic", "failed",
                            error=f"Proxy exit-IP check failed: {type(exc).__name__}: {exc}",
                        )
                    )

            try:
                response = await page.goto(
                    PRODUCT_URL,
                    wait_until="domcontentloaded",
                    timeout=45_000,
                )
                if response and response.status >= 400:
                    raise RuntimeError(f"Target returned HTTP {response.status}")

                body_text = (await page.locator("body").inner_text()).casefold()
                challenge_markers = (
                    "verify you are human",
                    "unusual traffic",
                    "captcha",
                    "access denied",
                    "automated requests",
                )
                if any(marker in body_text for marker in challenge_markers):
                    raise RuntimeError(
                        "Challenge or access-restriction page detected; "
                        "the monitor stopped without retrying or rotating IPs."
                    )

                cards = page.locator(CARD_SELECTOR)
                await cards.first.wait_for(state="visible", timeout=15_000)
                count = await cards.count()

                for index in range(count):
                    card = cards.nth(index)
                    try:
                        title_link = card.locator(TITLE_SELECTOR)
                        title = (await title_link.get_attribute("title")) or (
                            await title_link.inner_text()
                        ).strip()
                        href = await title_link.get_attribute("href")
                        product_url = urljoin(PRODUCT_URL, href or "")

                        price_text = (await card.locator(PRICE_SELECTOR).inner_text()).strip()
                        price_amount = parse_price(price_text)
                        availability_text = (
                            await card.locator(AVAILABILITY_SELECTOR).inner_text()
                        ).strip()

                        if price_amount is None:
                            item = base_record(
                                "product", "extraction_failed",
                                error="Price text was present but could not be parsed.",
                                product_name=title,
                                product_url=product_url,
                                proxy_exit_ip=exit_ip,
                                price_text=price_text,
                                availability_text=availability_text,
                                availability_status=normalize_availability(availability_text),
                            )
                        else:
                            item = base_record(
                                "product", "success",
                                product_name=title,
                                product_url=product_url,
                                proxy_exit_ip=exit_ip,
                                price_text=price_text,
                                price_amount=price_amount,
                                availability_text=availability_text,
                                availability_status=normalize_availability(availability_text),
                            )
                            item["comparison"] = compare_with_previous(records + new_records, item)

                        new_records.append(item)
                    except Exception as exc:
                        new_records.append(
                            base_record(
                                "product", "extraction_failed",
                                error=f"{type(exc).__name__}: {exc}",
                                proxy_exit_ip=exit_ip,
                            )
                        )

                run_record["status"] = "success"
                run_record["error"] = None
                run_record["products_seen"] = count

            except (PlaywrightTimeoutError, Exception) as exc:
                run_record["status"] = "check_failed"
                run_record["error"] = f"{type(exc).__name__}: {exc}"
                run_record["products_seen"] = 0

            finally:
                await context.close()
        finally:
            await browser.close()

    records.extend(new_records)
    save_records(records)

    print(f"Run status: {run_record['status']}")
    print(f"Records written: {len(new_records) - 1} product/diagnostic records")
    print(f"JSON: {JSON_PATH}")
    print(f"CSV:  {CSV_PATH}")
    if run_record["error"]:
        print(f"Error: {run_record['error']}")


if __name__ == "__main__":
    asyncio.run(main())
