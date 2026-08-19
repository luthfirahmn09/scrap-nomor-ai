# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Telegram bot scraping Google Maps for business contacts (phone, email). Results sent as Excel file.

**Stack:** Python 3.11+, python-telegram-bot v20 (async), Playwright, openpyxl

## Setup & Run

```bash
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# edit .env → set TELEGRAM_TOKEN

python bot.py
```

## Architecture

```
bot.py          Telegram handlers + /start, /search, inline button flow
scraper.py      Playwright async → Google Maps search → extract name/phone/website
exporter.py     Build .xlsx from results list, return BytesIO
config.py       Load .env vars (TELEGRAM_TOKEN, MAX_RESULTS, HEADLESS)
```

### Scraper filter logic (`scraper.py`)

`should_include(website)` — keep listing if:
- no website, OR
- website is social media (Instagram, Facebook, TikTok, etc.)

Listings with real standalone websites are skipped.

### Bot flow

```
/start or button → user types keyword → _run_scrape() → scrape_maps() → build_excel() → reply_document
```

`/search <keyword>` also works directly without the menu.

## Key env vars

| Var | Default | Notes |
|-----|---------|-------|
| `TELEGRAM_TOKEN` | — | From @BotFather, required |
| `MAX_RESULTS` | 30 | Max listings scraped per search |
| `HEADLESS` | true | Set `false` to watch browser |

## Notes

- Email field always empty — Google Maps doesn't expose emails. Extend `scraper.py` to fetch business websites if needed.
- Google Maps selectors (`data-item-id="authority"`, `data-item-id^="phone:"`) may break if Google updates layout. Adjust in `scraper.py:_extract_phone` and `_extract_website`.
