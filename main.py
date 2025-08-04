import asyncio
import os
import traceback
import uvicorn
import httpx
from fastapi import FastAPI
from datetime import datetime
from TikTokLive import TikTokLiveClient
from rich.console import Console
from aiogram import Bot, Dispatcher, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

USERNAMES = ["lvbliss2", "bliss_nt", "lv.bliss"]
user_status = {}

console = Console()
bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
router = Router()
dp = Dispatcher()
dp.include_router(router)

app = FastAPI()

@app.api_route("/ping", methods=["GET", "HEAD"])
async def ping():
    return {"status": "ok"}

async def run_server():
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config("main:app", host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

def timestamp_tag():
    now = datetime.now().strftime("%H:%M:%S")
    return f"[bold #d32b4b][{now}][/bold #d32b4b]"

def user_tag(username):
    return f"[bold #d32b4b]@{username}[/bold #d32b4b]"

async def send_telegram(text: str):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=text, disable_web_page_preview=True)
    except Exception as e:
        console.print(f"{timestamp_tag()} [white]Ошибка при отправке в Telegram:[/white] {e}")

async def monitor_user(username):
    tag = user_tag(username)
    was_live = None
    user_status[username] = False

    console.print(f"{timestamp_tag()} [white]Мониторинг пользователя {tag}...\n[/white]")

    while True:
        client = TikTokLiveClient(unique_id=username)

        try:
            is_live = await client.is_live()

            if is_live and not was_live:
                console.print(f"{timestamp_tag()} [white]{tag} НАЧАЛ эфир![/white]")
                await send_telegram(f"🔴 <b>{username}</b> начал эфир!\nhttps://www.tiktok.com/@{username}/live")
                user_status[username] = True
                was_live = True

            elif not is_live and was_live:
                console.print(f"{timestamp_tag()} [white]{tag} ЗАКОНЧИЛ эфир.[/white]")
                await send_telegram(f"⚪️ <b>{username}</b> завершил эфир.")
                user_status[username] = False
                was_live = False

            elif was_live is None:
                console.print(f"{timestamp_tag()} [white]{tag} не в эфире. Ожидание...[/white]")
                user_status[username] = False
                was_live = False

            await asyncio.sleep(10)

        except Exception as e:
            if isinstance(e, httpx.ConnectTimeout):
                console.print(f"{timestamp_tag()} {tag} [white]Сетевая ошибка (таймаут). Повтор через 10 сек...[/white]")
            elif isinstance(e, httpx.ReadTimeout):
                console.print(f"{timestamp_tag()} {tag} [white]Таймаут чтения. Повтор через 10 сек...[/white]")
            elif isinstance(e, ConnectionError) or "WebSocket" in str(e):
                console.print(f"{timestamp_tag()} {tag} [white]Проблема WebSocket или соединения. Повтор...[/white]")
            else:
                error_msg = traceback.format_exc()
                console.print(f"{timestamp_tag()} {tag} [red]Неизвестная ошибка:[/red]\n{error_msg}")

            await asyncio.sleep(15)
            continue

        await asyncio.sleep(10)

@router.message(Command("start"))
async def handle_start_command(message: Message):
    lines = []
    for username in USERNAMES:
        status = user_status.get(username)
        if status is None:
            emoji = "❓"
            text_status = "неизвестно"
        elif status:
            emoji = "🔴"
            text_status = "в эфире"
        else:
            emoji = "⚪️"
            text_status = "не в эфире"
        link = f"https://www.tiktok.com/@{username}/live"
        lines.append(f"{emoji} <b>{username}</b> — {text_status}\n{link}")
    await message.answer("\n\n".join(lines), disable_web_page_preview=True)

async def main():
    tasks = [dp.start_polling(bot), run_server()]
    for i, username in enumerate(USERNAMES):
        await asyncio.sleep(1.5)
        tasks.append(monitor_user(username))
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print(f"\n{timestamp_tag()} [white]Мониторинг остановлен пользователем.[/white]")

