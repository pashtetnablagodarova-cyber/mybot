import asyncio
import random
import time
from os import getenv
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

BOT_TOKEN = getenv("BOT_TOKEN", "8865006313:AAH6eQwsM1IufGWyo2_58MX_L2wVH7snknk")
DB = "/data/game.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                coins INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0,
                cases_opened INTEGER DEFAULT 0,
                last_bonus INTEGER DEFAULT 0,
                inventory TEXT DEFAULT '',
                last_hat INTEGER DEFAULT 0,
                hat_count INTEGER DEFAULT 0,
                last_dealer INTEGER DEFAULT 0,
                dealer_count INTEGER DEFAULT 0
            )
        """)
        await db.commit()


async def get_user(user_id, name="Игрок"):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            await db.execute("INSERT INTO users (user_id, name) VALUES (?, ?)", (user_id, name))
            await db.commit()
            cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
        return row


async def update_user(user_id, **kwargs):
    async with aiosqlite.connect(DB) as db:
        for k, v in kwargs.items():
            await db.execute(f"UPDATE users SET {k}=? WHERE user_id=?", (v, user_id))
        await db.commit()


def level_from_xp(xp):
    lvl, need, total = 1, 200, 0
    while xp >= total + need:
        total += need
        need = int(need * 1.2)
        lvl += 1
    return lvl, total, need


def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Я", callback_data="me"),
         InlineKeyboardButton(text="🏆 Топ", callback_data="top")],
        [InlineKeyboardButton(text="🎁 Кейсы", callback_data="cases"),
         InlineKeyboardButton(text="💎 Бонус", callback_data="bonus")],
        [InlineKeyboardButton(text="💰 Заработать", callback_data="earn")],
    ])


def back_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")]
    ])


@dp.message(F.text == "/start")
async def start(message: Message):
    await get_user(message.from_user.id, message.from_user.first_name or "Игрок")
    await message.answer(
        "🎩 Добро пожаловать в мир <b>Фокусов</b>!\n"
        "Зарабатывай монеты, открывай кейсы, повышай уровень.",
        reply_markup=main_menu(), parse_mode="HTML"
    )


@dp.callback_query(F.data == "menu")
async def menu(call: CallbackQuery):
    await call.message.edit_text("🎩 Главное меню:", reply_markup=main_menu())
    await call.answer()


@dp.callback_query(F.data == "me")
async def me(call: CallbackQuery):
    u = await get_user(call.from_user.id, call.from_user.first_name or "Игрок")
    _, name, coins, xp, cases, _, inv, _, _, _, _ = u
    lvl, cur_total, need = level_from_xp(xp)
    inv_list = [i for i in inv.split(",") if i]

    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE coins > ?", (coins,))
        place = (await cur.fetchone())[0] + 1

    text = (
        f"👤 <b>{name}</b>\n\n"
        f"🎚 Уровень: <b>{lvl}</b>\n"
        f"✨ Опыт: {xp - cur_total} / {need}\n"
        f"💰 Баланс: <b>{coins}</b> фокусов\n"
        f"🏅 Место в топе: <b>#{place}</b>\n"
        f"🎁 Открыто кейсов: {cases}\n\n"
        f"🎒 Инвентарь: {', '.join(inv_list) if inv_list else 'пусто'}"
    )
    await call.message.edit_text(text, reply_markup=back_menu(), parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "top")
async def top(call: CallbackQuery):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT name, coins, xp FROM users ORDER BY coins DESC LIMIT 10")
        rows = await cur.fetchall()

    text = "🏆 <b>Топ по балансу:</b>\n\n"
    for i, (name, coins, xp) in enumerate(rows, 1):
        lvl, _, _ = level_from_xp(xp)
        text += f"{i}. {name} — 💰{coins} | 🎚{lvl} lvl\n"

    text += "\n🎚 <b>Топ по уровню:</b>\n\n"
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT name, coins, xp FROM users ORDER BY xp DESC LIMIT 10")
        rows = await cur.fetchall()
    for i, (name, coins, xp) in enumerate(rows, 1):
        lvl, _, _ = level_from_xp(xp)
        text += f"{i}. {name} — 🎚{lvl} lvl | 💰{coins}\n"

    await call.message.edit_text(text, reply_markup=back_menu(), parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "cases")
async def cases(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Кейс новичка — 500 💰", callback_data="case1")],
        [InlineKeyboardButton(text="🎁 Кейс фокусника — 2500 💰", callback_data="case2")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")],
    ])
    await call.message.edit_text("🎁 Выбери кейс:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "case1")
async def case1(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    coins, xp, cases_opened, inv = u[2], u[3], u[4], u[6]
    if coins < 500:
        await call.answer("Недостаточно монет!", show_alert=True)
        return

    roll = random.randint(1, 100)
    inv_list = [i for i in inv.split(",") if i]

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
                      cases_opened=cases_opened + 1, inventory=",".join(inv_list))
    await call.message.edit_text(f"🎁 Кейс новичка открыт!\n\n{result}\n\n💰 Баланс: {coins}",
                                 reply_markup=back_menu())
    await call.answer()


@dp.callback_query(F.data == "case2")
async def case2(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    coins, xp, cases_opened, inv = u[2], u[3], u[4], u[6]
    if coins < 2500:
        await call.answer("Недостаточно монет!", show_alert=True)
        return

    roll = random.randint(1, 100)
    inv_list = [i for i in inv.split(",") if i]

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
                      cases_opened=cases_opened + 1, inventory=",".join(inv_list))
    await call.message.edit_text(f"🎁 Кейс фокусника открыт!\n\n{result}\n\n💰 Баланс: {coins}",
                                 reply_markup=back_menu())
    await call.answer()


@dp.callback_query(F.data == "bonus")
async def bonus(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    coins, xp, last = u[2], u[3], u[5]
    now = int(time.time())
    if now - last < 86400:
        left = 86400 - (now - last)
        h, m = left // 3600, (left % 3600) // 60
        await call.answer(f"Бонус доступен через {h}ч {m}мин", show_alert=True)
        return
    await update_user(call.from_user.id, coins=coins + 150, xp=xp + 50, last_bonus=now)
    await call.message.edit_text(
        f"🎉 Ежедневный бонус!\n\n💰 +150 монет\n✨ +50 опыта\n\nБаланс: {coins + 150}",
        reply_markup=back_menu()
    )
    await call.answer()


@dp.callback_query(F.data == "earn")
async def earn(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Угадайка (1 💰)", callback_data="guess")],
        [InlineKeyboardButton(text="🎩 Фокус с шариками", callback_data="hat")],
        [InlineKeyboardButton(text="🃏 Дуэль с дилером", callback_data="dealer")],
        [InlineKeyboardButton(text="🎡 Рулетка фокусника", callback_data="roulette")],
        [InlineKeyboardButton(text="⚡ Апгрейдер", callback_data="upgrade")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")],
    ])
    await call.message.edit_text("💰 Выбери способ заработка:", reply_markup=kb)
    await call.answer()


guess_numbers = {}


@dp.callback_query(F.data == "guess")
async def guess_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    if u[2] < 1:
        await call.answer("Нужна хотя бы 1 монета!", show_alert=True)
        return
    await update_user(call.from_user.id, coins=u[2] - 1)
    guess_numbers[call.from_user.id] = random.randint(1, 5)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(i), callback_data=f"gnum_{i}") for i in range(1, 6)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="earn")],
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
        await update_user(call.from_user.id, coins=u[2] + 5)
        text = f"🎉 Угадал! Число {target}.\n💰 +5 монет"
    else:
        text = f"😢 Не угадал. Было {target}."

    guess_numbers.pop(call.from_user.id, None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Играть ещё (1 💰)", callback_data="guess")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="earn")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


hat_games = {}


@dp.callback_query(F.data == "hat")
async def hat_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    now = int(time.time())
    hat_count = u[8]

    if now - u[7] > 3600:
        await update_user(call.from_user.id, hat_count=0, last_hat=now)
        hat_count = 0

    if hat_count >= 5:
        left = 3600 - (now - u[7])
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
        await update_user(call.from_user.id, coins=u[2] + 5, hat_count=u[8] + 1)
        text = "🎉 Угадал! +5 монет"
    else:
        await update_user(call.from_user.id, hat_count=u[8] + 1)
        text = f"😢 Не угадал. Шарик был под шляпой {target + 1}."

    hat_games.pop(call.from_user.id, None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎩 Ещё раз", callback_data="hat")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="earn")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


dealer_cards = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


@dp.callback_query(F.data == "dealer")
async def dealer_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    now = int(time.time())
    dealer_count = u[10]

    if now - u[9] > 86400:
        await update_user(call.from_user.id, dealer_count=0, last_dealer=now)
        dealer_count = 0

    if dealer_count >= 3:
        await call.answer("Лимит: 3 раза/день. Приходи завтра!", show_alert=True)
        return

    player = random.choice(dealer_cards)
    dealer = random.choice(dealer_cards)
    values = {c: i for i, c in enumerate(dealer_cards)}

    if values[player] > values[dealer]:
        await update_user(call.from_user.id, coins=u[2] + 10, dealer_count=u[10] + 1)
        text = f"🃏 Ты: {player} | Дилер: {dealer}\n\n🎉 Победа! +10 монет"
    elif values[player] < values[dealer]:
        await update_user(call.from_user.id, dealer_count=u[10] + 1)
        text = f"🃏 Ты: {player} | Дилер: {dealer}\n\n😢 Дилер выиграл."
    else:
        await update_user(call.from_user.id, dealer_count=u[10] + 1)
        text = f"🃏 Ты: {player} | Дилер: {dealer}\n\n🤝 Ничья!"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Ещё раз", callback_data="dealer")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="earn")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


roulette_state = {}


@dp.callback_query(F.data == "roulette")
async def roulette_start(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Красное (×2)", callback_data="rl_red")],
        [InlineKeyboardButton(text="⚫ Чёрное (×2)", callback_data="rl_black")],
        [InlineKeyboardButton(text="🟢 Зелёное (×14)", callback_data="rl_green")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="earn")],
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
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="earn")],
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
    if u[2] < bet:
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
        await update_user(call.from_user.id, coins=u[2] - bet + reward)
        text = f"🎡 Выпало: {landed}\n\n🎉 Выигрыш! +{reward} монет"
    else:
        await update_user(call.from_user.id, coins=u[2] - bet)
        text = f"🎡 Выпало: {landed}\n\n😢 Проигрыш. -{bet} монет"

    roulette_state.pop(call.from_user.id, None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎡 Ещё раз", callback_data="roulette")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="earn")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


upgrade_state = {}


@dp.callback_query(F.data == "upgrade")
async def upgrade_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    inv = [i for i in u[6].split(",") if i]
    if not inv:
        await call.answer("Инвентарь пуст!", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(text=item, callback_data=f"upg_{idx}")] for idx, item in enumerate(inv)]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="earn")])
    await call.message.edit_text("⚡ Выбери предмет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()


@dp.callback_query(F.data.startswith("upg_"))
async def upgrade_pick(call: CallbackQuery):
    idx = int(call.data.split("_")[1])
    u = await get_user(call.from_user.id)
    inv = [i for i in u[6].split(",") if i]
    if idx >= len(inv):
        await call.answer("Не найден", show_alert=True)
        return
    upgrade_state[call.from_user.id] = {"inv_idx": idx}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="×2 (60%)", callback_data="upg_x_2"),
         InlineKeyboardButton(text="×3 (40%)", callback_data="upg_x_3")],
        [InlineKeyboardButton(text="×5 (25%)", callback_data="upg_x_5"),
         InlineKeyboardButton(text="×10 (10%)", callback_data="upg_x_10")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="upgrade")],
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
    inv = [i for i in u[6].split(",") if i]

    if random.randint(1, 100) <= chances[mult]:
        reward = 1000 * mult
        inv.pop(state["inv_idx"])
        await update_user(call.from_user.id, coins=u[2] + reward, inventory=",".join(inv))
        text = f"🎉 Успех ×{mult}!\n💰 +{reward} монет"
    else:
        inv.pop(state["inv_idx"])
        await update_user(call.from_user.id, inventory=",".join(inv))
