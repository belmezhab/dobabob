import asyncio
import os
import logging
from typing import Dict

from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from aiohttp import web
from TikTokLive import TikTokLiveClient
import httpx

# ---------------- Настройки ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dobabob")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID_STR = os.getenv("CHAT_ID")

if not TELEGRAM_TOKEN or not CHAT_ID_STR:
    logger.error("Не заданы TELEGRAM_TOKEN или CHAT_ID")
    raise SystemExit(1)

try:
    CHAT_ID = int(CHAT_ID_STR)
except ValueError:
    logger.error("CHAT_ID должен быть числом")
    raise SystemExit(1)

USERNAMES = ["ya_bl1ss", "n3v3rdie1", "bliss_nt", "lv.bliss"]
user_status: Dict[str, bool] = {u: False for u in USERNAMES}
monitor_tasks: Dict[str, asyncio.Task] = {}

# ---------------- Telegram ----------------
bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
router = Router()
dp = Dispatcher()
dp.include_router(router)


@router.message(Command("start"))
async def handle_start_command(message: Message):
    if message.chat.id != CHAT_ID:
        return

    parts = []
    for u in USERNAMES:
        status = user_status.get(u)
        emoji = "❓" if status is None else ("🔴" if status else "⚪️")
        text_status = "в эфире" if status else "не в эфире"
        parts.append(f"{emoji} <b>{u}</b> — {text_status}\nhttps://www.tiktok.com/@{u}/live")
    await message.answer("\n\n".join(parts), disable_web_page_preview=True)


# ---------------- TikTok Monitor ----------------
async def monitor_user(username: str):
    """Мониторинг одного пользователя TikTok с авто-перезапуском клиента"""
    while True:
        try:
            client = TikTokLiveClient(unique_id=username)
            while True:
                try:
                    is_live = await client.is_live()
                except httpx.TimeoutException:
                    logger.warning("%s: timeout, повтор через 15с", username)
                    await asyncio.sleep(15)
                    continue
                except Exception as e:
                    logger.warning("%s: ошибка при запросе (%s), пересоздание клиента", username, e)
                    break

                prev = user_status.get(username)
                if is_live and not prev:
                    user_status[username] = True
                    await bot.send_message(
                        CHAT_ID,
                        f"🔴 <b>{username}</b> начал эфир!\nhttps://www.tiktok.com/@{username}/live",
                        disable_web_page_preview=True
                    )
                elif not is_live and prev:
                    user_status[username] = False
                    await bot.send_message(
                        CHAT_ID,
                        f"⚪️ <b>{username}</b> завершил эфир.",
                        disable_web_page_preview=True
                    )

                # Проверяем каждые 15 секунд
                await asyncio.sleep(15)
        except Exception as e:
            logger.exception("%s: критическая ошибка %s", username, e)
        finally:
            await asyncio.sleep(15)


# ---------------- Webhook Server ----------------
async def on_startup(app: web.Application):
    webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/webhook"
    await bot.set_webhook(webhook_url)
    logger.info("Webhook установлен: %s", webhook_url)

async def on_shutdown(app: web.Application):
    await bot.session.close()

# healthcheck endpoint
async def ping(request):
    return web.json_response({"status": "ok"})

def create_app() -> web.Application:
    app = web.Application()
    SimpleRequestHandler(dp, bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    app.router.add_get("/ping", ping)  # 🔥 сюда добавлен health check
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


async def main():
    # Запускаем мониторинг
    for u in USERNAMES:
        task = asyncio.create_task(monitor_user(u), name=f"monitor-{u}")
        monitor_tasks[u] = task

    # aiohttp сервер (Telegram webhook + мониторинг в фоне)
    app = create_app()

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8000)))
    await site.start()

    logger.info("Сервер запущен")
    # держим фоновые задачи
    await asyncio.gather(*monitor_tasks.values())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Завершение работы...")



