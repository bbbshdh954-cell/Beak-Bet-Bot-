import telebot
import time
import re
import logging
import sqlite3
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading
import os

# =====================================================
# НАСТРОЙКА
# =====================================================
TOKEN = "8916707885:AAGTRtepfBl4X64JTkyUThWvyGXHezrGF44"
bot = telebot.TeleBot(TOKEN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

users = {}
user_states = {}
temp_data = {}

ADMINS = [8435638438]

# =====================================================
# БАЗА ДАННЫХ
# =====================================================
DB_NAME = "users.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0,
            games INTEGER DEFAULT 0,
            turnover REAL DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT balance, games, turnover FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    if result:
        conn.close()
        return {"balance": result[0], "games": result[1], "turnover": result[2]}
    else:
        cursor.execute('INSERT INTO users (user_id, balance, games, turnover) VALUES (?, 0, 0, 0)', (user_id,))
        conn.commit()
        conn.close()
        return {"balance": 0.0, "games": 0, "turnover": 0.0}

def update_user(user_id, balance=None, games=None, turnover=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if balance is not None:
        cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (balance, user_id))
    if games is not None:
        cursor.execute('UPDATE users SET games = ? WHERE user_id = ?', (games, user_id))
    if turnover is not None:
        cursor.execute('UPDATE users SET turnover = ? WHERE user_id = ?', (turnover, user_id))
    conn.commit()
    conn.close()

init_db()

# =====================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================
def format_amount(amount):
    if amount == int(amount):
        return str(int(amount))
    return f"{amount:.2f}"

def get_user_link(user_id, name):
    return f"[{name}](tg://user?id={user_id})"

def get_user_name(user):
    if user.first_name:
        return user.first_name
    return "Пользователь"

def safe_edit(chat_id, message_id, text, reply_markup=None):
    try:
        bot.edit_message_text(
            text,
            chat_id,
            message_id,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return True
    except:
        return False

def safe_delete(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass

# =====================================================
# МЕНЮ ИГР
# =====================================================
def games_menu(message, amount=None, result_text=None, reply_to_msg_id=None):
    user_id = message.from_user.id
    name = message.from_user.first_name
    user_link = get_user_link(user_id, name)
    user_data = get_user(user_id)
    
    if amount is None:
        amount = user_states.get(user_id, {}).get("amount", 0.1)
    
    balance = user_data["balance"]
    formatted_amount = format_amount(amount)
    formatted_balance = format_amount(balance)
    
    if result_text:
        main_text = result_text
    else:
        main_text = (
            f"{user_link}, *Выберите игру, на которую хотите сделать ставку!*\n\n"
            f"➕ *Ставка:* *{formatted_amount}* 💲\n"
            f"💰 *Баланс:* *{formatted_balance}* 💲"
        )
    
    markup = InlineKeyboardMarkup(row_width=3)
    row1 = [
        InlineKeyboardButton("🎲 (до х216)", callback_data=f"game_cube_{amount}"),
        InlineKeyboardButton("⚽️ (до x2.5)", callback_data=f"game_football_{amount}"),
        InlineKeyboardButton("🏀 (до х5)", callback_data=f"game_basket_{amount}")
    ]
    markup.row(*row1)
    row2 = [
        InlineKeyboardButton("🎯 (до х6)", callback_data=f"game_darts_{amount}"),
        InlineKeyboardButton("🎳 (до x6)", callback_data=f"game_bowling_{amount}"),
        InlineKeyboardButton("🎰 (до х64)", callback_data=f"game_slots_{amount}")
    ]
    markup.row(*row2)
    row3 = [
        InlineKeyboardButton("©️ Авторские", callback_data=f"game_author_{amount}")
    ]
    markup.row(*row3)
    
    if reply_to_msg_id:
        bot.send_message(
            message.chat.id,
            main_text,
            parse_mode='Markdown',
            reply_markup=markup,
            reply_to_message_id=reply_to_msg_id
        )
    else:
        bot.send_message(
            message.chat.id,
            main_text,
            parse_mode='Markdown',
            reply_markup=markup
        )

# =====================================================
# АДМИН-ПАНЕЛЬ
# =====================================================
def admin_menu(message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Выдать", callback_data="admin_give"),
        InlineKeyboardButton("➖ Снять", callback_data="admin_take")
    )
    bot.send_message(message.chat.id, "👑 *Админ панель*", parse_mode='Markdown', reply_markup=markup)

# =====================================================
# БАСКЕТБОЛ МЕНЮ
# =====================================================
def basket_menu(call, amount):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    balance = user_data["balance"]
    markup = InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        InlineKeyboardButton("Чистый гол (x5)", callback_data=f"basket_clean_{amount}"),
        InlineKeyboardButton("Любой гол (x2.5)", callback_data=f"basket_any_{amount}")
    )
    markup.add(
        InlineKeyboardButton("Застрял мяч (x5)", callback_data=f"basket_stuck_{amount}"),
        InlineKeyboardButton("Промах (x1.65)", callback_data=f"basket_miss_{amount}")
    )
    markup.row(InlineKeyboardButton("🔙 Назад", callback_data=f"basket_back_{amount}"))
    
    text = f"🏀 *Выберите исход игры!*\n\n➕ *Ставка:* *{format_amount(amount)}* 💲\n💰 *Баланс:* *{format_amount(balance)}* 💲"
    
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        text,
        markup
    )
    bot.answer_callback_query(call.id)

# =====================================================
# ФУТБОЛ МЕНЮ
# =====================================================
def football_menu(call, amount):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    balance = user_data["balance"]
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("⚽️ Гол (x1.6)", callback_data=f"football_goal_{amount}"),
        InlineKeyboardButton("⚽️ Промах (x2.5)", callback_data=f"football_miss_{amount}")
    )
    markup.row(InlineKeyboardButton("🔙 Назад", callback_data=f"football_back_{amount}"))
    
    text = f"⚽️ *Выберите исход игры!*\n\n➕ *Ставка:* *{format_amount(amount)}* 💲\n💰 *Баланс:* *{format_amount(balance)}* 💲"
    
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        text,
        markup
    )
    bot.answer_callback_query(call.id)

# =====================================================
# ДАРТС МЕНЮ
# =====================================================
def darts_menu(call, amount):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    balance = user_data["balance"]
    
    markup = InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        InlineKeyboardButton("Прямо в центр (x6)", callback_data=f"darts_center_{amount}"),
        InlineKeyboardButton("Красный сектор (x2)", callback_data=f"darts_red_{amount}")
    )
    
    markup.add(
        InlineKeyboardButton("Белый сектор (x3)", callback_data=f"darts_white_{amount}"),
        InlineKeyboardButton("Отскок дротика (x6)", callback_data=f"darts_bounce_{amount}")
    )
    
    markup.add(
        InlineKeyboardButton("< Назад", callback_data=f"darts_back_{amount}")
    )
    
    text = f"🎯 *Выберите исход игры!*\n\n➕ *Ставка:* *{format_amount(amount)}* 💲\n💰 *Баланс:* *{format_amount(balance)}* 💲"
    
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        text,
        markup
    )
    bot.answer_callback_query(call.id)

# =====================================================
# МЕНЮ 2 БРОСКА
# =====================================================
def two_rolls_menu(call, amount):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    balance = user_data["balance"]
    
    markup = InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        InlineKeyboardButton("Оба чётных (x4)", callback_data=f"tworolls_botheven_{amount}"),
        InlineKeyboardButton("Оба нечёт (x4)", callback_data=f"tworolls_bothodd_{amount}")
    )
    
    markup.add(
        InlineKeyboardButton("Оба меньше (x4)", callback_data=f"tworolls_bothless_{amount}"),
        InlineKeyboardButton("Оба больше (x4)", callback_data=f"tworolls_bothmore_{amount}")
    )
    
    markup.add(
        InlineKeyboardButton("Любой дубль (x6)", callback_data=f"tworolls_anydouble_{amount}")
    )
    
    markup.add(
        InlineKeyboardButton("Точный дубль (до x36)", callback_data=f"tworolls_exactdouble_{amount}")
    )
    
    markup.add(
        InlineKeyboardButton("Произведения 18+ (x4.5)", callback_data=f"tworolls_product18_{amount}")
    )
    
    markup.add(
        InlineKeyboardButton("< Назад", callback_data=f"tworolls_back_{amount}")
    )
    
    text = f"🎲 *Выберите исход игры!*\n\n➕ *Ставка:* *{format_amount(amount)}* 💲\n💰 *Баланс:* *{format_amount(balance)}* 💲"
    
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        text,
        markup
    )
    bot.answer_callback_query(call.id)

# =====================================================
# КУБИК МЕНЮ
# =====================================================
def cube_menu(call, amount):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    balance = user_data["balance"]
    
    markup = InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        InlineKeyboardButton("2 Броска (до x36)", callback_data=f"cube_2rolls_{amount}"),
        InlineKeyboardButton("3 Броска (до x216)", callback_data=f"cube_3rolls_{amount}")
    )
    
    markup.add(
        InlineKeyboardButton("Чёт (x2)", callback_data=f"cube_even_{amount}"),
        InlineKeyboardButton("Нечёт (x2)", callback_data=f"cube_odd_{amount}")
    )
    
    markup.add(
        InlineKeyboardButton("Меньше (x2)", callback_data=f"cube_less_{amount}"),
        InlineKeyboardButton("Больше (x2)", callback_data=f"cube_more_{amount}")
    )
    
    markup.row(
        InlineKeyboardButton("1 (x6)", callback_data=f"cube_1_{amount}"),
        InlineKeyboardButton("2 (x6)", callback_data=f"cube_2_{amount}"),
        InlineKeyboardButton("3 (x6)", callback_data=f"cube_3_{amount}")
    )
    
    markup.row(
        InlineKeyboardButton("4 (x6)", callback_data=f"cube_4_{amount}"),
        InlineKeyboardButton("5 (x6)", callback_data=f"cube_5_{amount}"),
        InlineKeyboardButton("6 (x6)", callback_data=f"cube_6_{amount}")
    )
    
    markup.add(
        InlineKeyboardButton("Лесенка (x2.2)", callback_data=f"cube_ladder_{amount}")
    )
    
    markup.add(
        InlineKeyboardButton("< Назад", callback_data=f"cube_back_{amount}")
    )
    
    text = f"🎲 *Выберите исход игры!*\n\n➕ *Ставка:* *{format_amount(amount)}* 💲\n💰 *Баланс:* *{format_amount(balance)}* 💲"
    
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        text,
        markup
    )
    bot.answer_callback_query(call.id)

# =====================================================
# ОБРАБОТЧИК ДАРТС
# =====================================================
def process_darts_bet(call, bet_type, amount):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    balance = user_data["balance"]
    
    if amount > balance:
        bot.answer_callback_query(call.id, f"❌ Недостаточно средств! Баланс: {format_amount(balance)} $", show_alert=True)
        return
    
    user_data["balance"] -= amount
    update_user(user_id, balance=user_data["balance"])
    update_user(user_id, games=user_data["games"] + 1)
    user_data["games"] += 1
    update_user(user_id, turnover=user_data["turnover"] + amount)
    user_data["turnover"] += amount
    
    name = get_user_name(call.from_user)
    
    bet_configs = {
        "center": {"name": "Прямо в центр", "coef": 6, "win_values": [6]},
        "red": {"name": "Красный сектор", "coef": 2, "win_values": [1, 2, 3, 4, 5]},
        "white": {"name": "Белый сектор", "coef": 3, "win_values": [4, 5]},
        "bounce": {"name": "Отскок дротика", "coef": 6, "win_values": [1, 2]}
    }
    
    config = bet_configs.get(bet_type)
    if not config:
        return
    
    bot.answer_callback_query(call.id)
    
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        f"{name} ставит *{format_amount(amount)}* 💲\n🎯 Дартс - {config['name']}",
        None
    )
    
    time.sleep(0.5)
    
    msg = bot.send_dice(call.message.chat.id, '🎯')
    time.sleep(2.5)
    v = msg.dice.value
    time.sleep(0.3)
    
    coef = config['coef']
    win = v in config['win_values']
    
    if win:
        win_amount = round(amount * coef, 2)
        win_after_commission = round(win_amount * 0.94, 2)
        user_data["balance"] += win_after_commission
        update_user(user_id, balance=user_data["balance"])
        
        result_text = (
            f"{name}, ⏫ *Выигрывает* *{format_amount(win_after_commission)}* 💲\n"
            f"*Ставка* *{format_amount(amount)}* $ × *{coef}*\n\n"
            f"➕ *Ставка:* *{format_amount(amount)}* 💲\n"
            f"💰 *Баланс:* *{format_amount(user_data['balance'])}* 💲"
        )
        
        class FakeMessage:
            def __init__(self, chat_id, from_user):
                self.chat = type('obj', (object,), {'id': chat_id})
                self.from_user = from_user
        
        fake_msg = FakeMessage(call.message.chat.id, type('obj', (object,), {'id': user_id, 'first_name': name}))
        games_menu(fake_msg, amount, result_text, reply_to_msg_id=msg.message_id)
    else:
        result_text = (
            f"{name}, ⏬ *Проигрывает* *{format_amount(amount)}* 💲\n"
            f"*Ставка* *{format_amount(amount)}* $ × *{coef}*\n\n"
            f"➕ *Ставка:* *{format_amount(amount)}* 💲\n"
            f"💰 *Баланс:* *{format_amount(user_data['balance'])}* 💲"
        )
        
        class FakeMessage:
            def __init__(self, chat_id, from_user):
                self.chat = type('obj', (object,), {'id': chat_id})
                self.from_user = from_user
        
        fake_msg = FakeMessage(call.message.chat.id, type('obj', (object,), {'id': user_id, 'first_name': name}))
        games_menu(fake_msg, amount, result_text, reply_to_msg_id=msg.message_id)

# =====================================================
# ОБРАБОТЧИК 2 БРОСКОВ
# =====================================================
def process_two_rolls_bet(call, bet_type, amount):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    balance = user_data["balance"]
    
    if amount > balance:
        bot.answer_callback_query(call.id, f"❌ Недостаточно средств! Баланс: {format_amount(balance)} $", show_alert=True)
        return
    
    user_data["balance"] -= amount
    update_user(user_id, balance=user_data["balance"])
    update_user(user_id, games=user_data["games"] + 1)
    user_data["games"] += 1
    update_user(user_id, turnover=user_data["turnover"] + amount)
    user_data["turnover"] += amount
    
    name = get_user_name(call.from_user)
    
    bet_configs = {
        "botheven": {
            "name": "Оба чётных",
            "coef": 4,
            "win_func": lambda d1, d2: d1 % 2 == 0 and d2 % 2 == 0
        },
        "bothodd": {
            "name": "Оба нечёт",
            "coef": 4,
            "win_func": lambda d1, d2: d1 % 2 != 0 and d2 % 2 != 0
        },
        "bothless": {
            "name": "Оба меньше",
            "coef": 4,
            "win_func": lambda d1, d2: d1 <= 3 and d2 <= 3
        },
        "bothmore": {
            "name": "Оба больше",
            "coef": 4,
            "win_func": lambda d1, d2: d1 >= 4 and d2 >= 4
        },
        "anydouble": {
            "name": "Любой дубль",
            "coef": 6,
            "win_func": lambda d1, d2: d1 == d2
        },
        "exactdouble": {
            "name": "Точный дубль",
            "coef": 36,
            "win_func": lambda d1, d2: d1 == d2
        },
        "product18": {
            "name": "Произведения 18+",
            "coef": 4.5,
            "win_func": lambda d1, d2: d1 * d2 >= 18
        }
    }
    
    config = bet_configs.get(bet_type)
    if not config:
        return
    
    bot.answer_callback_query(call.id)
    
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        f"{name} ставит *{format_amount(amount)}* 💲\n🎲 2 Броска - {config['name']}",
        None
    )
    
    time.sleep(0.3)
    
    msg1 = bot.send_dice(call.message.chat.id, '🎲')
    time.sleep(0.2)
    msg2 = bot.send_dice(call.message.chat.id, '🎲')
    time.sleep(1.5)
    
    d1 = msg1.dice.value
    d2 = msg2.dice.value
    
    time.sleep(0.3)
    
    coef = config['coef']
    win = config['win_func'](d1, d2)
    
    if win:
        win_amount = round(amount * coef, 2)
        win_after_commission = round(win_amount * 0.94, 2)
        user_data["balance"] += win_after_commission
        update_user(user_id, balance=user_data["balance"])
        
        result_text = (
            f"{name}, ⏫ *Выигрывает* *{format_amount(win_after_commission)}* 💲\n"
            f"*Ставка* *{format_amount(amount)}* $ × *{coef}*\n\n"
            f"➕ *Ставка:* *{format_amount(amount)}* 💲\n"
            f"💰 *Баланс:* *{format_amount(user_data['balance'])}* 💲"
        )
        
        class FakeMessage:
            def __init__(self, chat_id, from_user):
                self.chat = type('obj', (object,), {'id': chat_id})
                self.from_user = from_user
        
        fake_msg = FakeMessage(call.message.chat.id, type('obj', (object,), {'id': user_id, 'first_name': name}))
        games_menu(fake_msg, amount, result_text, reply_to_msg_id=msg1.message_id)
    else:
        result_text = (
            f"{name}, ⏬ *Проигрывает* *{format_amount(amount)}* 💲\n"
            f"*Ставка* *{format_amount(amount)}* $ × *{coef}*\n\n"
            f"➕ *Ставка:* *{format_amount(amount)}* 💲\n"
            f"💰 *Баланс:* *{format_amount(user_data['balance'])}* 💲"
        )
        
        class FakeMessage:
            def __init__(self, chat_id, from_user):
                self.chat = type('obj', (object,), {'id': chat_id})
                self.from_user = from_user
        
        fake_msg = FakeMessage(call.message.chat.id, type('obj', (object,), {'id': user_id, 'first_name': name}))
        games_menu(fake_msg, amount, result_text, reply_to_msg_id=msg1.message_id)

# =====================================================
# ОБРАБОТЧИК СТАВОК ДЛЯ КУБИКА
# =====================================================
def process_cube_bet(call, bet_type, amount):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    balance = user_data["balance"]
    
    if amount > balance:
        bot.answer_callback_query(call.id, f"❌ Недостаточно средств! Баланс: {format_amount(balance)} $", show_alert=True)
        return
    
    user_data["balance"] -= amount
    update_user(user_id, balance=user_data["balance"])
    update_user(user_id, games=user_data["games"] + 1)
    user_data["games"] += 1
    update_user(user_id, turnover=user_data["turnover"] + amount)
    user_data["turnover"] += amount
    
    name = get_user_name(call.from_user)
    
    if bet_type == "2rolls":
        two_rolls_menu(call, amount)
        return
    
    if bet_type == "3rolls":
        bot.answer_callback_query(call.id)
        safe_edit(
            call.message.chat.id,
            call.message.message_id,
            f"*3 Броска*\n\nСкоро будет доступно!",
            None
        )
        return
    
    LADDER_COEFS = {
        1: 0.1,
        2: 0.2,
        3: 0.5,
        4: 1.2,
        5: 1.5,
        6: 2.2
    }
    
    bet_configs = {
        "even": {"name": "Чёт", "coef": 2, "win_func": lambda v: v in [2, 4, 6]},
        "odd": {"name": "Нечет", "coef": 2, "win_func": lambda v: v in [1, 3, 5]},
        "less": {"name": "Меньше", "coef": 2, "win_func": lambda v: v in [1, 2, 3]},
        "more": {"name": "Больше", "coef": 2, "win_func": lambda v: v in [4, 5, 6]},
        "1": {"name": "1", "coef": 6, "win_func": lambda v: v == 1},
        "2": {"name": "2", "coef": 6, "win_func": lambda v: v == 2},
        "3": {"name": "3", "coef": 6, "win_func": lambda v: v == 3},
        "4": {"name": "4", "coef": 6, "win_func": lambda v: v == 4},
        "5": {"name": "5", "coef": 6, "win_func": lambda v: v == 5},
        "6": {"name": "6", "coef": 6, "win_func": lambda v: v == 6},
        "ladder": {"name": "Лесенка", "coef": None, "win_func": lambda v: v in [1, 2, 3, 4, 5, 6]},
    }
    
    config = bet_configs.get(bet_type)
    if not config:
        return
    
    bot.answer_callback_query(call.id)
    
    if bet_type == "ladder":
        safe_edit(
            call.message.chat.id,
            call.message.message_id,
            f"{name} ставит *{format_amount(amount)}* 💲\n🎲 Кубик - Лесенка (x2.2)",
            None
        )
    else:
        safe_edit(
            call.message.chat.id,
            call.message.message_id,
            f"{name} ставит *{format_amount(amount)}* 💲\n🎲 Кубик - {config['name']}",
            None
        )
    
    time.sleep(0.5)
    
    msg = bot.send_dice(call.message.chat.id, '🎲')
    time.sleep(2.5)
    v = msg.dice.value
    time.sleep(0.3)
    
    if bet_type == "ladder":
        coef = LADDER_COEFS.get(v, 0.1)
        win = True
    else:
        coef = config['coef']
        win = config['win_func'](v)
    
    if win:
        win_amount = round(amount * coef, 2)
        win_after_commission = round(win_amount * 0.94, 2)
        user_data["balance"] += win_after_commission
        update_user(user_id, balance=user_data["balance"])
        
        if bet_type == "ladder":
            bet_name = f"Лесенка (x{coef})"
        else:
            bet_name = config['name']
        
        result_text = (
            f"{name}, ⏫ *Выигрывает* *{format_amount(win_after_commission)}* 💲\n"
            f"*Ставка* *{format_amount(amount)}* $ × *{coef}*\n\n"
            f"➕ *Ставка:* *{format_amount(amount)}* 💲\n"
            f"💰 *Баланс:* *{format_amount(user_data['balance'])}* 💲"
        )
        
        class FakeMessage:
            def __init__(self, chat_id, from_user):
                self.chat = type('obj', (object,), {'id': chat_id})
                self.from_user = from_user
        
        fake_msg = FakeMessage(call.message.chat.id, type('obj', (object,), {'id': user_id, 'first_name': name}))
        games_menu(fake_msg, amount, result_text, reply_to_msg_id=msg.message_id)
    else:
        result_text = (
            f"{name}, ⏬ *Проигрывает* *{format_amount(amount)}* 💲\n"
            f"*Ставка* *{format_amount(amount)}* $ × *{coef}*\n\n"
            f"➕ *Ставка:* *{format_amount(amount)}* 💲\n"
            f"💰 *Баланс:* *{format_amount(user_data['balance'])}* 💲"
        )
        
        class FakeMessage:
            def __init__(self, chat_id, from_user):
                self.chat = type('obj', (object,), {'id': chat_id})
                self.from_user = from_user
        
        fake_msg = FakeMessage(call.message.chat.id, type('obj', (object,), {'id': user_id, 'first_name': name}))
        games_menu(fake_msg, amount, result_text, reply_to_msg_id=msg.message_id)

# =====================================================
# ОБРАБОТЧИК СТАВОК ДЛЯ ФУТБОЛА И БАСКЕТБОЛА
# =====================================================
def process_bet(call, game_type, bet_type, amount):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    balance = user_data["balance"]
    
    if amount > balance:
        bot.answer_callback_query(call.id, f"❌ Недостаточно средств! Баланс: {format_amount(balance)} $", show_alert=True)
        return
    
    user_data["balance"] -= amount
    update_user(user_id, balance=user_data["balance"])
    update_user(user_id, games=user_data["games"] + 1)
    user_data["games"] += 1
    update_user(user_id, turnover=user_data["turnover"] + amount)
    user_data["turnover"] += amount
    
    name = get_user_name(call.from_user)
    
    game_configs = {
        "football": {
            "emoji": "⚽️",
            "name": "Футбол",
            "dice": "⚽",
            "timeout": 3.5,
            "coefs": {"goal": 1.6, "miss": 2.5},
            "win_conditions": {"goal": [3, 4, 5], "miss": [1, 2]}
        },
        "basket": {
            "emoji": "🏀",
            "name": "Баскетбол",
            "dice": "🏀",
            "timeout": 2.5,
            "coefs": {"clean": 5.0, "any": 2.5, "stuck": 5.0, "miss": 1.65},
            "win_conditions": {"clean": [5], "any": [4, 5], "stuck": [3], "miss": [1, 2]}
        }
    }
    
    config = game_configs.get(game_type)
    if not config:
        return
    
    bet_texts = {
        "goal": "Гол", "miss": "Промах",
        "clean": "Чистый гол", "any": "Любой гол",
        "stuck": "Застрял мяч"
    }
    bet_type_text = bet_texts.get(bet_type, bet_type)
    
    bot.answer_callback_query(call.id)
    
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        f"{name} ставит *{format_amount(amount)}* 💲\n{config['emoji']} {config['name']} - {bet_type_text}",
        None
    )
    
    time.sleep(0.5)
    
    msg = bot.send_dice(call.message.chat.id, config['dice'])
    time.sleep(config['timeout'])
    
    v = msg.dice.value
    coef = config['coefs'].get(bet_type, 1.0)
    win_condition = config['win_conditions'].get(bet_type, [])
    win = v in win_condition
    
    time.sleep(0.3)
    
    if win:
        win_amount = round(amount * coef, 2)
        win_after_commission = round(win_amount * 0.94, 2)
        user_data["balance"] += win_after_commission
        update_user(user_id, balance=user_data["balance"])
        
        result_text = (
            f"{name}, ⏫ *Выигрывает* *{format_amount(win_after_commission)}* 💲\n"
            f"*Ставка* *{format_amount(amount)}* $ × *{coef}*\n\n"
            f"➕ *Ставка:* *{format_amount(amount)}* 💲\n"
            f"💰 *Баланс:* *{format_amount(user_data['balance'])}* 💲"
        )
        
        class FakeMessage:
            def __init__(self, chat_id, from_user):
                self.chat = type('obj', (object,), {'id': chat_id})
                self.from_user = from_user
        
        fake_msg = FakeMessage(call.message.chat.id, type('obj', (object,), {'id': user_id, 'first_name': name}))
        games_menu(fake_msg, amount, result_text, reply_to_msg_id=msg.message_id)
    else:
        result_text = (
            f"{name}, ⏬ *Проигрывает* *{format_amount(amount)}* 💲\n"
            f"*Ставка* *{format_amount(amount)}* $ × *{coef}*\n\n"
            f"➕ *Ставка:* *{format_amount(amount)}* 💲\n"
            f"💰 *Баланс:* *{format_amount(user_data['balance'])}* 💲"
        )
        
        class FakeMessage:
            def __init__(self, chat_id, from_user):
                self.chat = type('obj', (object,), {'id': chat_id})
                self.from_user = from_user
        
        fake_msg = FakeMessage(call.message.chat.id, type('obj', (object,), {'id': user_id, 'first_name': name}))
        games_menu(fake_msg, amount, result_text, reply_to_msg_id=msg.message_id)

# =====================================================
# ОСНОВНОЙ ОБРАБОТЧИК ВСЕХ CALLBACK
# =====================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call: CallbackQuery):
    try:
        user_id = call.from_user.id
        data = call.data
        
        if data.startswith('darts_back_'):
            amount = float(data.split('_')[2])
            bot.answer_callback_query(call.id)
            class FakeMessage:
                def __init__(self, chat_id, from_user):
                    self.chat = type('obj', (object,), {'id': chat_id})
                    self.from_user = from_user
            fake_msg = FakeMessage(call.message.chat.id, call.from_user)
            games_menu(fake_msg, amount, reply_to_msg_id=call.message.message_id)
            return
        
        if data.startswith('darts_'):
            parts = data.split('_')
            bet_type = parts[1]
            amount = float(parts[2])
            process_darts_bet(call, bet_type, amount)
            return
        
        if data.startswith('tworolls_back_'):
            amount = float(data.split('_')[2])
            bot.answer_callback_query(call.id)
            class FakeMessage:
                def __init__(self, chat_id, from_user):
                    self.chat = type('obj', (object,), {'id': chat_id})
                    self.from_user = from_user
            fake_msg = FakeMessage(call.message.chat.id, call.from_user)
            cube_menu(fake_msg, amount)
            return
        
        if data.startswith('tworolls_'):
            parts = data.split('_')
            bet_type = parts[1]
            amount = float(parts[2])
            process_two_rolls_bet(call, bet_type, amount)
            return
        
        if data.startswith('cube_back_'):
            amount = float(data.split('_')[2])
            bot.answer_callback_query(call.id)
            class FakeMessage:
                def __init__(self, chat_id, from_user):
                    self.chat = type('obj', (object,), {'id': chat_id})
                    self.from_user = from_user
            fake_msg = FakeMessage(call.message.chat.id, call.from_user)
            games_menu(fake_msg, amount, reply_to_msg_id=call.message.message_id)
            return
        
        if data.startswith('cube_'):
            parts = data.split('_')
            bet_type = parts[1]
            amount = float(parts[2])
            process_cube_bet(call, bet_type, amount)
            return
        
        if data.startswith('basket_back_'):
            amount = float(data.split('_')[2])
            bot.answer_callback_query(call.id)
            class FakeMessage:
                def __init__(self, chat_id, from_user):
                    self.chat = type('obj', (object,), {'id': chat_id})
                    self.from_user = from_user
            fake_msg = FakeMessage(call.message.chat.id, call.from_user)
            games_menu(fake_msg, amount, reply_to_msg_id=call.message.message_id)
            return
        
        if data.startswith('basket_'):
            parts = data.split('_')
            bet_type = parts[1]
            amount = float(parts[2])
            process_bet(call, "basket", bet_type, amount)
            return
        
        if data.startswith('football_back_'):
            amount = float(data.split('_')[2])
            bot.answer_callback_query(call.id)
            class FakeMessage:
                def __init__(self, chat_id, from_user):
                    self.chat = type('obj', (object,), {'id': chat_id})
                    self.from_user = from_user
            fake_msg = FakeMessage(call.message.chat.id, call.from_user)
            games_menu(fake_msg, amount, reply_to_msg_id=call.message.message_id)
            return
        
        if data.startswith('football_goal_') or data.startswith('football_miss_'):
            parts = data.split('_')
            bet_type = parts[1]
            amount = float(parts[2])
            process_bet(call, "football", bet_type, amount)
            return
        
        if data.startswith('game_'):
            parts = data.split('_')
            game = parts[1]
            amount = float(parts[2])
            user_data = get_user(user_id)
            balance = user_data["balance"]
            
            if amount > balance:
                bot.answer_callback_query(call.id, f"❌ Недостаточно средств! Баланс: {format_amount(balance)} $", show_alert=True)
                return
            
            user_states[user_id] = {"amount": amount}
            bot.answer_callback_query(call.id)
            
            if game == "football":
                football_menu(call, amount)
                return
            elif game == "basket":
                basket_menu(call, amount)
                return
            elif game == "darts":
                darts_menu(call, amount)
                return
            elif game == "cube":
                cube_menu(call, amount)
                return
            elif game == "author":
                bot.send_message(
                    call.message.chat.id,
                    f"©️ *Авторские игры*\n💰 *Ставка:* *{format_amount(amount)}* $\n\nСкоро будут доступны!",
                    parse_mode='Markdown'
                )
                return
            elif game in ["bowling", "slots"]:
                user_data["balance"] -= amount
                update_user(user_id, balance=user_data["balance"])
                update_user(user_id, games=user_data["games"] + 1)
                user_data["games"] += 1
                update_user(user_id, turnover=user_data["turnover"] + amount)
                user_data["turnover"] += amount
                
                name = get_user_name(call.from_user)
                
                game_names = {
                    "bowling": "🎳 Боулинг",
                    "slots": "🎰 Слоты"
                }
                game_name = game_names.get(game, "Игра")
                dice_emoji = game
                
                bet_msg = bot.send_message(
                    call.message.chat.id,
                    f"{name} ставит *{format_amount(amount)}* 💲\n{game_name}",
                    parse_mode='Markdown'
                )
                
                time.sleep(0.5)
                
                msg = bot.send_dice(call.message.chat.id, dice_emoji)
                
                timeouts = {"bowling": 3.5, "slots": 5}
                time.sleep(timeouts.get(game, 3))
                v = msg.dice.value
                time.sleep(0.3)
                
                win = False
                coef = 1.0
                
                if game == "bowling":
                    coef = 1.9
                    win = v == 6
                elif game == "slots":
                    coef = 16
                    win = v in [1, 22, 43, 64]
                
                safe_delete(call.message.chat.id, bet_msg.message_id)
                
                if win:
                    win_amount = round(amount * coef, 2)
                    win_after_commission = round(win_amount * 0.94, 2)
                    user_data["balance"] += win_after_commission
                    update_user(user_id, balance=user_data["balance"])
                    
                    result_text = (
                        f"{name}, ⏫ *Выигрывает* *{format_amount(win_after_commission)}* 💲\n"
                        f"*Ставка* *{format_amount(amount)}* $ × *{coef}*\n\n"
                        f"➕ *Ставка:* *{format_amount(amount)}* 💲\n"
                        f"💰 *Баланс:* *{format_amount(user_data['balance'])}* 💲"
                    )
                    
                    class FakeMessage:
                        def __init__(self, chat_id, from_user):
                            self.chat = type('obj', (object,), {'id': chat_id})
                            self.from_user = from_user
                    
                    fake_msg = FakeMessage(call.message.chat.id, type('obj', (object,), {'id': user_id, 'first_name': name}))
                    games_menu(fake_msg, amount, result_text, reply_to_msg_id=msg.message_id)
                else:
                    result_text = (
                        f"{name}, ⏬ *Проигрывает* *{format_amount(amount)}* 💲\n"
                        f"*Ставка* *{format_amount(amount)}* $ × *{coef}*\n\n"
                        f"➕ *Ставка:* *{format_amount(amount)}* 💲\n"
                        f"💰 *Баланс:* *{format_amount(user_data['balance'])}* 💲"
                    )
                    
                    class FakeMessage:
                        def __init__(self, chat_id, from_user):
                            self.chat = type('obj', (object,), {'id': chat_id})
                            self.from_user = from_user
                    
                    fake_msg = FakeMessage(call.message.chat.id, type('obj', (object,), {'id': user_id, 'first_name': name}))
                    games_menu(fake_msg, amount, result_text, reply_to_msg_id=msg.message_id)
            return
        
        if data == "to_menu":
            bot.answer_callback_query(call.id)
            class FakeMessage:
                def __init__(self, chat_id, from_user):
                    self.chat = type('obj', (object,), {'id': chat_id})
                    self.from_user = from_user
            fake_msg = FakeMessage(call.message.chat.id, call.from_user)
            games_menu(fake_msg, user_states.get(user_id, {}).get("amount", 0.1))
            return
        
        if data == "admin_give":
            if user_id not in ADMINS:
                bot.answer_callback_query(call.id, "❌ Нет прав", show_alert=True)
                return
            bot.answer_callback_query(call.id, "➕ Введите ID")
            temp_data[user_id] = {"action": "give"}
            msg = bot.send_message(call.message.chat.id, "👤 Введите Telegram ID пользователя:")
            bot.register_next_step_handler(msg, admin_get_id)
            return
        
        if data == "admin_take":
            if user_id not in ADMINS:
                bot.answer_callback_query(call.id, "❌ Нет прав", show_alert=True)
                return
            bot.answer_callback_query(call.id, "➖ Введите ID")
            temp_data[user_id] = {"action": "take"}
            msg = bot.send_message(call.message.chat.id, "👤 Введите Telegram ID пользователя:")
            bot.register_next_step_handler(msg, admin_get_id)
            return
        
        bot.answer_callback_query(call.id, "❌ Неизвестная кнопка")
        
    except Exception as e:
        logger.error(f"Ошибка в callback: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка, попробуйте снова")
        except:
            pass

# =====================================================
# АДМИН: ОБРАБОТЧИК ID
# =====================================================
def admin_get_id(message: Message):
    user_id = message.from_user.id
    try:
        target_id = int(message.text.strip())
        temp_data[user_id]["target_id"] = target_id
        user_data = get_user(target_id)
        bot.send_message(message.chat.id, f"👤 Пользователь {target_id} найден. Баланс: {format_amount(user_data['balance'])} $")
        msg = bot.send_message(message.chat.id, "💰 Введите сумму:")
        bot.register_next_step_handler(msg, admin_get_amount)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный ID! Введите число.")
        msg = bot.send_message(message.chat.id, "👤 Введите Telegram ID пользователя:")
        bot.register_next_step_handler(msg, admin_get_id)

# =====================================================
# АДМИН: ОБРАБОТЧИК СУММЫ
# =====================================================
def admin_get_amount(message: Message):
    user_id = message.from_user.id
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0!")
            msg = bot.send_message(message.chat.id, "💰 Введите сумму:")
            bot.register_next_step_handler(msg, admin_get_amount)
            return
        target_id = temp_data[user_id]["target_id"]
        action = temp_data[user_id]["action"]
        user_data = get_user(target_id)
        if action == "give":
            new_balance = user_data["balance"] + amount
            update_user(target_id, balance=new_balance)
            bot.send_message(
                message.chat.id,
                f"✅ Пользователю {target_id} выдано {format_amount(amount)}$\n💰 Новый баланс: {format_amount(new_balance)} $"
            )
        else:
            if user_data["balance"] <= amount:
                new_balance = 0
                update_user(target_id, balance=new_balance)
                bot.send_message(
                    message.chat.id,
                    f"✅ С пользователя {target_id} снято {format_amount(amount)}$\n💰 Баланс обнулён: 0$"
                )
            else:
                new_balance = user_data["balance"] - amount
                update_user(target_id, balance=new_balance)
                bot.send_message(
                    message.chat.id,
                    f"✅ С пользователя {target_id} снято {format_amount(amount)}$\n💰 Новый баланс: {format_amount(new_balance)} $"
                )
        del temp_data[user_id]
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверная сумма! Введите число.")
        msg = bot.send_message(message.chat.id, "💰 Введите сумму:")
        bot.register_next_step_handler(msg, admin_get_amount)

# =====================================================
# КОМАНДЫ
# =====================================================
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    get_user(user_id)
    games_menu(message, 0.1)

@bot.message_handler(commands=['admin'])
def admin_command(message):
    if message.from_user.id in ADMINS:
        admin_menu(message)
    else:
        bot.reply_to(message, "❌ У вас нет прав администратора")

@bot.message_handler(func=lambda message: message.text and message.text.lower() == 'играть')
def play_command(message):
    user_id = message.from_user.id
    get_user(user_id)
    amount = user_states.get(user_id, {}).get("amount", 0.1)
    games_menu(message, amount)

@bot.message_handler(func=lambda message: message.text and message.text.lower() in ['вб', 'соси', 'ебать', 'мне похуй'])
def all_in_handler(message):
    user_id = message.from_user.id
    user_data = get_user(user_id)
    amount = user_data["balance"]
    
    if amount < 0.1:
        bot.reply_to(message, "❌ Недостаточно средств для вабанка! Минимум 0.1$")
        return
    
    if amount > 250:
        amount = 250
    
    name = get_user_name(message.from_user)
    formatted_amount = format_amount(amount)
    formatted_balance = format_amount(user_data["balance"])
    
    user_states[user_id] = {"amount": amount}
    
    result_text = (
        f"{name}, 💰 *Установил ставку - ВАБАНК* 😵\n\n"
        f"➕ *Ставка:* *{formatted_amount}* 💲\n"
        f"💰 *Баланс:* *{formatted_balance}* 💲"
    )
    
    games_menu(message, amount, result_text)

@bot.message_handler(func=lambda message: message.text and re.match(r'^(\d+\.?\d*)\$?$', message.text.strip()))
def bet_amount_handler(message):
    user_id = message.from_user.id
    text = message.text.strip()
    if not text.endswith('$'):
        return
    match = re.match(r'^(\d+\.?\d*)\$?$', text)
    if not match:
        return
    amount = float(match.group(1))
    user_data = get_user(user_id)
    if amount < 0.1:
        bot.reply_to(message, "⚠️ Минимальная ставка: 0.1$")
        amount = 0.1
    elif amount > 250:
        bot.reply_to(message, "⚠️ Максимальная ставка: 250$")
        amount = 250
    elif amount > user_data["balance"]:
        bot.reply_to(message, f"⚠️ Недостаточно средств! Баланс: {format_amount(user_data['balance'])} $")
        amount = user_data["balance"]
    user_states[user_id] = {"amount": amount}
    games_menu(message, amount)

@bot.message_handler(func=lambda message: True)
def game_text_handler(message):
    user_id = message.from_user.id
    user_data = get_user(user_id)
    
    text = message.text.lower().strip()
    
    if text in ['вб', 'соси', 'ебать', 'мне похуй', 'играть', '']:
        return
    
    if re.match(r'^(\d+\.?\d*)\$?$', text):
        return
    
    match = re.match(r"([1-6]|чет|нечет|больше|меньше)", text)
    if not match:
        return
    bet = match.group(1)
    if user_id not in user_states:
        bot.send_message(message.chat.id, "❌ Сначала введите сумму ставки!")
        return
    amount = user_states[user_id]["amount"]
    balance = user_data["balance"]
    if amount > balance:
        bot.send_message(message.chat.id, f"❌ Недостаточно средств! Баланс: {format_amount(balance)} $")
        return
    user_data["balance"] -= amount
    update_user(user_id, balance=user_data["balance"])
    update_user(user_id, games=user_data["games"] + 1)
    user_data["games"] += 1
    update_user(user_id, turnover=user_data["turnover"] + amount)
    user_data["turnover"] += amount
    name = get_user_name(message.from_user)
    
    bet_names = {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6",
                 "чет": "Чёт", "нечет": "Нечёт", "больше": "Больше", "меньше": "Меньше"}
    bet_name = bet_names.get(bet, bet)
    
    bet_msg = bot.send_message(
        message.chat.id,
        f"{name} ставит *{format_amount(amount)}* 💲\n🎲 Кубик - {bet_name}",
        parse_mode='Markdown'
    )
    
    time.sleep(0.5)
    
    msg = bot.send_dice(message.chat.id, '🎲')
    time.sleep(2.5)
    v = msg.dice.value
    time.sleep(0.3)
    
    win = False
    coef = 1.0
    if bet.isdigit():
        if v == int(bet):
            win = True
            coef = 6.0
    elif bet == "чет" and v in [2, 4, 6]:
        win = True
        coef = 1.9
    elif bet == "нечет" and v in [1, 3, 5]:
        win = True
        coef = 1.9
    elif bet == "больше" and v in [4, 5, 6]:
        win = True
        coef = 1.9
    elif bet == "меньше" and v in [1, 2, 3]:
        win = True
        coef = 1.9
    
    safe_delete(message.chat.id, bet_msg.message_id)
    
    if win:
        win_amount = round(amount * coef, 2)
        win_after_commission = round(win_amount * 0.94, 2)
        user_data["balance"] += win_after_commission
        update_user(user_id, balance=user_data["balance"])
        
        result_text = (
            f"{name}, ⏫ *Выигрывает* *{format_amount(win_after_commission)}* 💲\n"
            f"*Ставка* *{format_amount(amount)}* $ × *{coef}*\n\n"
            f"➕ *Ставка:* *{format_amount(amount)}* 💲\n"
            f"💰 *Баланс:* *{format_amount(user_data['balance'])}* 💲"
        )
        
        class FakeMessage:
            def __init__(self, chat_id, from_user):
                self.chat = type('obj', (object,), {'id': chat_id})
                self.from_user = from_user
        
        fake_msg = FakeMessage(message.chat.id, type('obj', (object,), {'id': user_id, 'first_name': name}))
        games_menu(fake_msg, amount, result_text, reply_to_msg_id=msg.message_id)
    else:
        result_text = (
            f"{name}, ⏬ *Проигрывает* *{format_amount(amount)}* 💲\n"
            f"*Ставка* *{format_amount(amount)}* $ × *{coef}*\n\n"
            f"➕ *Ставка:* *{format_amount(amount)}* 💲\n"
            f"💰 *Баланс:* *{format_amount(user_data['balance'])}* 💲"
        )
        
        class FakeMessage:
            def __init__(self, chat_id, from_user):
                self.chat = type('obj', (object,), {'id': chat_id})
                self.from_user = from_user
        
        fake_msg = FakeMessage(message.chat.id, type('obj', (object,), {'id': user_id, 'first_name': name}))
        games_menu(fake_msg, amount, result_text, reply_to_msg_id=msg.message_id)

# =====================================================
# FLASK ДЛЯ RENDER
# =====================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_bot():
    print("🎲 Streak Bet запущен!")
    print("✅ Бот работает в ЛС и группах!")
    bot.infinity_polling(timeout=60, long_polling_timeout=30, skip_pending=True)

thread = threading.Thread(target=run_bot)
thread.start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
