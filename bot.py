import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import HEADLESS, MAX_RESULTS, TELEGRAM_TOKEN
from exporter import build_excel
from scraper import scrape_maps

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

_MAIN_MENU = InlineKeyboardMarkup(
    [[InlineKeyboardButton("🔍 Search by Keyword", callback_data="search")]]
)

# States
_ST_KEYWORD = "waiting_keyword"
_ST_MAX     = "waiting_max"


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.message.reply_text(
        "Halo! Bot ini scrape Google Maps untuk data bisnis.\n\n"
        "<b>Output:</b> Nama · No. Telepon · Link WhatsApp · Email · Link Google Maps\n"
        "<b>Filter:</b> hanya bisnis tanpa website, atau yang websitenya media sosial "
        "(Instagram, Facebook, dll.)\n\n"
        "Pilih menu di bawah atau ketik /search &lt;keyword&gt;",
        parse_mode="HTML",
        reply_markup=_MAIN_MENU,
    )


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyword = " ".join(context.args).strip() if context.args else ""
    if keyword:
        await _ask_max(update, context, keyword)
    else:
        context.user_data[_ST_KEYWORD] = True
        await update.message.reply_text('Ketik keyword pencarian.\n\nContoh: "Dokter gigi di Bandung"')


async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == "search":
        context.user_data[_ST_KEYWORD] = True
        await query.message.reply_text('Ketik keyword pencarian.\n\nContoh: "Dokter gigi di Bandung"')


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    if context.user_data.get(_ST_KEYWORD):
        context.user_data.pop(_ST_KEYWORD)
        await _ask_max(update, context, text)
        return

    if context.user_data.get(_ST_MAX):
        context.user_data.pop(_ST_MAX)
        keyword = context.user_data.pop("keyword", "")
        # Parse max input
        if text.lower() in ("skip", "-", ""):
            max_results = MAX_RESULTS
        else:
            try:
                max_results = max(1, min(int(text), 200))
            except ValueError:
                await update.message.reply_text(
                    "Input tidak valid. Masukkan angka (misal: 50) atau ketik <b>skip</b>.",
                    parse_mode="HTML",
                )
                context.user_data[_ST_MAX] = True
                context.user_data["keyword"] = keyword
                return
        await _run_scrape(update, context, keyword, max_results)
        return

    await update.message.reply_text(
        "Gunakan /start untuk memulai atau /search &lt;keyword&gt;",
        parse_mode="HTML",
    )


async def _ask_max(
    update: Update, context: ContextTypes.DEFAULT_TYPE, keyword: str
) -> None:
    context.user_data[_ST_MAX] = True
    context.user_data["keyword"] = keyword
    await update.message.reply_text(
        f'Keyword: <b>{keyword}</b>\n\n'
        f'Mau scrape maksimal berapa listing?\n'
        f'(Ketik angka, contoh: <b>50</b> · default: <b>{MAX_RESULTS}</b> · max: 200)\n\n'
        f'Atau ketik <b>skip</b> untuk pakai default.',
        parse_mode="HTML",
    )


async def _run_scrape(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    keyword: str,
    max_results: int,
) -> None:
    status = await update.message.reply_text(
        f'⏳ Scraping <b>{keyword}</b> (maks {max_results} listing)...',
        parse_mode="HTML",
    )

    async def on_progress(current: int, total: int) -> None:
        if current == 1 or current % 5 == 0:
            try:
                await status.edit_text(
                    f'⏳ Scraping <b>{keyword}</b>\nProgress: {current}/{total} listing...',
                    parse_mode="HTML",
                )
            except Exception:
                pass

    try:
        results = await scrape_maps(
            keyword,
            max_results=max_results,
            headless=HEADLESS,
            progress_cb=on_progress,
        )

        if not results:
            await status.edit_text(
                f'❌ Tidak ada hasil untuk "<b>{keyword}</b>".\n'
                "Semua listing memiliki website (bukan sosmed).",
                parse_mode="HTML",
            )
            return

        excel_buf = build_excel(results, keyword)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gmaps_{keyword[:25].replace(' ', '_')}_{ts}.xlsx"

        await status.edit_text(
            f'✅ Selesai! <b>{len(results)}</b> hasil untuk "<b>{keyword}</b>".',
            parse_mode="HTML",
        )
        await update.message.reply_document(
            document=excel_buf,
            filename=filename,
            caption=f"📊 {len(results)} bisnis\n🔑 Keyword: {keyword}\n📋 Maks diminta: {max_results}",
            reply_markup=_MAIN_MENU,
        )

    except Exception as e:
        logger.exception(f"Scrape failed for '{keyword}'")
        await status.edit_text(f"❌ Error: {e}")


def main() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN kosong — set di file .env")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CallbackQueryHandler(button_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot running (headless=%s)...", HEADLESS)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
