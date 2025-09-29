import asyncio
import os
import logging
from typing import Dict

from aiogram.types import Message
from aiogram.filters import Command
from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from fastapi import FastAPI
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

USERNAMES = ["lvbliss2", "bliss_nt", "lv.bliss", "n3v3rdie1"]
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
    # Бот отвечает только твоему чату
    if message.chat.id != CHAT_ID:
        return

    parts = []
    for u in USERNAMES:
        status = user_status.get(u)
        emoji = "❓" if status is None else ("🔴" if status else "⚪️")
        text_status = "в эфире" if status else "не в эфире"
        parts.append(f"{emoji} {u} — {text_status}\nhttps://www.tiktok.com/@{u}/live")
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
                    logger.warning("%s: timeout, повтор через 10с", username)
                    await asyncio.sleep(10)
                    continue
                except Exception as e:
                    logger.warning("%s: ошибка при запросе (%s), пересоздание клиента", username, e)
                    break  # пересоздадим client

                prev = user_status.get(username)
                if is_live and not prev:
                    user_status[username] = True
                    await bot.send_message(
                        CHAT_ID,
                        f"🔴 {username} начал эфир!\nhttps://www.tiktok.com/@{username}/live"
                    )
                elif not is_live and prev:
                    user_status[username] = False
                    await bot.send_message(
                        CHAT_ID,
                        f"⚪️ {username} завершил эфир."
                    )
                await asyncio.sleep(10)
        except Exception as e:
            logger.exception("%s: критическая ошибка %s", username, e)
        finally:
            # ждём перед новой попыткой
            await asyncio.sleep(15)


# ---------------- FastAPI ----------------
app = FastAPI()


@app.get("/ping")
async def ping():
    # Проверяем, живы ли все задачи мониторинга
    dead_users = [u for u, t in monitor_tasks.items() if t.done()]
    if dead_users:
        return {"status": "error", "dead_monitors": dead_users}
    return {"status": "ok"}


async def run_server():
    import uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


# ---------------- Main ----------------
async def main():
    # Запускаем мониторинг для всех пользователей
    for u in USERNAMES:
        task = asyncio.create_task(monitor_user(u), name=f"monitor-{u}")
        monitor_tasks[u] = task

    # Запускаем Telegram и HTTP сервер
    await asyncio.gather(
        dp.start_polling(bot),
        run_server(),
        *monitor_tasks.values(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Завершение работы...")

