import os
from aiohttp import web
from aiogram import Bot
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties

from bot import dp, init_db

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))


async def handle(request):
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="ok")
    except Exception as e:
        print(f"Error: {e}")
        return web.Response(text="error", status=500)


app = web.Application()
app.router.add_post("/", handle)
app.router.add_get("/", lambda r: web.Response(text="Bot is alive"))
