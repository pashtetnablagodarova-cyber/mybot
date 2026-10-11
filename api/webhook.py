import os
import json
import time
import random
import asyncio
from http.server import BaseHTTPRequestHandler
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup
)
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties
import asyncpg

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
CHANNEL_URL = "https://t.me/randomkanews"
ADMIN_ID = 8006016784

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

db_pool = None
broadcast_state = {"waiting": False}
guess_numbers = {}
hat_games = {}
roulette_state = {}
upgrade_state = {}


async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                name TEXT,
                coins BIGINT DEFAULT 0,
                xp BIGINT DEFAULT 0,
                cases_opened INTEGER DEFAULT 0,
                last_bonus BIGINT DEFAULT 0,
                inventory TEXT DEFAULT '',
                last_hat BIGINT DEFAULT 0,
                hat_count INTEGER DEFAULT 0,
                last_dealer BIGINT DEFAULT 0,
                dealer_count INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                last_streak BIGINT DEFAULT 0,
                streak_total INTEGER DEFAULT 0,
                crystals INTEGER DEFAULT 0,
                season_xp BIGINT DEFAULT 0
            )
        """)


async def get_user(user_id, name="Игрок"):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        if not row:
            await conn.execute(
                "INSERT INTO users (user_id, name) VALUES ($1, $2)", user_id, name
            )
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        return row


async def update_user(user_id, **kwargs):
    async with db_pool.acquire() as conn:
        sets = ", ".join([f"{k}=${i+2}" for i, k in enumerate(kwargs.keys())])
        values = list(kwargs.values())
        await conn.execute(f"UPDATE users SET {sets} WHERE user_id=$1", user_id, *values)


def level_from_xp(xp):
    lvl, need, total = 1, 200, 0
    while xp >= total + need:
        total += need
        need = int(need * 1.2)
        lvl += 1
    return lvl, total, need


def streak_reward(day):
    rewards = {1: (150, 0), 2: (250, 0), 3: (400, 0), 4: (600, 0),
               5: (900, 0), 6: (1300, 0), 7: (2000, 0)}
    return rewards.get(day, (0, 0))


def main_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Я"), KeyboardButton(text="🏆 Топ")],
            [KeyboardButton(text="🎁 Кейсы"), KeyboardButton(text="🔥 Стрик")],
            [KeyboardButton(text="💰 Заработать"), KeyboardButton(text="📰 Новости")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери действие..."
    )


def is_admin(user_id):
    return user_id == ADMIN_ID


@dp.message(F.text == "/start")
async def start(message: Message):
    await get_user(message.from_user.id, message.from_user.first_name or "Игрок")
    u = await get_user(message.from_user.id)
    if u["banned"] == 1:
        await message.answer("🚫 Ты забанен.")
        return
    await message.answer(
        "🎩 Добро пожаловать в мир <b>Фокусов</b>!\n"
        "Зарабатывай монеты, открывай кейсы, повышай уровень.",
        reply_markup=main_reply_menu()
    )


@dp.message(F.text == "👤 Я")
async def me(message: Message):
    u = await get_user(message.from_user.id, message.from_user.first_name or "Игрок")
    if u["banned"] == 1:
        await message.answer("🚫 Ты забанен.")
        return
    lvl, cur_total, need = level_from_xp(u["xp"])
    inv_list = [i for i in u["inventory"].split(",") if i]
    async with db_pool.acquire() as conn:
        place = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE coins > $1 AND banned=0", u["coins"]
        )
    place += 1
    text = (
        f"👤 <b>{u['name']}</b>\n\n"
        f"🎚 Уровень: <b>{lvl}</b>\n"
        f"✨ Опыт: {u['xp'] - cur_total} / {need}\n"
        f"💰 Баланс: <b>{u['coins']}</b>\n"
        f"💎 Кристаллы: <b>{u['crystals']}</b>\n"
        f"🏅 Место: <b>#{place}</b>\n"
        f"🔥 Стрик: <b>{u['streak']}</b> (всего {u['streak_total']})\n"
        f"📅 Сезон XP: <b>{u['season_xp']}</b>\n"
        f"🎁 Кейсов: {u['cases_opened']}\n\n"
        f"🎒 Инвентарь: {', '.join(inv_list) if inv_list else 'пусто'}"
    )
    await message.answer(text)


@dp.message(F.text == "🏆 Топ")
async def top(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 За всё время", callback_data="top_all")],
        [InlineKeyboardButton(text="📅 Сезон", callback_data="top_season")],
    ])
    await message.answer("🏆 Выбери рейтинг:", reply_markup=kb)


@dp.callback_query(F.data == "top_all")
async def top_all(call: CallbackQuery):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT name, coins, xp FROM users WHERE banned=0 ORDER BY coins DESC LIMIT 10")
    text = "🌍 <b>Топ за всё время:</b>\n\n"
    for i, r in enumerate(rows, 1):
        lvl, _, _ = level_from_xp(r["xp"])
        text += f"{i}. {r['name']} — 💰{r['coins']} | 🎚{lvl}\n"
    text += "\n🎚 <b>Топ по уровню:</b>\n\n"
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT name, coins, xp FROM users WHERE banned=0 ORDER BY xp DESC LIMIT 10")
    for i, r in enumerate(rows, 1):
        lvl, _, _ = level_from_xp(r["xp"])
        text += f"{i}. {r['name']} — 🎚{lvl} | 💰{r['coins']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 За всё время", callback_data="top_all")],
        [InlineKeyboardButton(text="📅 Сезон", callback_data="top_season")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "top_season")
async def top_season(call: CallbackQuery):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT name, season_xp FROM users WHERE banned=0 ORDER BY season_xp DESC LIMIT 10")
    text = "📅 <b>Топ сезона:</b>\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. {r['name']} — ⭐ {r['season_xp']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 За всё время", callback_data="top_all")],
        [InlineKeyboardButton(text="📅 Сезон", callback_data="top_season")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@dp.message(F.text == "🎁 Кейсы")
async def cases(message: Message):
    u = await get_user(message.from_user.id)
    if u["banned"] == 1:
        await message.answer("🚫 Ты забанен.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Кейс новичка — 500 💰", callback_data="case1")],
        [InlineKeyboardButton(text="🎁 Кейс фокусника — 2500 💰", callback_data="case2")],
    ])
    await message.answer("🎁 Выбери кейс:", reply_markup=kb)


@dp.callback_query(F.data == "case1")
async def case1(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    if u["banned"] == 1:
        await call.answer("🚫", show_alert=True)
        return
    coins, xp = u["coins"], u["xp"]
    if coins < 500:
        await call.answer("Недостаточно монет!", show_alert=True)
        return
    roll = random.randint(1, 100)
    inv_list = [i for i in u["inventory"].split(",") if i]
    if roll <= 40:
        coins += 300 - 500
        result = "🪙 +300 монет"
    elif roll <= 65:
        xp += 40; coins -= 500
        result = "✨ +40 опыта"
    elif roll <= 85:
        coins += 800 - 500
        result = "🪙 +800 монет"
    elif roll <= 95:
        inv_list.append("🃏 Карта фокусника"); coins -= 500
        result = "🃏 Карта фокусника"
    else:
        inv_list.append("🔮 Малый амулет"); coins -= 500
        result = "🔮 Малый амулет"
    await update_user(call.from_user.id, coins=coins, xp=xp,
                      cases_opened=u["cases_opened"] + 1, inventory=",".join(inv_list))
    await call.message.edit_text(f"🎁 Кейс новичка!\n\n{result}\n\n💰 {coins}")
    await call.answer()


@dp.callback_query(F.data == "case2")
async def case2(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    if u["banned"] == 1:
        await call.answer("🚫", show_alert=True)
        return
    coins, xp = u["coins"], u["xp"]
    if coins < 2500:
        await call.answer("Недостаточно монет!", show_alert=True)
        return
    roll = random.randint(1, 100)
    inv_list = [i for i in u["inventory"].split(",") if i]
    if roll <= 30:
        coins += 2000 - 2500
        result = "🪙 +2000 монет"
    elif roll <= 50:
        xp += 120; coins -= 2500
        result = "✨ +120 опыта"
    elif roll <= 65:
        inv_list.append("🎩 Цилиндр"); coins -= 2500
        result = "🎩 Цилиндр"
    elif roll <= 80:
        inv_list.append("🪄 Палочка волшебника"); coins -= 2500
        result = "🪄 Палочка"
    elif roll <= 90:
        inv_list.append("🃏 Карта фокусника"); coins -= 2500
        result = "🃏 Карта"
    elif roll <= 97:
        inv_list.append("🔮 Хрустальный шар"); coins -= 2500
        result = "🔮 Хрустальный шар"
    else:
        inv_list.append("💎 Магический кристалл"); coins -= 2500
        result = "💎 Кристалл"
    await update_user(call.from_user.id, coins=coins, xp=xp,
                      cases_opened=u["cases_opened"] + 1, inventory=",".join(inv_list))
    await call.message.edit_text(f"🎁 Кейс фокусника!\n\n{result}\n\n💰 {coins}")
    await call.answer()


@dp.message(F.text == "🔥 Стрик")
async def streak(message: Message):
    u = await get_user(message.from_user.id)
    if u["banned"] == 1:
        await message.answer("🚫 Ты забанен.")
        return
    now = int(time.time())
    today = now // 86400
    last_day = u["last_streak"] // 86400 if u["last_streak"] else 0
    if last_day == today:
        await message.answer("⏳ Ты уже получал награду сегодня.")
        return
    streak_val = u["streak"] + 1 if last_day == today - 1 else 1
    streak_total = u["streak_total"] + 1
    day = ((streak_val - 1) % 7) + 1
    rc, rx = streak_reward(day)
    crystals = u["crystals"]
    bonus = ""
    if streak_total == 30:
        rc += 10000; crystals += 1
        bonus = "\n🎉 30 дней! +10 000 и 💎"
    elif streak_total == 100:
        rc += 50000; crystals += 3
        bonus = "\n🎉 100 дней! +50 000 и 💎×3"
    elif streak_total == 365:
        rc += 500000; crystals += 10
        bonus = "\n🎉 Год! +500 000 и 💎×10"
    item_text = ""
    inv_list = [i for i in u["inventory"].split(",") if i]
    if day == 7:
        item = random.choice(["🃏 Карта фокусника", "🎩 Цилиндр", "🪄 Палочка волшебника"])
        inv_list.append(item)
        item_text = f"\n🎁 {item}"
    await update_user(message.from_user.id, coins=u["coins"] + rc, xp=u["xp"] + rx,
                      streak=streak_val, last_streak=now, streak_total=streak_total,
                      crystals=crystals, inventory=",".join(inv_list))
    await message.answer(f"🔥 День {streak_val}\n💰 +{rc}\n✨ +{rx}{item_text}{bonus}")


@dp.message(F.text == "📰 Новости")
async def news(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📰 Канал", url=CHANNEL_URL)]
    ])
    await message.answer("📰 Новости:", reply_markup=kb)


@dp.message(F.text == "💰 Заработать")
async def earn(message: Message):
    u = await get_user(message.from_user.id)
    if u["banned"] == 1:
        await message.answer("🚫 Ты забанен.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Угадайка (1 💰)", callback_data="guess")],
        [InlineKeyboardButton(text="🎩 Фокус с шариками", callback_data="hat")],
        [InlineKeyboardButton(text="🃏 Дуэль с дилером", callback_data="dealer")],
        [InlineKeyboardButton(text="🎡 Рулетка", callback_data="roulette")],
        [InlineKeyboardButton(text="⚡ Апгрейдер", callback_data="upgrade")],
    ])
    await message.answer("💰 Выбери способ:", reply_markup=kb)


@dp.callback_query(F.data == "guess")
async def guess_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    if u["coins"] < 1:
        await call.answer("Нужна 1 монета!", show_alert=True)
        return
    await update_user(call.from_user.id, coins=u["coins"] - 1)
    guess_numbers[call.from_user.id] = random.randint(1, 5)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(i), callback_data=f"gnum_{i}") for i in range(1, 6)],
    ])
    await call.message.edit_text("🎲 Число 1-5:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("gnum_"))
async def guess_answer(call: CallbackQuery):
    n = int(call.data.split("_")[1])
    target = guess_numbers.get(call.from_user.id)
    u = await get_user(call.from_user.id)
    if target is None:
        await call.answer("Нет игры", show_alert=True)
        return
    if n == target:
        await update_user(call.from_user.id, coins=u["coins"] + 5)
        text = f"🎉 Угадал! {target}\n💰 +5"
    else:
        text = f"😢 Было {target}."
    guess_numbers.pop(call.from_user.id, None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Ещё (1 💰)", callback_data="guess")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "hat")
async def hat_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    now = int(time.time())
    hc = u["hat_count"]
    if now - u["last_hat"] > 3600:
        await update_user(call.from_user.id, hat_count=0, last_hat=now)
        hc = 0
    if hc >= 5:
        left = 3600 - (now - u["last_hat"])
        await call.answer(f"Лимит. Жди {left//60} мин", show_alert=True)
        return
    hat_games[call.from_user.id] = random.randint(0, 2)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎩 1", callback_data="hat_0"),
         InlineKeyboardButton(text="🎩 2", callback_data="hat_1"),
         InlineKeyboardButton(text="🎩 3", callback_data="hat_2")],
    ])
    await call.message.edit_text("🎩 Где шарик?", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("hat_"))
async def hat_answer(call: CallbackQuery):
    choice = int(call.data.split("_")[1])
    target = hat_games.get(call.from_user.id)
    u = await get_user(call.from_user.id)
    if target is None:
        await call.answer("Нет игры", show_alert=True)
        return
    if choice == target:
        await update_user(call.from_user.id, coins=u["coins"] + 5, hat_count=u["hat_count"] + 1)
        text = "🎉 +5"
    else:
        await update_user(call.from_user.id, hat_count=u["hat_count"] + 1)
        text = f"😢 Шляпа {target + 1}."
    hat_games.pop(call.from_user.id, None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎩 Ещё", callback_data="hat")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


dealer_cards = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


@dp.callback_query(F.data == "dealer")
async def dealer_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    now = int(time.time())
    dc = u["dealer_count"]
    if now - u["last_dealer"] > 86400:
        await update_user(call.from_user.id, dealer_count=0, last_dealer=now)
        dc = 0
    if dc >= 3:
        await call.answer("Лимит 3/день", show_alert=True)
        return
    p = random.choice(dealer_cards)
    d = random.choice(dealer_cards)
    vals = {c: i for i, c in enumerate(dealer_cards)}
    if vals[p] > vals[d]:
        await update_user(call.from_user.id, coins=u["coins"] + 10, dealer_count=u["dealer_count"] + 1)
        text = f"🃏 {p} vs {d}\n🎉 +10"
    elif vals[p] < vals[d]:
        await update_user(call.from_user.id, dealer_count=u["dealer_count"] + 1)
        text = f"🃏 {p} vs {d}\n😢 Дилер."
    else:
        await update_user(call.from_user.id, dealer_count=u["dealer_count"] + 1)
        text = f"🃏 {p} vs {d}\n🤝 Ничья"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Ещё", callback_data="dealer")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "roulette")
async def roulette_start(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 ×2", callback_data="rl_red")],
        [InlineKeyboardButton(text="⚫ ×2", callback_data="rl_black")],
        [InlineKeyboardButton(text="🟢 ×14", callback_data="rl_green")],
    ])
    await call.message.edit_text("🎡 Цвет:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("rl_"))
async def roulette_color(call: CallbackQuery):
    color = call.data.split("_")[1]
    roulette_state[call.from_user.id] = {"color": color}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="10", callback_data="rbet_10"),
         InlineKeyboardButton(text="50", callback_data="rbet_50"),
         InlineKeyboardButton(text="100", callback_data="rbet_100")],
        [InlineKeyboardButton(text="500", callback_data="rbet_500"),
         InlineKeyboardButton(text="1000", callback_data="rbet_1000")],
    ])
    await call.message.edit_text(f"🎡 {color}\nСтавка:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("rbet_"))
async def roulette_bet(call: CallbackQuery):
    bet = int(call.data.split("_")[1])
    st = roulette_state.get(call.from_user.id)
    if not st:
        await call.answer("Сначала цвет", show_alert=True)
        return
    u = await get_user(call.from_user.id)
    if u["coins"] < bet:
        await call.answer("Мало монет!", show_alert=True)
        return
    roll = random.randint(1, 100)
    landed = "red" if roll <= 45 else ("black" if roll <= 90 else "green")
    if landed == st["color"]:
        reward = bet * 14 if landed == "green" else bet * 2
        await update_user(call.from_user.id, coins=u["coins"] - bet + reward)
        text = f"🎡 {landed}\n🎉 +{reward}"
    else:
        await update_user(call.from_user.id, coins=u["coins"] - bet)
        text = f"🎡 {landed}\n😢 -{bet}"
    roulette_state.pop(call.from_user.id, None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎡 Ещё", callback_data="roulette")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "upgrade")
async def upgrade_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    inv = [i for i in u["inventory"].split(",") if i]
    if not inv:
        await call.answer("Пусто!", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(text=item, callback_data=f"upg_{idx}")] for idx, item in enumerate(inv)]
    await call.message.edit_text("⚡ Предмет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()


@dp.callback_query(F.data.startswith("upg_"))
async def upgrade_pick(call: CallbackQuery):
    idx = int(call.data.split("_")[1])
    u = await get_user(call.from_user.id)
    inv = [i for i in u["inventory"].split(",") if i]
    if idx >= len(inv):
        await call.answer("Нет", show_alert=True)
        return
    upgrade_state[call.from_user.id] = {"inv_idx": idx}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="×2", callback_data="upg_x_2"),
         InlineKeyboardButton(text="×3", callback_data="upg_x_3")],
        [InlineKeyboardButton(text="×5", callback_data="upg_x_5"),
         InlineKeyboardButton(text="×10", callback_data="upg_x_10")],
    ])
    await call.message.edit_text(f"⚡ {inv[idx]}\nМножитель:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("upg_x_"))
async def upgrade_do(call: CallbackQuery):
    mult = int(call.data.split("_")[-1])
    st = upgrade_state.get(call.from_user.id)
    if not st:
        await call.answer("Ошибка", show_alert=True)
        return
    chances = {2: 60, 3: 40, 5: 25, 10: 10}
    u = await get_user(call.from_user.id)
    inv = [i for i in u["inventory"].split(",") if i]
    if random.randint(1, 100) <= chances[mult]:
        reward = 1000 * mult
        inv.pop(st["inv_idx"])
        await update_user(call.from_user.id, coins=u["coins"] + reward, inventory=",".join(inv))
        text = f"🎉 ×{mult}! +{reward}"
    else:
        inv.pop(st["inv_idx"])
        await update_user(call.from_user.id, inventory=",".join(inv))
        text = f"💥 ×{mult} провал"
    upgrade_state.pop(call.from_user.id, None)
    await call.message.edit_text(text)


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Стат", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="💰 +монет", callback_data="adm_give")],
        [InlineKeyboardButton(text="💸 -монет", callback_data="adm_take")],
        [InlineKeyboardButton(text="✨ XP", callback_data="adm_setxp")],
        [InlineKeyboardButton(text="💎 Кристаллы", callback_data="adm_crystals")],
        [InlineKeyboardButton(text="🚫 Бан", callback_data="adm_ban")],
        [InlineKeyboardButton(text="✅ Разбан", callback_data="adm_unban")],
        [InlineKeyboardButton(text="🎁 Предмет", callback_data="adm_giveitem")],
        [InlineKeyboardButton(text="❌", callback_data="adm_close")],
    ])


@dp.message(F.text == "/admin")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 Админ:", reply_markup=admin_menu())


@dp.callback_query(F.data == "adm_stats")
async def adm_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    async with db_pool.acquire() as conn:
        r = await conn.fetchrow("SELECT COUNT(*) as t, SUM(coins) as c, SUM(xp) as x, SUM(cases_opened) as cs FROM users")
        b = await conn.fetchval("SELECT COUNT(*) FROM users WHERE banned=1")
    text = (f"📊 Игроков: {r['t'] or 0}\n🚫 Бан: {b or 0}\n"
            f"💰 Монет: {r['c'] or 0}\n✨ XP: {r['x'] or 0}\n🎁 Кейсов: {r['cs'] or 0}")
    await call.message.edit_text(text, reply_markup=admin_menu())
    await call.answer()


@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    broadcast_state["waiting"] = True
    await call.message.edit_text("📢 Текст рассылки (или /cancel):")
    await call.answer()


@dp.message(F.text == "/cancel")
async def cancel_broadcast(message: Message):
    if not is_admin(message.from_user.id):
        return
    broadcast_state["waiting"] = False
    await message.answer("❌ Отменено.")


@dp.message(F.text)
async def handle_broadcast(message: Message):
    if not is_admin(message.from_user.id) or not broadcast_state["waiting"]:
        return
    broadcast_state["waiting"] = False
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users WHERE banned=0")
    sent, failed = 0, 0
    for r in rows:
        try:
            await bot.send_message(r["user_id"], message.text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await message.answer(f"📢 {sent} / ❌ {failed}")


@dp.callback_query(F.data == "adm_give")
async def adm_give(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("💰 give 123 1000")
    await call.answer()


@dp.message(F.text.startswith("give "))
async def adm_give_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, uid, a = message.text.split()
        uid, a = int(uid), int(a)
    except:
        await message.answer("❌ give 123 1000")
        return
    u = await get_user(uid)
    await update_user(uid, coins=u["coins"] + a)
    await message.answer(f"✅ +{a}")


@dp.callback_query(F.data == "adm_take")
async def adm_take(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("💸 take 123 1000")
    await call.answer()


@dp.message(F.text.startswith("take "))
async def adm_take_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, uid, a = message.text.split()
        uid, a = int(uid), int(a)
    except:
        await message.answer("❌ take 123 1000")
        return
    u = await get_user(uid)
    await update_user(uid, coins=max(0, u["coins"] - a))
    await message.answer(f"✅ -{a}")


@dp.callback_query(F.data == "adm_setxp")
async def adm_setxp(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("✨ setxp 123 500")
    await call.answer()


@dp.message(F.text.startswith("setxp "))
async def adm_setxp_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, uid, a = message.text.split()
        uid, a = int(uid), int(a)
    except:
        await message.answer("❌ setxp 123 500")
        return
    await get_user(uid)
    await update_user(uid, xp=a)
    await message.answer(f"✅ XP {a}")


@dp.callback_query(F.data == "adm_crystals")
async def adm_crystals(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("💎 crystal 123 5")
    await call.answer()


@dp.message(F.text.startswith("crystal "))
async def adm_crystal_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, uid, a = message.text.split()
        uid, a = int(uid), int(a)
    except:
        await message.answer("❌ crystal 123 5")
        return
    u = await get_user(uid)
    await update_user(uid, crystals=u["crystals"] + a)
    await message.answer(f"✅ +{a}💎")


@dp.callback_query(F.data == "adm_ban")
async def adm_ban(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("🚫 ban 123")
    await call.answer()


@dp.message(F.text.startswith("ban "))
async def adm_ban_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, uid = message.text.split()
        uid = int(uid)
    except:
        await message.answer("❌ ban 123")
        return
    await get_user(uid)
    await update_user(uid, banned=1)
    await message.answer("🚫 Забанен.")


@dp.callback_query(F.data == "adm_unban")
async def adm_unban(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("✅ unban 123")
    await call.answer()


@dp.message(F.text.startswith("unban "))
async def adm_unban_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, uid = message.text.split()
        uid = int(uid)
    except:
        await message.answer("❌ unban 123")
        return
    await get_user(uid)
    await update_user(uid, banned=0)
    await message.answer("✅ Разбанен.")


@dp.callback_query(F.data == "adm_giveitem")
async def adm_giveitem(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("🎁 item 123 🎩 Цилиндр")
    await call.answer()


@dp.message(F.text.startswith("item "))
async def adm_giveitem_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ item 123 Название")
        return
    try:
        uid = int(parts[1]); item = parts[2]
    except:
        await message.answer("❌ Ошибка")
        return
    u = await get_user(uid)
    inv = [i for i in u["inventory"].split(",") if i]
    inv.append(item)
    await update_user(uid, inventory=",".join(inv))
    await message.answer(f"✅ {item}")


@dp.callback_query(F.data == "adm_close")
async def adm_close(call: CallbackQuery):
    await call.message.delete()
    await call.answer()


# ============ VERCEL HANDLER ============

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
            import traceback
            traceback.print_exc()
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"error: {e}".encode())
