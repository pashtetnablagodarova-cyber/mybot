import asyncio
import random
import time
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup
)

BOT_TOKEN = "8865006313:AAH6eQwsM1IufGWyo2_58MX_L2wVH7snknk"
DB = "game.db"

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
                inventory TEXT DEFAULT ''
            )
        """)
        await db.commit()


async def get_user(user_id, name="Игрок"):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO users (user_id, name) VALUES (?, ?)",
                (user_id, name)
            )
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
        [InlineKeyboardButton(text="👤 Я", callback_data="me")],
        [InlineKeyboardButton(text="🏆 Топ", callback_data="top")],
        [InlineKeyboardButton(text="🎁 Кейсы", callback_data="cases")],
        [InlineKeyboardButton(text="💎 Бонус", callback_data="bonus")],
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
        reply_markup=main_menu(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "menu")
async def menu(call: CallbackQuery):
    await call.message.edit_text("🎩 Главное меню:", reply_markup=main_menu())
    await call.answer()


@dp.callback_query(F.data == "me")
async def me(call: CallbackQuery):
    u = await get_user(call.from_user.id, call.from_user.first_name or "Игрок")
    _, name, coins, xp, cases, _, inv = u
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

    text = "🏆 <b>Топ игроков по балансу:</b>\n\n"
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
        [InlineKeyboardButton(text="🎁 Кейс 1 — 1000 💰", callback_data="case1")],
        [InlineKeyboardButton(text="🎁 Кейс 2 — 5000 💰", callback_data="case2")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")],
    ])
    await call.message.edit_text("🎁 Выбери кейс:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "case1")
async def case1(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    coins, xp, cases_opened = u[2], u[3], u[4]
    if coins < 1000:
        await call.answer("Недостаточно монет!", show_alert=True)
        return

    roll = random.randint(1, 100)
    if roll <= 40:
        result, coins = "💰 +100 монет", coins + 100 - 1000
    elif roll <= 55:
        result, xp = "✨ +20 опыта", xp + 20
        coins -= 1000
    elif roll <= 90:
        result, coins = "💰 +700 монет", coins + 700 - 1000
    else:
        result, xp = "✨ +50 опыта", xp + 50
        coins -= 1000

    await update_user(call.from_user.id, coins=coins, xp=xp, cases_opened=cases_opened + 1)
    await call.message.edit_text(f"🎁 Кейс 1 открыт!\n\n{result}\n\n💰 Баланс: {coins}",
                                 reply_markup=back_menu())
    await call.answer()


@dp.callback_query(F.data == "case2")
async def case2(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    coins, xp, cases_opened, inv = u[2], u[3], u[4], u[6]
    if coins < 5000:
        await call.answer("Недостаточно монет!", show_alert=True)
        return

    roll = random.randint(1, 100)
    inv_list = [i for i in inv.split(",") if i]

    if roll <= 10:
        inv_list.append("Цилиндр")
        result = "🎩 Цилиндр (1500 💰)"
    elif roll <= 20:
        inv_list.append("Палочка волшебника")
        result = "🪄 Палочка волшебника (1500 💰)"
    elif roll <= 40:
        result = "😢 Неудача — ничего"
    elif roll <= 45:
        inv_list.append("Магическая пыль")
        result = "✨ Магическая пыль (8000 💰)"
    else:
        inv_list.append("Магия")
        result = "🔮 Магия (1000 💰)"

    coins -= 5000
    await update_user(call.from_user.id, coins=coins, xp=xp,
                      cases_opened=cases_opened + 1, inventory=",".join(inv_list))
    await call.message.edit_text(f"🎁 Кейс 2 открыт!\n\n{result}\n\n💰 Баланс: {coins}",
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
    await update_user(call.from_user.id, coins=coins + 100, xp=xp + 50, last_bonus=now)
    await call.message.edit_text(
        f"🎉 Ежедневный бонус получен!\n\n💰 +100 монет\n✨ +50 опыта\n\nБаланс: {coins + 100}",
        reply_markup=back_menu()
    )
    await call.answer()


@dp.callback_query(F.data == "earn")
async def earn(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Угадайка (1 💰)", callback_data="guess")],
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
        await call.answer("Игра не найдена. Начни заново.", show_alert=True)
        return

    if n == target:
        await update_user(call.from_user.id, coins=u[2] + 10)
        text = f"🎉 Угадал! Это было число {target}.\n💰 +10 монет"
    else:
        text = f"😢 Не угадал. Было число {target}."

    guess_numbers.pop(call.from_user.id, None)
    await call.message.edit_text(text, reply_markup=back_menu())
    await call.answer()


upgrade_state = {}


@dp.callback_query(F.data == "upgrade")
async def upgrade_start(call: CallbackQuery):
    u = await get_user(call.from_user.id)
    inv = [i for i in u[6].split(",") if i]
    if not inv:
        await call.answer("У тебя пустой инвентарь!", show_alert=True)
        return

    buttons = [[InlineKeyboardButton(text=item, callback_data=f"upg_{idx}")]
               for idx, item in enumerate(inv)]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="earn")])
    await call.message.edit_text("⚡ Выбери предмет для апгрейда:",
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()


@dp.callback_query(F.data.startswith("upg_"))
async def upgrade_pick(call: CallbackQuery):
    idx = int(call.data.split("_")[1])
    u = await get_user(call.from_user.id)
    inv = [i for i in u[6].split(",") if i]
    if idx >= len(inv):
        await call.answer("Предмет не найден", show_alert=True)
        return

    upgrade_state[call.from_user.id] = {"item": inv[idx], "inv_idx": idx}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="×2", callback_data="upg_x_2"),
         InlineKeyboardButton(text="×3", callback_data="upg_x_3")],
        [InlineKeyboardButton(text="×5", callback_data="upg_x_5"),
         InlineKeyboardButton(text="×10", callback_data="upg_x_10")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="upgrade")],
    ])
    await call.message.edit_text(f"⚡ Предмет: {inv[idx]}\nВыбери множитель:", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("upg_x_"))
async def upgrade_do(call: CallbackQuery):
    mult = int(call.data.split("_")[-1])
    state = upgrade_state.get(call.from_user.id)
    if not state:
        await call.answer("Ошибка, начни заново", show_alert=True)
        return

    chances = {2: 60, 3: 40, 5: 25, 10: 10}
    u = await get_user(call.from_user.id)
    inv = [i for i in u[6].split(",") if i]

    if random.randint(1, 100) <= chances[mult]:
        reward = 1500 * mult
        inv.pop(state["inv_idx"])
        await update_user(call.from_user.id, coins=u[2] + reward, inventory=",".join(inv))
        text = f"🎉 Успех! ×{mult}\n💰 +{reward} монет\nПредмет сгорел."
    else:
        inv.pop(state["inv_idx"])
        await update_user(call.from_user.id, inventory=",".join(inv))
        text = f"💥 Провал на ×{mult}. Предмет потерян."

    upgrade_state.pop(call.from_user.id, None)
    await call.message.edit_text(text, reply_markup=back_menu())
    await call.answer()


async def main():
    await init_db()
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
