import sqlite3
import os
import hashlib
import secrets
import datetime
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("skyrex_auth_db")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USERS_DB_PATH = os.path.join(PROJECT_ROOT, "users.db")

def get_auth_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(USERS_DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def init_auth_db():
    """Initializes tables for real server-side users, sessions, and subscriptions."""
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                subscribed INTEGER NOT NULL DEFAULT 0,
                subscription_expires TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)
        
        # 3. Verification codes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                email TEXT PRIMARY KEY COLLATE NOCASE,
                code TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 3. Create default admin user if not exists
        admin = cursor.execute("SELECT id FROM users WHERE email = 'admin@skyrex.ru'").fetchone()
        if not admin:
            salt = secrets.token_hex(16)
            pwd_hash = hash_password("admin123", salt)
            expires = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)).isoformat()
            cursor.execute("""
                INSERT INTO users (email, password_hash, salt, role, subscribed, subscription_expires)
                VALUES ('admin@skyrex.ru', ?, ?, 'admin', 1, ?)
            """, (pwd_hash, salt, expires))
            logger.info("Created default admin user: admin@skyrex.ru")
            
        conn.commit()

def hash_password(password: str, salt: str) -> str:
    """Secure PBKDF2-HMAC-SHA256 password hashing."""
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()

def save_verification_code(email: str, password: str, code: str, expires_minutes: int = 10) -> Dict[str, Any]:
    """Saves pending registration verification code with hashed password."""
    email = email.strip().lower()
    if not email or "@" not in email:
        return {"success": False, "error": "Некорректный email адрес."}
    if len(password) < 6:
        return {"success": False, "error": "Пароль должен содержать минимум 6 символов."}

    init_auth_db()
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        existing = cursor.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return {"success": False, "error": "Пользователь с таким email уже зарегистрирован."}

        salt = secrets.token_hex(16)
        pwd_hash = hash_password(password, salt)
        expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=expires_minutes)).isoformat()

        cursor.execute("""
            INSERT OR REPLACE INTO verification_codes (email, code, password_hash, salt, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (email, code, pwd_hash, salt, expires_at))
        conn.commit()

    return {"success": True}

def verify_code_and_register(email: str, code: str) -> Dict[str, Any]:
    """Validates code from database and registers the user."""
    email = email.strip().lower()
    code = code.strip()

    init_auth_db()
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        record = cursor.execute("SELECT * FROM verification_codes WHERE email = ?", (email,)).fetchone()
        if not record:
            return {"success": False, "error": "Запрос на регистрацию не найден. Запросите код повторно."}

        # Check expiration
        try:
            exp_dt = datetime.datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
            if datetime.datetime.now(datetime.timezone.utc) > exp_dt:
                cursor.execute("DELETE FROM verification_codes WHERE email = ?", (email,))
                conn.commit()
                return {"success": False, "error": "Срок действия кода истёк. Запросите новый."}
        except Exception:
            pass

        if record["code"] != code:
            return {"success": False, "error": "Неверный код подтверждения."}

        # Register user into users table
        try:
            cursor.execute("""
                INSERT INTO users (email, password_hash, salt, role, subscribed, subscription_expires)
                VALUES (?, ?, ?, 'user', 0, NULL)
            """, (email, record["password_hash"], record["salt"]))
            user_id = cursor.lastrowid
            # Clean up verification code
            cursor.execute("DELETE FROM verification_codes WHERE email = ?", (email,))
            conn.commit()
        except sqlite3.IntegrityError:
            return {"success": False, "error": "Пользователь с таким email уже существует."}

    token = create_session(user_id)
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user_id,
            "email": email,
            "role": "user",
            "subscribed": False,
            "subscriptionExpires": None
        }
    }


def login_user(email: str, password: str) -> Dict[str, Any]:
    """Authenticates user with email and password."""
    email = email.strip().lower()
    init_auth_db()
    
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        user = cursor.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            return {"success": False, "error": "Неверный email или пароль."}
            
        calc_hash = hash_password(password, user["salt"])
        if calc_hash != user["password_hash"]:
            return {"success": False, "error": "Неверный email или пароль."}
            
        token = create_session(user["id"])
        
        # Check active subscription
        is_sub = bool(user["subscribed"])
        sub_exp = user["subscription_expires"]
        if is_sub and sub_exp:
            try:
                exp_dt = datetime.datetime.fromisoformat(sub_exp.replace("Z", "+00:00"))
                if datetime.datetime.now(datetime.timezone.utc) > exp_dt:
                    is_sub = False
                    cursor.execute("UPDATE users SET subscribed = 0 WHERE id = ?", (user["id"],))
                    conn.commit()
            except Exception:
                pass
                
        return {
            "success": True,
            "token": token,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "role": user["role"],
                "subscribed": is_sub,
                "subscriptionExpires": sub_exp
            }
        }

def create_session(user_id: int) -> str:
    """Creates a secure 30-day session token."""
    token = secrets.token_hex(32)
    expires = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).isoformat()
    
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, user_id, expires))
        conn.commit()
    return token

def get_user_by_token(token: str) -> Optional[Dict[str, Any]]:
    """Validates session token and returns active user profile."""
    if not token:
        return None
        
    init_auth_db()
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        row = cursor.execute("""
            SELECT s.expires_at, u.id, u.email, u.role, u.subscribed, u.subscription_expires
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token = ?
        """, (token,)).fetchone()
        
        if not row:
            return None
            
        # Check session expiry
        try:
            exp_dt = datetime.datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if datetime.datetime.now(datetime.timezone.utc) > exp_dt:
                cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                return None
        except Exception:
            return None
            
        # Check subscription expiry
        is_sub = bool(row["subscribed"])
        sub_exp = row["subscription_expires"]
        if is_sub and sub_exp:
            try:
                sub_dt = datetime.datetime.fromisoformat(sub_exp.replace("Z", "+00:00"))
                if datetime.datetime.now(datetime.timezone.utc) > sub_dt:
                    is_sub = False
                    cursor.execute("UPDATE users SET subscribed = 0 WHERE id = ?", (row["id"],))
                    conn.commit()
            except Exception:
                pass
                
        return {
            "id": row["id"],
            "email": row["email"],
            "role": row["role"],
            "subscribed": is_sub,
            "subscriptionExpires": sub_exp
        }

def logout_token(token: str):
    """Deletes active session token."""
    if not token:
        return
    with get_auth_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()

def activate_subscription(user_id: int, days: int = 30) -> Dict[str, Any]:
    """Activates/extends premium subscription for user."""
    expires = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)).isoformat()
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET subscribed = 1, subscription_expires = ? WHERE id = ?", (expires, user_id))
        conn.commit()
        user = cursor.execute("SELECT id, email, role, subscribed, subscription_expires FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(user)
