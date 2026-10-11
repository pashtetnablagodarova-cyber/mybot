import os
import json
import asyncio
from http.server import BaseHTTPRequestHandler
from aiogram import Bot
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties
from bot import dp, init_db


BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

_db_initialized = False


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive")

    def do_POST(self):
        global _db_initialized
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def process():
                global _db_initialized
                if not _db_initialized:
                    await init_db()
                    _db_initialized = True
                update = Update.model_validate(data, context={"bot": bot})
                await dp.feed_update(bot, update)

            loop.run_until_complete(process())
            loop.close()

            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"error: {e}".encode())
