# KindProxy Playwright Price Monitor

A lightweight Python demo that uses [Playwright](https://playwright.dev/python/) to collect product names, displayed prices, and availability from a practice catalogue. It can optionally route browser traffic through a residential proxy and save timestamped snapshots as JSON and CSV.

This repository accompanies the KindProxy tutorial:

**[E-commerce Price Monitoring with Playwright and Residential Proxies](https://www.kindproxy.com/blog/en/blog/ecommerce-price-monitoring-playwright-residential-proxies-2026/)**

> **Important scope note:** The example uses [Books to Scrape](https://books.toscrape.com/), a practice website with randomly assigned prices. It demonstrates a monitoring workflow; it does not demonstrate real regional price differences or production-grade e-commerce monitoring.

## Features

- Launch Chromium with Playwright.
- Optional HTTP proxy configuration with username/password authentication.
- Record the observed proxy exit IP (when proxy mode is enabled).
- Capture product name, URL, displayed price, and availability.
- Preserve raw price text and parse a numeric amount.
- Save run-level status and product-level extraction status.
- Write historical snapshots to JSON and CSV.
- Compare successful observations only when the product and configured test context match.
- Stop and record a failed check when a challenge/access-restriction page is detected; the script does not attempt to bypass it.

## Demo screenshots

### Terminal run

![Successful terminal run showing 20 product records written](https://cdn.kindproxy.com/blog_images/price_run.png)

### JSON snapshot

![JSON snapshot containing product details, price, currency, availability, and proxy exit IP](https://cdn.kindproxy.com/blog_images/price_json.png)

### CSV history and comparison

![CSV spreadsheet showing baseline records from the first run and no_change records from the second run](https://cdn.kindproxy.com/blog_images/price_csv.png)

## Requirements

- Python 3.10+
- Playwright
- Chromium
- Optional: a proxy endpoint and credentials

## Installation

Clone the repository:

```bash
git clone https://github.com/KindProxy/kindproxy-playwright-price-monitor.git
cd kindproxy-playwright-price-monitor
```

Create and activate a virtual environment.

**Linux / macOS**

```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install Python dependencies and Chromium:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

On Linux, if Playwright reports missing system libraries:

```bash
python -m playwright install-deps chromium
```

## Configuration

Copy the example environment file:

**Linux / macOS**

```bash
cp .env.example .env
```

**Windows CMD**

```cmd
copy .env.example .env
```

**Windows PowerShell**

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```env
# Optional proxy settings. Leave blank for a direct practice run.
PROXY_SERVER=http://gw.kindproxy.com:12000
PROXY_USERNAME=your_dashboard_username
PROXY_PASSWORD=your_dashboard_password

PRODUCT_URL=https://books.toscrape.com/
REGION_LABEL=UK
BROWSER_LOCALE=en-GB
BROWSER_TIMEZONE=Europe/London
CURRENCY_CODE=GBP
DELIVERY_COUNTRY=
ACCOUNT_STATE=signed_out
```

Use the proxy endpoint and credentials supplied in your account. Copy the generated username and password exactly. Do not manually append another provider's session or location parameters.

For a direct run without a proxy, leave `PROXY_SERVER`, `PROXY_USERNAME`, and `PROXY_PASSWORD` empty.

**Keep `.env` private.** It contains credentials and is excluded from Git by `.gitignore`. Never commit real proxy credentials, customer data, or private logs.

### What the region settings mean

- `REGION_LABEL` is a label attached to the test record; it does not verify the proxy's country.
- `BROWSER_LOCALE` sets the browser locale.
- `BROWSER_TIMEZONE` sets the browser time zone.
- `CURRENCY_CODE` is the configured currency code recorded with the observation. The script does not detect currency from the page.
- `DELIVERY_COUNTRY` is metadata only. This demo does not enter a delivery address on the website.
- `ACCOUNT_STATE` is a descriptive label; this demo does not sign in to a store.

A proxy exit country, browser locale, time zone, currency, delivery destination, and account state are separate variables. Do not assume that changing one automatically changes the others.

## Usage

Run:

```bash
python monitor.py
```

The script writes:

```text
output/
├── snapshots.json
└── snapshots.csv
```

The first successful observation for a product/context is marked `baseline`. A later successful observation with the same comparison dimensions can be marked `no_change`, `price_increased`, or `price_decreased`.

A missing or unparseable price is not converted to zero. Failed navigation or a detected challenge is recorded as a failed run rather than a valid price observation.

## Output fields

| Field | Description |
|---|---|
| `checked_at` | UTC timestamp |
| `status` | Run or extraction result |
| `product_name` / `product_url` | Product identity |
| `region` | User-defined test label |
| `locale` / `browser_timezone` | Browser context |
| `delivery_country` | Optional configured metadata |
| `account_state` | User-defined account-state label |
| `proxy_exit_ip` | Exit IP observed through the optional proxy |
| `price_text` | Raw displayed price text |
| `price_amount` | Parsed numeric amount |
| `currency` | Configured currency code, not auto-detected |
| `availability_text` | Raw availability wording |
| `availability_status` | Normalized availability |
| `comparison` | Historical comparison result |

## Customizing for another website

The CSS selectors in `monitor.py` are specific to the Books to Scrape catalogue:

```python
CARD_SELECTOR = "article.product_pod"
TITLE_SELECTOR = "h3 a"
PRICE_SELECTOR = ".price_color"
AVAILABILITY_SELECTOR = ".availability"
```

For another website:

1. Confirm that you are authorized to access and monitor the page.
2. Inspect the page markup and update the selectors.
3. Adapt `parse_price()` to the site's number format.
4. Confirm the currency from reliable page data or site metadata rather than guessing from a symbol.
5. Validate the availability wording and update `normalize_availability()` if needed.
6. Keep comparison dimensions consistent between observations.

This repository is a single-run example. It does not implement multi-country scheduling, delivery-address automation, account login, database storage, alerting, or a production job queue.

## Proxy configuration

Playwright supports proxy configuration at browser launch. This demo passes the proxy server and optional credentials to Chromium.

KindProxy setup guide:

[How to Use Residential Proxies with Playwright](https://www.kindproxy.com/blog/en/blog/how-to-use-residential-proxies-with-playwright-2026/)

Official Playwright documentation:

[Playwright Python: Network](https://playwright.dev/python/docs/network)

A residential proxy changes the network route; it does not guarantee access, prevent CAPTCHA pages, or set the storefront's delivery country or currency.

## Responsible use

- Prefer an official API or data feed when it provides the information you need.
- Follow the target website's terms, access policies, and applicable laws.
- Use conservative request rates.
- Do not automate CAPTCHA solving or repeatedly rotate IPs to evade access restrictions.
- Stop and record a failed check when the site returns a challenge or access-denied page.
- Do not publish credentials, private customer information, or sensitive logs.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
