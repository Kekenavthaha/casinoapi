import hashlib
import hmac
import json
import random
import os
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

def update_user_balance(user_id: int, username: str, delta: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id, username, score, daily_earned) VALUES (?, ?, 0, 0)", (user_id, username))
    cursor.execute("UPDATE users SET score = score + ? WHERE user_id = ?", (delta, user_id))
    if delta > 0:
        cursor.execute("UPDATE users SET daily_earned = daily_earned + ? WHERE user_id = ?", (delta, user_id))
    conn.commit()
    conn.close()

# Остальные функции (spin_slots, calc_slots_win, get_jackpot, update_jackpot, spin_roulette, calc_roulette_win, roll_dice, DICE_ODDS) должны быть здесь полностью, как в твоём исходном файле. Я опускаю их для краткости, но они ОБЯЗАТЕЛЬНЫ.

@app.route("/api/casino/init", methods=["POST"])
def init_casino():
    user_data, error_response, status = get_telegram_user()
    if error_response:
        return error_response, status
    user_id = user_data["id"]
    username = user_data.get("username") or user_data.get("first_name", "Player")
    update_user_balance(user_id, username, 0)
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
    update_user_balance(user_id, username, -bet)
    jackpot_fee = int(bet * 0.02)
    if jackpot_fee > 0:
        update_jackpot(jackpot_fee)
    # ... логика игр (как в исходнике) ...
    return jsonify(result)

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# Vercel требует, чтобы приложение экспортировалось как `app`