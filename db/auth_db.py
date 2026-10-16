import sqlite3
import os
import re
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
        
        # Check if users table exists and migrate if needed
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        users_table_exists = cursor.fetchone() is not None
        
        if not users_table_exists:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    subscribed INTEGER NOT NULL DEFAULT 0,
                    subscription_expires TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        else:
            cols = [col[1].lower() for col in cursor.execute("PRAGMA table_info(users);").fetchall()]
            if "username" not in cols:
                # Migrate table to use username instead of email
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                        password_hash TEXT NOT NULL,
                        salt TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'user',
                        subscribed INTEGER NOT NULL DEFAULT 0,
                        subscription_expires TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                if "email" in cols:
                    cursor.execute("""
                        INSERT OR IGNORE INTO users_new (id, username, password_hash, salt, role, subscribed, subscription_expires, created_at)
                        SELECT id, email, password_hash, salt, role, subscribed, subscription_expires, created_at FROM users;
                    """)
                cursor.execute("DROP TABLE users;")
                cursor.execute("ALTER TABLE users_new RENAME TO users;")
                logger.info("Migrated users table to username schema.")
        
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
        
        # 3. Clean up obsolete verification_codes table
        cursor.execute("DROP TABLE IF EXISTS verification_codes;")
        
        # 4. Create or update admin user if configured via environment variables
        admin_login = (os.getenv("ADMIN_LOGIN") or os.getenv("ADMIN_USERNAME") or os.getenv("ADMIN_EMAIL") or "").strip()
        admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
        
        # Remove legacy insecure test users if present
        cursor.execute("DELETE FROM users WHERE username = 'admin@skyrex.ru' AND password_hash = ?", 
                       (hash_password("admin123", "legacy_salt_placeholder"),))
        
        if admin_login and admin_password:
            existing = cursor.execute("SELECT id FROM users WHERE username = ? COLLATE NOCASE", (admin_login,)).fetchone()
            salt = secrets.token_hex(16)
            pwd_hash = hash_password(admin_password, salt)
            if existing:
                cursor.execute("""
                    UPDATE users SET password_hash = ?, salt = ?, role = 'admin' WHERE id = ?
                """, (pwd_hash, salt, existing["id"]))
            else:
                cursor.execute("""
                    INSERT INTO users (username, password_hash, salt, role, subscribed)
                    VALUES (?, ?, ?, 'admin', 1)
                """, (admin_login, pwd_hash, salt))
            logger.info(f"Configured admin account for {admin_login}")
            
        conn.commit()

def hash_password(password: str, salt: str) -> str:
    """Secure PBKDF2-HMAC-SHA256 password hashing."""
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()

def register_user(username: str, password: str) -> Dict[str, Any]:
    """Directly registers a new user by login/username and password into users.db."""
    username = (username or "").strip()
    if not username:
        return {"success": False, "error": "Логин не может быть пустым."}
    if len(username) < 3:
        return {"success": False, "error": "Логин должен содержать минимум 3 символа."}
    if len(username) > 32:
        return {"success": False, "error": "Логин не должен превышать 32 символа."}
    if not re.match(r"^[\w\.\-]+$", username, re.UNICODE):
        return {"success": False, "error": "Логин может содержать только буквы, цифры, дефис, точку и подчеркивание."}
    if not password or len(password) < 6:
        return {"success": False, "error": "Пароль должен содержать минимум 6 символов."}

    init_auth_db()
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        existing = cursor.execute("SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        if existing:
            return {"success": False, "error": "Пользователь с таким логином уже зарегистрирован."}

        salt = secrets.token_hex(16)
        pwd_hash = hash_password(password, salt)

        try:
            cursor.execute("""
                INSERT INTO users (username, password_hash, salt, role, subscribed, subscription_expires)
                VALUES (?, ?, ?, 'user', 0, NULL)
            """, (username, pwd_hash, salt))
            user_id = cursor.lastrowid
            conn.commit()
        except sqlite3.IntegrityError:
            return {"success": False, "error": "Пользователь с таким логином уже зарегистрирован."}

    token = create_session(user_id)
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user_id,
            "username": username,
            "role": "user",
            "subscribed": False,
            "subscriptionExpires": None
        }
    }

def login_user(username: str, password: str) -> Dict[str, Any]:
    """Authenticates user with username and password against users.db."""
    username = (username or "").strip()
    if not username or not password:
        return {"success": False, "error": "Введите логин и пароль."}

    init_auth_db()
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        user = cursor.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        if not user:
            return {"success": False, "error": "Неверный логин или пароль."}

        calc_hash = hash_password(password, user["salt"])
        if calc_hash != user["password_hash"]:
            return {"success": False, "error": "Неверный логин или пароль."}

        token = create_session(user["id"])

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
                "username": user["username"],
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
            SELECT s.expires_at, u.id, u.username, u.role, u.subscribed, u.subscription_expires
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
            "username": row["username"],
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
        user = cursor.execute("SELECT id, username, role, subscribed, subscription_expires FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(user)

# Backward-compatibility stubs for legacy verification codes
def save_verification_code(email: str, password: str, code: str, expires_minutes: int = 10) -> Dict[str, Any]:
    return register_user(email, password)

def verify_code_and_register(email: str, code: str) -> Dict[str, Any]:
    return {"success": False, "error": "Email verification is deprecated. Use register_user."}
