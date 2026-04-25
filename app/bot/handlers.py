"""
bot/handlers.py — Telegram бот.

Режимы запуска (TELEGRAM_MODE):
  polling — для локальной разработки
  webhook — для прода (VPS + nginx + SSL)
"""

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_MODE, WEBHOOK_URL, WEBHOOK_PATH, WEBHOOK_SECRET, RATE_LIMIT_REQUESTS, RATE_LIMIT_DAYS, RATE_LIMIT_WHITELIST
from app.services.cache import check_rate_limit, get_cached
from app.services.rag import ask as rag_ask

log = logging.getLogger(__name__)

WELCOME = (
    "👋 <b>Привет! Я — Супервизор в кармане.</b>\n\n"
    "Помогаю начинающим гештальт-терапевтам разбираться в сложных моментах — "
    "отвечаю на вопросы по теории и практике.\n\n"
    "💬 <b>Просто опиши что происходит на сессии</b> — и я помогу разобраться.\n\n"
    "Например:\n"
    "• <i>«Клиент сказал, что хочет бросить терапию»</i>\n"
    "• <i>«Чувствую, что недостаточно квалифицирован для этого случая»</i>\n"
    "• <i>«Клиент агрессивно реагирует на мои интервенции»</i>\n"
    "• <i>«Как работать с сопротивлением?»</i>\n\n"
    "⚠️ <b>Важно:</b> ответы не заменяют живую супервизию.\n\n"
    "ℹ️ /help — как устроена система и больше примеров"
)


def _split_message(text: str, limit: int = 4096) -> list[str]:
    """Разбивает длинное сообщение на части по границам абзацев."""
    if len(text) <= limit:
        return [text]
    parts = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        split_at = text.rfind("\n\n", 0, limit)
        if split_at == -1:
            split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        parts.append(text[:split_at].strip())
        text = text[split_at:].strip()
    return parts


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME, parse_mode="HTML")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = update.message.text
    user_id = update.effective_user.id

    # Проверяем лимит только если ответа нет в кэше
    if not await get_cached(question):
        whitelisted = user_id in RATE_LIMIT_WHITELIST
        allowed, _ = await check_rate_limit(user_id, whitelisted=whitelisted)
        if not allowed:
            await update.message.reply_text(
                f"⚠️ Вы достигли лимита {RATE_LIMIT_REQUESTS} вопросов за {RATE_LIMIT_DAYS} дня.\n"
                "Лимит обновится автоматически."
            )
            return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        result = await rag_ask(
            question=question,
            user_id=user_id,
            channel="telegram",
        )
        for part in _split_message(result["answer"]):
            await update.message.reply_text(part, parse_mode="HTML")
    except Exception as e:
        log.exception("Ошибка при обработке сообщения от user_id=%d: %s", user_id, e)
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуй ещё раз чуть позже.")


HELP = (
    "📖 <b>Как устроен Супервизор в кармане</b>\n\n"

    "Это инструмент для начинающих гештальт-терапевтов. "
    "Он отвечает на вопросы, опираясь на профессиональную литературу по гештальт-подходу — "
    "не на общие слова из интернета, а на конкретные книги.\n\n"

    "📚 <b>База знаний:</b>\n"
    "• <b>Джойс и Силлс «Гештальт-терапия шаг за шагом»</b> — практическое руководство "
    "по ведению сессии, работе с контактом, сопротивлением, экспериментами и завершением терапии\n"
    "• <b>Манн «Гештальт-терапия: 100 ключевых моментов»</b> — концентрированный разбор "
    "ключевых идей и техник гештальт-подхода\n"
    "• <b>Польстер «Интегрированная гештальт-терапия»</b> — глубокий разбор механизмов "
    "прерывания контакта: интроекция, проекция, ретрофлексия, дефлексия, слияние\n"
    "• <b>Перлз «Гештальт-подход. Свидетель терапии»</b> — первоисточник: незавершённый "
    "гештальт, осознавание, цикл опыта\n\n"

    "💡 <b>Как использовать:</b>\n"
    "Просто опиши что происходит — не нужно формулировать «правильный вопрос». "
    "Чем конкретнее, тем точнее ответ.\n\n"

    "🗂 <b>Примеры ситуаций:</b>\n"
    "• <i>«Клиент молчит всю сессию, я не знаю как его разговорить»</i>\n"
    "• <i>«Клиент хочет завершить терапию после двух встреч»</i>\n"
    "• <i>«Чувствую, что этот клиент меня раздражает — что с этим делать?»</i>\n"
    "• <i>«Как работать с человеком, который всё время интеллектуализирует?»</i>\n"
    "• <i>«Клиент плачет, я не понимаю нужно ли вмешиваться»</i>\n"
    "• <i>«Что такое ретрофлексия и как её распознать?»</i>\n\n"

    "⚠️ <b>Важно помнить:</b>\n"
    "Супервизор в кармане — это поддержка между сессиями, а не замена живой супервизии. "
    "В сложных случаях обязательно обращайся к своему супервизору."
)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP, parse_mode="HTML")


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


_bot_app: Application | None = None


async def startup() -> None:
    global _bot_app
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN не задан — бот не запущен")
        return

    _bot_app = build_app()
    await _bot_app.initialize()
    await _bot_app.start()

    if TELEGRAM_MODE == "webhook":
        url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
        await _bot_app.bot.set_webhook(url, secret_token=WEBHOOK_SECRET or None)
        log.info("Telegram webhook установлен: %s", url)
    else:
        await _bot_app.updater.start_polling()
        log.info("Telegram бот запущен в режиме polling")


async def shutdown() -> None:
    if _bot_app is None:
        return
    if TELEGRAM_MODE == "polling":
        await _bot_app.updater.stop()
    await _bot_app.stop()
    await _bot_app.shutdown()
    log.info("Telegram бот остановлен")


async def process_update(data: dict) -> None:
    """Обработка входящего webhook-апдейта."""
    if _bot_app is None:
        return
    update = Update.de_json(data, _bot_app.bot)
    await _bot_app.process_update(update)
