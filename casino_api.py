import hashlib
import hmac
import json
import random
import os
from datetime import datetime
from urllib.parse import parse_qsl
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlitecloud

app = Flask(__name__)
CORS(app, origins=["https://kekenavthaha.github.io", "https://t.me", "https://web.telegram.org"])

BOT_TOKEN = "8678746666:AAH4plrQGjFpQB6OTHyFVjaBy5Ls_nW0d5k"
DB_CONN_STRING = "sqlitecloud://cbretur2vk.g4.sqlite.cloud:8860/social_credit.db?apikey=EVDJcgbetjvOo9KUEwj6H2WZPpOmD5l9U3uDQfVrOR8"

def get_db_connection():
    return sqlitecloud.connect(DB_CONN_STRING)

# --- Проверка Telegram initData ---
def verify_telegram_init_data(init_data: str) -> tuple[bool, dict | None]:
    try:
        parsed = dict(parse_qsl(init_data))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return False, None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated_hash, received_hash):
            return False, None
        user_data = json.loads(parsed["user"])
        return True, user_data
    except Exception:
        return False, None

def get_telegram_user():
    body = request.get_json()
    init_data = body.get("initData")
    is_valid, user_data = verify_telegram_init_data(init_data)
    if not is_valid:
        return None, jsonify({"detail": "Unauthorized"}), 401
    return user_data, None, None

# --- Работа с БД ---
def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT score, username FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"score": row[0], "username": row[1]}
    else:
        return {"score": 0, "username": ""}

# ✅ Обновлённая функция: баланс меняется, но daily_earned НЕ трогается
def update_user_balance(user_id: int, username: str, delta: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id, username, score, daily_earned) VALUES (?, ?, 0, 0)", (user_id, username))
    cursor.execute("UPDATE users SET score = score + ? WHERE user_id = ?", (delta, user_id))
    # НЕ трогаем daily_earned — этим займётся daily_casino_result
    conn.commit()
    conn.close()

# --- Игровая логика (слоты, рулетка, кости) ---
SYMBOLS = ['🦀', '💎', '🍒', '7', '🔔', '🍋']
WEIGHTS = [8, 10, 35, 12, 20, 15]
WEIGHTED_SYMBOLS = []
for sym, w in zip(SYMBOLS, WEIGHTS):
    WEIGHTED_SYMBOLS.extend([sym] * w)

def spin_slots():
    return [random.choice(WEIGHTED_SYMBOLS) for _ in range(3)]

def get_jackpot():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT amount FROM jackpot WHERE id=1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 1000

def update_jackpot(delta: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE jackpot SET amount = amount + ? WHERE id=1", (delta,))
    conn.commit()
    conn.close()

def calc_slots_win(symbols, bet):
    win = 0
    jackpot = False
    s1, s2, s3 = symbols
    if s1 == s2 == s3:
        if s1 == '🦀': win = bet * 50
        elif s1 == '💎': win = bet * 25
        elif s1 == '7': win = bet * 15
        else: win = bet * 5
    elif (s1 == s2 or s2 == s3 or s1 == s3) and random.random() < 0.3:
        win = bet * 2
    if not win and symbols.count('🦀') == 2 and random.random() < 0.2:
        win = bet * 3
    if symbols == ['🦀','🦀','🦀'] and random.randint(1,100) == 1:
        jackpot = True
        win += get_jackpot()
        update_jackpot(-get_jackpot())
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE jackpot SET amount = 1000 WHERE id=1")
        conn.commit()
        conn.close()
    return win, jackpot

REDS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
def spin_roulette():
    num = random.randint(0,36)
    color = 'green' if num == 0 else ('red' if num in REDS else 'black')
    return num, color

def calc_roulette_win(bet, bet_type, bet_value, num, color):
    win = 0
    if bet_type == 'straight' and num == bet_value:
        win = bet * 35
    elif bet_type == 'red' and color == 'red':
        win = bet * 2
    elif bet_type == 'black' and color == 'black':
        win = bet * 2
    elif bet_type == 'even' and num != 0 and num % 2 == 0:
        win = bet * 2
    elif bet_type == 'odd' and num % 2 == 1:
        win = bet * 2
    elif bet_type == 'dozen1' and 1 <= num <= 12:
        win = bet * 3
    elif bet_type == 'dozen2' and 13 <= num <= 24:
        win = bet * 3
    elif bet_type == 'dozen3' and 25 <= num <= 36:
        win = bet * 3
    return win

DICE_ODDS = {2:36,12:36,3:18,11:18,4:12,10:12,5:9,9:9,6:7,8:7,7:6}
def roll_dice():
    d1 = random.randint(1,6)
    d2 = random.randint(1,6)
    return d1, d2, d1+d2

# --- API эндпоинты ---
@app.route("/api/casino/init", methods=["POST"])
def init_casino():
    user_data, error_response, status = get_telegram_user()
    if error_response:
        return error_response, status
    user_id = user_data["id"]
    username = user_data.get("username") or user_data.get("first_name", "Player")
    update_user_balance(user_id, username, 0)  # создаём, если нет
    data = get_user(user_id)
    return jsonify({"balance": data["score"], "user_id": user_id})

@app.route("/api/casino/bet", methods=["POST"])
def place_bet():
    user_data, error_response, status = get_telegram_user()
    if error_response:
        return error_response, status
    user_id = user_data["id"]
    username = user_data.get("username") or user_data.get("first_name", "Player")
    body = request.get_json()
    game = body.get("game")
    bet = body.get("bet")
    extra_data = body.get("data", {})
    if bet <= 0 or bet > 500:
        return jsonify({"detail": "Bet must be between 1 and 500"}), 400
    data = get_user(user_id)
    if data["score"] < bet:
        return jsonify({"detail": "Not enough credits"}), 400

    # Списываем ставку (daily_earned не меняется)
    update_user_balance(user_id, username, -bet)
    jackpot_fee = int(bet * 0.02)
    if jackpot_fee > 0:
        update_jackpot(jackpot_fee)

    # Игровая логика
    win = 0
    result = {}
    if game == "slots":
        symbols = spin_slots()
        win, jackpot = calc_slots_win(symbols, bet)
        if win > 0:
            update_user_balance(user_id, username, win)
        result = {
            "win": win,
            "new_balance": get_user(user_id)["score"],
            "reels": symbols,
            "jackpot": jackpot
        }
    elif game == "roulette":
        num, color = spin_roulette()
        bet_type = extra_data.get("bet_type")
        bet_value = extra_data.get("bet_value")
        win = calc_roulette_win(bet, bet_type, bet_value, num, color)
        if win > 0:
            update_user_balance(user_id, username, win)
        result = {
            "win": win,
            "new_balance": get_user(user_id)["score"],
            "number": num,
            "color": color
        }
    elif game == "dice":
        guess_sum = extra_data.get("sum")
        d1, d2, total = roll_dice()
        if total == guess_sum:
            win = bet * DICE_ODDS.get(total, 4)
            update_user_balance(user_id, username, win)
        result = {
            "win": win,
            "new_balance": get_user(user_id)["score"],
            "dice1": d1,
            "dice2": d2,
            "sum": total
        }
    else:
        return jsonify({"detail": "Unknown game"}), 400

    # ✅ Записываем чистую прибыль за эту ставку в daily_casino_result
    net_profit = win - bet
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO daily_casino_result (user_id, date, net_profit)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, date) DO UPDATE SET net_profit = net_profit + ?
    """, (user_id, today, net_profit, net_profit))
    conn.commit()
    conn.close()

    return jsonify(result)

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)