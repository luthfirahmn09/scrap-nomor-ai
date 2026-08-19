# 📇 Scrap Nomor AI

A Telegram bot that searches Google Maps for local businesses and returns their contact info (name, phone, WhatsApp link, Google Maps link) as a ready-to-use Excel file — handy for building outreach/lead lists for a niche ("dentists in Bandung", "coffee shops in Jakarta", ...).

## How it works

```
/start or button → type a keyword → scrape_maps() (Playwright) → build_excel() → sent back as .xlsx
```

1. You send a keyword (e.g. `"Dokter gigi di Bandung"`) via `/search <keyword>` or the inline menu.
2. `scraper.py` drives a headless Chromium browser (Playwright) against `google.com/maps/search/...`, scrolls the results feed, and opens each listing to pull its name, phone number, and website link.
3. **Filter**: a listing is kept only if it has **no website**, or its "website" is actually a social media profile (Instagram, Facebook, TikTok, etc.) — the idea being these businesses are more likely to need help getting online, and are less likely to already have found via their own site.
4. `exporter.py` builds an `.xlsx` (via `openpyxl`) with a clickable WhatsApp link (`wa.me/...`) derived from the phone number, plus the Google Maps link.
5. The file is sent straight back to the chat.

## Getting started

```bash
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# edit .env → set TELEGRAM_TOKEN (from @BotFather)

python bot.py
```

Or with Docker:

```bash
cp .env.example .env
docker-compose up -d --build
```

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `TELEGRAM_TOKEN` | — | Required, from [@BotFather](https://t.me/BotFather) |
| `MAX_RESULTS` | 30 | Default cap on listings scraped per search (user can override per-search, up to 200) |
| `HEADLESS` | true | Set `false` to watch the browser scrape in real time (debugging) |

## Project structure

```
bot.py          # Telegram handlers: /start, /search, inline menu, conversation flow
scraper.py      # Playwright-driven Google Maps scraper + the website/social-media filter
exporter.py     # Builds the .xlsx report from scraped results
config.py       # Loads .env (TELEGRAM_TOKEN, MAX_RESULTS, HEADLESS)
```

## Notes & limitations

- The email column is always empty — Google Maps listings don't expose an email address directly. Extending the scraper to visit each business's own website (when it has one) to look for a contact email would be a natural next step.
- Google Maps' DOM selectors (`data-item-id="authority"`, `data-item-id^="phone:"`, the results `[role="feed"]`) can change without notice; if scraping starts returning empty results, that's the first place to check (`scraper.py`, `_extract_phone` / `_extract_website`).
- This is a browser-automation scraper against Google Maps' public web UI, not an official API — be mindful of Google's Terms of Service and keep request volume reasonable (`MAX_RESULTS`, delays between listings) for your own use case.

## License

MIT
