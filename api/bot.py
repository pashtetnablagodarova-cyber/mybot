import os
import random
import time
import asyncpg
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8865006313:AAH6eQwsM1IufGWyo2_58MX_L2wVH7snknk")
DATABASE_URL = os.getenv("DATABASE_URL", "")
CHANNEL_URL = "https://t.me/randomkanews"
ADMIN_ID = 8006016784

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

db_pool = None
broadcast_state = {"waiting": False}


async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
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
                "INSERT INTO users (user_id, name) VALUES ($1, $2)",
                user_id, name
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
        reply_markup=main_reply_menu(), parse_mode="HTML"
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
        f"💰 Баланс: <b>{u['coins']}</b> фокусов\n"
        f"💎 Кристаллы: <b>{u['crystals']}</b>\n"
        f"🏅 Место в топе: <b>#{place}</b>\n"
        f"🔥 Стрик: <b>{u['streak']}</b> дней (всего {u['streak_total']})\n"
        f"📅 Сезонный XP: <b>{u['season_xp']}</b>\n"
        f"🎁 Открыто кейсов: {u['cases_opened']}\n\n"
        f"🎒 Инвентарь: {', '.join(inv_list) if inv_list else 'пусто'}"
    )
    await message.answer(text, parse_mode="HTML")


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
        rows = await conn.fetch(
            "SELECT name, coins, xp FROM users WHERE banned=0 ORDER BY coins DESC LIMIT 10"
        )
    text = "🌍 <b>Топ за всё время:</b>\n\n"
    for i, r in enumerate(rows, 1):
        lvl, _, _ = level_from_xp(r["xp"])
        text += f"{i}. {r['name']} — 💰{r['coins']} | 🎚{lvl} lvl\n"

    text += "\n🎚 <b>Топ по уровню:</b>\n\n"
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT name, coins, xp FROM users WHERE banned=0 ORDER BY xp DESC LIMIT 10"
        )
    for i, r in enumerate(rows, 1):
        lvl, _, _ = level_from_xp(r["xp"])
        text += f"{i}. {r['name']} — 🎚{lvl} lvl | 💰{r['coins']}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 За всё время", callback_data="top_all")],
        [InlineKeyboardButton(text="📅 Сезон", callback_data="top_season")],
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "top_season")
async def top_season(call: CallbackQuery):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT name, season_xp FROM users WHERE banned=0 ORDER BY season_xp DESC LIMIT 10"
        )
    text = "📅 <b>Топ сезона (бета):</b>\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. {r['name']} — ⭐ {r['season_xp']}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 За всё время", callback_data="top_all")],
        [InlineKeyboardButton(text="📅 Сезон", callback_data="top_season")],
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
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
        await call.answer("🚫 Ты забанен.", show_alert=True)
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
        xp += 40
        coins -= 500
        result = "✨ +40 опыта"
    elif roll <= 85:
        coins += 800 - 500
        result = "🪙 +800 монет"
    elif roll <= 95:
        inv_list.append("🃏 Карта фокусника")
        coins -= 500
        result = "🃏 Карта фокусника (1500 💰)"
    else:
        inv_list.append("🔮 Малый амулет")
        coins -= 500
        result = "🔮 Малый амулет (3000 💰)"

    await update_user(call.from_user.id, coins=coins, xp=xp,
                      cases_opened=u["cases_opened"] + 1,
                      inventory=",".join(inv_list))
    await call.message.edit_text(f"🎁 Кейс новичка открыт!\n\n{result}\n\n💰 Баланс: {coins}")
    await call.answer()


@dp.callback_query(F.data == "case2")
async def case2(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    if u["banned"] == 1:
        await call.answer("🚫 Ты забанен.", show_alert=True)
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
        xp += 120
        coins -= 2500
        result = "✨ +120 опыта"
    elif roll <= 65:
        inv_list.append("🎩 Цилиндр")
        coins -= 2500
        result = "🎩 Цилиндр (4000 💰)"
    elif roll <= 80:
        inv_list.append("🪄 Палочка волшебника")
        coins -= 2500
        result = "🪄 Палочка волшебника (4000 💰)"
    elif roll <= 90:
        inv_list.append("🃏 Карта фокусника")
        coins -= 2500
        result = "🃏 Карта фокусника (1500 💰)"
    elif roll <= 97:
        inv_list.append("🔮 Хрустальный шар")
        coins -= 2500
        result = "🔮 Хрустальный шар (7000 💰)"
    else:
        inv_list.append("💎 Магический кристалл")
        coins -= 2500
        result = "💎 Магический кристалл (15000 💰)"

    await update_user(call.from_user.id, coins=coins, xp=xp,
                      cases_opened=u["cases_opened"] + 1,
                      inventory=",".join(inv_list))
    await call.message.edit_text(f"🎁 Кейс фокусника открыт!\n\n{result}\n\n💰 Баланс: {coins}")
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
        await message.answer("⏳ Ты уже получал награду сегодня. Возвращайся завтра!")
        return

    streak_val = u["streak"] + 1 if last_day == today - 1 else 1
    streak_total = u["streak_total"] + 1
    day = ((streak_val - 1) % 7) + 1
    reward_coins, reward_xp = streak_reward(day)
    crystals = u["crystals"]
    bonus_text = ""
    if streak_total == 30:
        reward_coins += 10000
        crystals += 1
        bonus_text = "\n\n🎉 <b>30 дней!</b>\n💰 +10 000\n💎 +1 кристалл"
    elif streak_total == 100:
        reward_coins += 50000
        crystals += 3
        bonus_text = "\n\n🎉 <b>100 дней!</b>\n💰 +50 000\n💎 +3 кристалла"
    elif streak_total == 365:
        reward_coins += 500000
        crystals += 10
        bonus_text = "\n\n🎉 <b>Год!</b>\n💰 +500 000\n💎 +10 кристаллов"

    item_text = ""
    inv_list = [i for i in u["inventory"].split(",") if i]
    if day == 7:
        item = random.choice(["🃏 Карта фокусника", "🎩 Цилиндр", "🪄 Палочка волшебника"])
        inv_list.append(item)
        item_text = f"\n🎁 Предмет: {item}"

    await update_user(message.from_user.id,
                      coins=u["coins"] + reward_coins,
                      xp=u["xp"] + reward_xp,
                      streak=streak_val, last_streak=now,
                      streak_total=streak_total, crystals=crystals,
                      inventory=",".join(inv_list))
    await message.answer(
        f"🔥 <b>Стрик: день {streak_val}</b>\n\n"
        f"💰 +{reward_coins} монет\n✨ +{reward_xp} опыта"
        f"{item_text}{bonus_text}", parse_mode="HTML"
    )


@dp.message(F.text == "📰 Новости")
async def news(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📰 Перейти в канал", url=CHANNEL_URL)]
    ])
    await message.answer("📰 Все новости — в канале:", reply_markup=kb)


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
        [InlineKeyboardButton(text="🎡 Рулетка фокусника", callback_data="roulette")],
        [InlineKeyboardButton(text="⚡ Апгрейдер", callback_data="upgrade")],
    ])
    await message.answer("💰 Выбери способ заработка:", reply_markup=kb)


guess_numbers = {}
hat_games = {}
roulette_state = {}
upgrade_state = {}


@dp.callback_query(F.data == "guess")
async def guess_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    if u["coins"] < 1:
        await call.answer("Нужна хотя бы 1 монета!", show_alert=True)
        return
    await update_user(call.from_user.id, coins=u["coins"] - 1)
    guess_numbers[call.from_user.id] = random.randint(1, 5)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(i), callback_data=f"gnum_{i}") for i in range(1, 6)],
    ])
    await call.message.edit_text("🎲 Угадай число от 1 до 5:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("gnum_"))
async def guess_answer(call: CallbackQuery):
    n = int(call.data.split("_")[1])
    target = guess_numbers.get(call.from_user.id)
    u = await get_user(call.from_user.id)
    if target is None:
        await call.answer("Игра не найдена", show_alert=True)
        return
    if n == target:
        await update_user(call.from_user.id, coins=u["coins"] + 5)
        text = f"🎉 Угадал! Число {target}.\n💰 +5 монет"
    else:
        text = f"😢 Не угадал. Было {target}."
    guess_numbers.pop(call.from_user.id, None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Играть ещё (1 💰)", callback_data="guess")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "hat")
async def hat_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    now = int(time.time())
    hat_count = u["hat_count"]
    if now - u["last_hat"] > 3600:
        await update_user(call.from_user.id, hat_count=0, last_hat=now)
        hat_count = 0
    if hat_count >= 5:
        left = 3600 - (now - u["last_hat"])
        m = left // 60
        await call.answer(f"Лимит: 5 раз/час. Жди {m} мин", show_alert=True)
        return
    hat_games[call.from_user.id] = random.randint(0, 2)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎩 1", callback_data="hat_0"),
         InlineKeyboardButton(text="🎩 2", callback_data="hat_1"),
         InlineKeyboardButton(text="🎩 3", callback_data="hat_2")],
    ])
    await call.message.edit_text("🎩 Под какой шляпой шарик?", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("hat_"))
async def hat_answer(call: CallbackQuery):
    choice = int(call.data.split("_")[1])
    target = hat_games.get(call.from_user.id)
    u = await get_user(call.from_user.id)
    if target is None:
        await call.answer("Игра не найдена", show_alert=True)
        return
    if choice == target:
        await update_user(call.from_user.id, coins=u["coins"] + 5, hat_count=u["hat_count"] + 1)
        text = "🎉 Угадал! +5 монет"
    else:
        await update_user(call.from_user.id, hat_count=u["hat_count"] + 1)
        text = f"😢 Не угадал. Шарик был под шляпой {target + 1}."
    hat_games.pop(call.from_user.id, None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎩 Ещё раз", callback_data="hat")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


dealer_cards = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


@dp.callback_query(F.data == "dealer")
async def dealer_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    now = int(time.time())
    dealer_count = u["dealer_count"]
    if now - u["last_dealer"] > 86400:
        await update_user(call.from_user.id, dealer_count=0, last_dealer=now)
        dealer_count = 0
    if dealer_count >= 3:
        await call.answer("Лимит: 3 раза/день.", show_alert=True)
        return
    player = random.choice(dealer_cards)
    dealer = random.choice(dealer_cards)
    values = {c: i for i, c in enumerate(dealer_cards)}
    if values[player] > values[dealer]:
        await update_user(call.from_user.id, coins=u["coins"] + 10, dealer_count=u["dealer_count"] + 1)
        text = f"🃏 Ты: {player} | Дилер: {dealer}\n\n🎉 Победа! +10 монет"
    elif values[player] < values[dealer]:
        await update_user(call.from_user.id, dealer_count=u["dealer_count"] + 1)
        text = f"🃏 Ты: {player} | Дилер: {dealer}\n\n😢 Дилер выиграл."
    else:
        await update_user(call.from_user.id, dealer_count=u["dealer_count"] + 1)
        text = f"🃏 Ты: {player} | Дилер: {dealer}\n\n🤝 Ничья!"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Ещё раз", callback_data="dealer")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "roulette")
async def roulette_start(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Красное (×2)", callback_data="rl_red")],
        [InlineKeyboardButton(text="⚫ Чёрное (×2)", callback_data="rl_black")],
        [InlineKeyboardButton(text="🟢 Зелёное (×14)", callback_data="rl_green")],
    ])
    await call.message.edit_text("🎡 Выбери цвет:", reply_markup=kb)
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
    await call.message.edit_text(f"🎡 Ты выбрал: {color}\nВыбери ставку:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("rbet_"))
async def roulette_bet(call: CallbackQuery):
    bet = int(call.data.split("_")[1])
    state = roulette_state.get(call.from_user.id)
    if not state:
        await call.answer("Сначала выбери цвет", show_alert=True)
        return
    u = await get_user(call.from_user.id)
    if u["coins"] < bet:
        await call.answer("Недостаточно монет!", show_alert=True)
        return
    roll = random.randint(1, 100)
    if roll <= 45:
        landed = "red"
    elif roll <= 90:
        landed = "black"
    else:
        landed = "green"
    if landed == state["color"]:
        reward = bet * 14 if landed == "green" else bet * 2
        await update_user(call.from_user.id, coins=u["coins"] - bet + reward)
        text = f"🎡 Выпало: {landed}\n\n🎉 Выигрыш! +{reward} монет"
    else:
        await update_user(call.from_user.id, coins=u["coins"] - bet)
        text = f"🎡 Выпало: {landed}\n\n😢 Проигрыш. -{bet} монет"
    roulette_state.pop(call.from_user.id, None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎡 Ещё раз", callback_data="roulette")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "upgrade")
async def upgrade_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    inv = [i for i in u["inventory"].split(",") if i]
    if not inv:
        await call.answer("Инвентарь пуст!", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(text=item, callback_data=f"upg_{idx}")] for idx, item in enumerate(inv)]
    await call.message.edit_text("⚡ Выбери предмет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()


@dp.callback_query(F.data.startswith("upg_"))
async def upgrade_pick(call: CallbackQuery):
    idx = int(call.data.split("_")[1])
    u = await get_user(call.from_user.id)
    inv = [i for i in u["inventory"].split(",") if i]
    if idx >= len(inv):
        await call.answer("Не найден", show_alert=True)
        return
    upgrade_state[call.from_user.id] = {"inv_idx": idx}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="×2 (60%)", callback_data="upg_x_2"),
         InlineKeyboardButton(text="×3 (40%)", callback_data="upg_x_3")],
        [InlineKeyboardButton(text="×5 (25%)", callback_data="upg_x_5"),
         InlineKeyboardButton(text="×10 (10%)", callback_data="upg_x_10")],
    ])
    await call.message.edit_text(f"⚡ {inv[idx]}\nВыбери множитель:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("upg_x_"))
async def upgrade_do(call: CallbackQuery):
    mult = int(call.data.split("_")[-1])
    state = upgrade_state.get(call.from_user.id)
    if not state:
        await call.answer("Ошибка", show_alert=True)
        return
    chances = {2: 60, 3: 40, 5: 25, 10: 10}
    u = await get_user(call.from_user.id)
    inv = [i for i in u["inventory"].split(",") if i]
    if random.randint(1, 100) <= chances[mult]:
        reward = 1000 * mult
        inv.pop(state["inv_idx"])
        await update_user(call.from_user.id, coins=u["coins"] + reward, inventory=",".join(inv))
        text = f"🎉 Успех ×{mult}!\n💰 +{reward} монет"
    else:
        inv.pop(state["inv_idx"])
        await update_user(call.from_user.id, inventory=",".join(inv))
        text = f"💥 Провал ×{mult}. Предмет потерян."
    upgrade_state.pop(call.from_user.id, None)
    await call.message.edit_text(text)


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="💰 Выдать монеты", callback_data="adm_give")],
        [InlineKeyboardButton(text="💸 Забрать монеты", callback_data="adm_take")],
        [InlineKeyboardButton(text="✨ Установить XP", callback_data="adm_setxp")],
        [InlineKeyboardButton(text="💎 Выдать кристаллы", callback_data="adm_crystals")],
        [InlineKeyboardButton(text="🚫 Забанить", callback_data="adm_ban")],
        [InlineKeyboardButton(text="✅ Разбанить", callback_data="adm_unban")],
        [InlineKeyboardButton(text="🎁 Выдать предмет", callback_data="adm_giveitem")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="adm_close")],
    ])


@dp.message(F.text == "/admin")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_menu(), parse_mode="HTML")


@dp.callback_query(F.data == "adm_stats")
async def adm_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) as t, SUM(coins) as c, SUM(xp) as x, SUM(cases_opened) as cs FROM users")
        banned = await conn.fetchval("SELECT COUNT(*) FROM users WHERE banned=1")
    text = (f"📊 <b>Статистика</b>\n\n"
            f"👥 Игроков: <b>{row['t'] or 0}</b>\n"
            f"🚫 Забанено: <b>{banned or 0}</b>\n"
            f"💰 Монет: <b>{row['c'] or 0}</b>\n"
            f"✨ Опыта: <b>{row['x'] or 0}</b>\n"
            f"🎁 Кейсов: <b>{row['cs'] or 0}</b>")
    await call.message.edit_text(text, reply_markup=admin_menu(), parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    broadcast_state["waiting"] = True
    await call.message.edit_text("📢 Отправь текст рассылки.\n/cancel — отмена")
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
    await message.answer(f"📢 Готово!\n✅ {sent}\n❌ {failed}")


@dp.callback_query(F.data == "adm_give")
async def adm_give(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("💰 <code>give 123456789 1000</code>", parse_mode="HTML")
    await call.answer()


@dp.message(F.text.startswith("give "))
async def adm_give_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, uid, amount = message.text.split()
        uid, amount = int(uid), int(amount)
    except Exception:
        await message.answer("❌ Формат: give 123456789 1000")
        return
    u = await get_user(uid)
    await update_user(uid, coins=u["coins"] + amount)
    await message.answer(f"✅ +{amount} монет игроку {uid}.")


@dp.callback_query(F.data == "adm_take")
async def adm_take(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("💸 <code>take 123456789 1000</code>", parse_mode="HTML")
    await call.answer()


@dp.message(F.text.startswith("take "))
async def adm_take_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, uid, amount = message.text.split()
        uid, amount = int(uid), int(amount)
    except Exception:
        await message.answer("❌ Формат: take 123456789 1000")
        return
    u = await get_user(uid)
    new = max(0, u["coins"] - amount)
    await update_user(uid, coins=new)
    await message.answer(f"✅ -{amount}. Баланс: {new}")


@dp.callback_query(F.data == "adm_setxp")
async def adm_setxp(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("✨ <code>setxp 123456789 500</code>", parse_mode="HTML")
    await call.answer()


@dp.message(F.text.startswith("setxp "))
async def adm_setxp_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, uid, amount = message.text.split()
        uid, amount = int(uid), int(amount)
    except Exception:
        await message.answer("❌ Формат: setxp 123456789 500")
        return
    await get_user(uid)
    await update_user(uid, xp=amount)
    await message.answer(f"✅ XP = {amount}.")


@dp.callback_query(F.data == "adm_crystals")
async def adm_crystals(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("💎 <code>crystal 123456789 5</code>", parse_mode="HTML")
    await call.answer()


@dp.message(F.text.startswith("crystal "))
async def adm_crystal_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, uid, amount = message.text.split()
        uid, amount = int(uid), int(amount)
    except Exception:
        await message.answer("❌ Формат: crystal 123456789 5")
        return
    u = await get_user(uid)
    await update_user(uid, crystals=u["crystals"] + amount)
    await message.answer(f"✅ +{amount} кристаллов игроку {uid}.")


@dp.callback_query(F.data == "adm_ban")
async def adm_ban(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("🚫 <code>ban 123456789</code>", parse_mode="HTML")
    await call.answer()


@dp.message(F.text.startswith("ban "))
async def adm_ban_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, uid = message.text.split()
        uid = int(uid)
    except Exception:
        await message.answer("❌ Формат: ban 123456789")
        return
    await get_user(uid)
    await update_user(uid, banned=1)
    await message.answer(f"🚫 {uid} забанен.")


@dp.callback_query(F.data == "adm_unban")
async def adm_unban(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("✅ <code>unban 123456789</code>", parse_mode="HTML")
    await call.answer()


@dp.message(F.text.startswith("unban "))
async def adm_unban_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, uid = message.text.split()
        uid = int(uid)
    except Exception:
        await message.answer("❌ Формат: unban 123456789")
        return
    await get_user(uid)
    await update_user(uid, banned=0)
    await message.answer(f"✅ {uid} разбанен.")


@dp.callback_query(F.data == "adm_giveitem")
async def adm_giveitem(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("🎁 <code>item 123456789 🎩 Цилиндр</code>", parse_mode="HTML")
    await call.answer()


@dp.message(F.text.startswith("item "))
async def adm_giveitem_exec(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ Формат: item 123456789 🎩 Цилиндр")
        return
    try:
        uid = int(parts[1])
        item = parts[2]
    except Exception:
        await message.answer("❌ Формат неверный")
        return
    u = await get_user(uid)
    inv = [i for i in u["inventory"].split(",") if i]
    inv.append(item)
    await update_user(uid, inventory=",".join(inv))
    await message.answer(f"✅ Выдан «{item}» игроку {uid}.")


@dp.callback_query(F.data == "adm_close")
async def adm_close(call: CallbackQuery):
    await call.message.delete()
    await call.answer()
