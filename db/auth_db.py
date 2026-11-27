import sqlite3
import os
import re
import time
import hashlib
import secrets
import datetime
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, Tuple, List

logger = logging.getLogger("skyrex_auth_db")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USERS_DB_PATH = os.path.join(PROJECT_ROOT, "users.db")

_AUTH_DB_INITIALIZED = False
# In-memory session cache: token -> {"user": dict, "expires_ts": float}
_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}

def get_auth_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(USERS_DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 20000;")
    return conn

def init_auth_db(force: bool = False):
    """Initializes tables for real server-side users, sessions, and subscriptions."""
    global _AUTH_DB_INITIALIZED
    if _AUTH_DB_INITIALIZED and not force:
        return
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
                    nickname TEXT,
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
                        nickname TEXT,
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

        # Ensure nickname column exists in users table
        cols = [col[1].lower() for col in cursor.execute("PRAGMA table_info(users);").fetchall()]
        if "nickname" not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN nickname TEXT;")
            logger.info("Migrated users table: added nickname column.")
        
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);")
        
        # 3. Email verification codes table for passwordless OTP authentication
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                email TEXT PRIMARY KEY COLLATE NOCASE,
                code TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                last_sent_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_verif_email ON verification_codes(email);")

        # 4. Payments table for YooKassa transactions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                currency TEXT DEFAULT 'RUB',
                status TEXT NOT NULL,
                payment_url TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);")

        # 5. Support messages table for client-admin helpdesk
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                email TEXT NOT NULL,
                sender TEXT NOT NULL, -- 'user' or 'admin'
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_support_email ON support_messages(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_support_is_read ON support_messages(is_read);")
        
        # 6. Create or update lifetime admin user
        admin_login = (os.getenv("ADMIN_LOGIN") or os.getenv("ADMIN_USERNAME") or os.getenv("ADMIN_EMAIL") or "nicitachebotariow@yandex.ru").strip().lower()
        admin_password = os.getenv("ADMIN_PASSWORD", "Nikita97639244").strip()
        
        # Remove legacy insecure test users if present
        cursor.execute("DELETE FROM users WHERE username = 'admin@skyrex.ru' AND password_hash = ?", 
                       (hash_password("admin123", "legacy_salt_placeholder"),))
        
        if admin_login and admin_password:
            existing = cursor.execute("SELECT id FROM users WHERE username = ? COLLATE NOCASE", (admin_login,)).fetchone()
            salt = secrets.token_hex(16)
            pwd_hash = hash_password(admin_password, salt)
            lifetime_exp = "2099-12-31T23:59:59Z"
            if existing:
                cursor.execute("""
                    UPDATE users 
                    SET password_hash = ?, salt = ?, role = 'admin', subscribed = 1, subscription_expires = ?, nickname = 'Никита (Skyrex)'
                    WHERE id = ?
                """, (pwd_hash, salt, lifetime_exp, existing["id"]))
            else:
                cursor.execute("""
                    INSERT INTO users (username, nickname, password_hash, salt, role, subscribed, subscription_expires)
                    VALUES (?, 'Никита (Skyrex)', ?, ?, 'admin', 1, ?)
                """, (admin_login, pwd_hash, salt, lifetime_exp))
            logger.info(f"Configured permanent lifetime admin account for {admin_login}")
            
        conn.commit()
    _AUTH_DB_INITIALIZED = True

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
    if len(password) > 128:
        return {"success": False, "error": "Пароль не должен превышать 128 символов."}

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

    if len(password) > 128:
        return {"success": False, "error": "Пароль слишком длинный (максимум 128 символов)."}

    with get_auth_connection() as conn:
        cursor = conn.cursor()
        user = cursor.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        if not user:
            return {"success": False, "error": "Неверный логин или пароль."}

        calc_hash = hash_password(password, user["salt"])
        if not secrets.compare_digest(calc_hash, user["password_hash"]):
            return {"success": False, "error": "Неверный логин или пароль."}

        token = create_session(user["id"])

        is_sub = bool(user["subscribed"])
        sub_exp = user["subscription_expires"]
        if user["role"] == "admin" or user["username"].lower() == "nicitachebotariow@yandex.ru":
            is_sub = True
        elif is_sub and sub_exp:
            try:
                exp_dt = datetime.datetime.fromisoformat(sub_exp.replace("Z", "+00:00"))
                if datetime.datetime.now(datetime.timezone.utc) > exp_dt:
                    is_sub = False
                    cursor.execute("UPDATE users SET subscribed = 0 WHERE id = ?", (user["id"],))
                    conn.commit()
            except Exception:
                pass

        nick = user["nickname"] if "nickname" in user.keys() and user["nickname"] else (user["username"].split("@")[0] if "@" in user["username"] else user["username"])
        user_dict = {
            "id": user["id"],
            "username": user["username"],
            "nickname": nick,
            "role": user["role"],
            "subscribed": is_sub,
            "subscriptionExpires": sub_exp
        }
        _TOKEN_CACHE[token] = {"user": user_dict, "expires_ts": time.time() + 30.0}
        return {
            "success": True,
            "token": token,
            "user": user_dict
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
    """Validates session token and returns active user profile with in-memory caching."""
    if not token:
        return None

    # Ultra-fast in-memory cache lookup
    cached = _TOKEN_CACHE.get(token)
    if cached and time.time() < cached["expires_ts"]:
        return cached["user"]

    with get_auth_connection() as conn:
        cursor = conn.cursor()
        row = cursor.execute("""
            SELECT s.expires_at, u.id, u.username, u.nickname, u.role, u.subscribed, u.subscription_expires
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token = ?
        """, (token,)).fetchone()

        if not row:
            _TOKEN_CACHE.pop(token, None)
            return None

        # Check session expiry
        try:
            exp_dt = datetime.datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if datetime.datetime.now(datetime.timezone.utc) > exp_dt:
                _TOKEN_CACHE.pop(token, None)
                return None
        except Exception:
            _TOKEN_CACHE.pop(token, None)
            return None

        is_sub = bool(row["subscribed"])
        sub_exp = row["subscription_expires"]
        if row["role"] == "admin" or row["username"].lower() == "nicitachebotariow@yandex.ru":
            is_sub = True
        elif is_sub and sub_exp:
            try:
                sub_dt = datetime.datetime.fromisoformat(sub_exp.replace("Z", "+00:00"))
                if datetime.datetime.now(datetime.timezone.utc) > sub_dt:
                    is_sub = False
            except Exception:
                pass

        row_keys = row.keys()
        nick = row["nickname"] if "nickname" in row_keys and row["nickname"] else (row["username"].split("@")[0] if "@" in row["username"] else row["username"])
        user_dict = {
            "id": row["id"],
            "username": row["username"],
            "nickname": nick,
            "role": row["role"],
            "subscribed": is_sub,
            "subscriptionExpires": sub_exp
        }
        # Cache profile for 30 seconds to avoid repeating SQLite queries on hot endpoints
        _TOKEN_CACHE[token] = {"user": user_dict, "expires_ts": time.time() + 30.0}
        return user_dict

def logout_token(token: str):
    """Deletes active session token and clears cache."""
    if not token:
        return
    _TOKEN_CACHE.pop(token, None)
    with get_auth_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()

def activate_subscription(user_id: int, days: int = 30) -> Dict[str, Any]:
    """Activates/extends premium subscription for user (stacks with remaining days)."""
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        existing = cursor.execute("SELECT subscription_expires FROM users WHERE id = ?", (user_id,)).fetchone()
        base_dt = now_dt
        if existing and existing["subscription_expires"]:
            try:
                curr_exp = datetime.datetime.fromisoformat(existing["subscription_expires"].replace("Z", "+00:00"))
                if curr_exp > now_dt:
                    base_dt = curr_exp
            except Exception:
                pass

        new_expires = (base_dt + datetime.timedelta(days=days)).isoformat()
        cursor.execute("UPDATE users SET subscribed = 1, subscription_expires = ? WHERE id = ?", (new_expires, user_id))
        conn.commit()

        # Invalidate in-memory session cache for this user so changes apply immediately
        for t, val in list(_TOKEN_CACHE.items()):
            if val.get("user", {}).get("id") == user_id:
                val["user"]["subscribed"] = True
                val["user"]["subscriptionExpires"] = new_expires

        user = cursor.execute("SELECT id, username, nickname, role, subscribed, subscription_expires FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(user) if user else {}

def create_payment_record(
    payment_id: str,
    user_id: int,
    amount: int,
    currency: str = "RUB",
    status: str = "pending",
    payment_url: str = "",
    description: str = ""
) -> bool:
    """Creates a new payment transaction record."""
    try:
        with get_auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO payments (id, user_id, amount, currency, status, payment_url, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (payment_id, user_id, amount, currency, status, payment_url, description))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error creating payment record: {e}")
        return False

def update_payment_status(payment_id: str, status: str) -> Optional[Dict[str, Any]]:
    """Updates status of a payment record and returns updated payment data."""
    try:
        with get_auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE payments 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, payment_id))
            conn.commit()

            row = cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error updating payment status: {e}")
        return None

def get_payment_record(payment_id: str) -> Optional[Dict[str, Any]]:
    """Fetches payment details by YooKassa payment id."""
    try:
        with get_auth_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error fetching payment record: {e}")
        return None

def send_otp_email(to_email: str, code: str) -> Tuple[bool, Optional[str]]:
    """Sends 6-digit OTP code to user via Mail.ru SMTP."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.mail.ru").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", "").strip() or f"Skyrex Computers <{smtp_user}>"

    if not smtp_user or not smtp_pass:
        logger.error("SMTP credentials are not configured in environment.")
        return False, "Почтовый шлюз сервера временно не настроен. Свяжитесь с поддержкой."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Код подтверждения Skyrex: {code}"
    msg["From"] = smtp_from
    msg["To"] = to_email

    text_content = (
        f"Код подтверждения для входа на Skyrex Computers: {code}\n\n"
        f"Срок действия кода — 15 минут.\n"
        f"Если вы не запрашивали авторизацию, просто проигнорируйте это письмо.\n\n"
        f"---\nSkyrex Computers https://skyrex.pro"
    )

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ margin: 0; padding: 0; background-color: #0c1017; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0; }}
    .container {{ max-width: 500px; margin: 30px auto; background: #131923; border: 1px solid #1f2937; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.6); }}
    .header {{ background: linear-gradient(135deg, #0a0f1d 0%, #1e1b4b 100%); padding: 28px 20px; text-align: center; border-bottom: 2px solid #00ffcc44; }}
    .logo {{ font-size: 26px; font-weight: 800; letter-spacing: 4px; color: #00ffcc; text-transform: uppercase; margin: 0; }}
    .sublogo {{ font-size: 11px; letter-spacing: 2px; color: #94a3b8; margin-top: 4px; text-transform: uppercase; }}
    .body {{ padding: 35px 30px; text-align: center; }}
    .title {{ font-size: 20px; font-weight: 600; color: #ffffff; margin-bottom: 12px; }}
    .desc {{ font-size: 14px; color: #94a3b8; line-height: 1.6; margin-bottom: 24px; }}
    .code-box {{ background: #080d14; border: 1px solid #00ffcc88; border-radius: 10px; padding: 16px 24px; display: inline-block; margin-bottom: 24px; box-shadow: 0 0 20px rgba(0,255,204,0.18); }}
    .code {{ font-family: 'Courier New', Courier, monospace; font-size: 34px; font-weight: 800; color: #00ffcc; letter-spacing: 8px; margin: 0; }}
    .notice {{ font-size: 12px; color: #64748b; line-height: 1.5; }}
    .footer {{ background: #080d14; padding: 18px; text-align: center; font-size: 11px; color: #475569; border-top: 1px solid #1e293b; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo">SKYREX</div>
      <div class="sublogo">Computers & AI Architect</div>
    </div>
    <div class="body">
      <div class="title">Код подтверждения для входа</div>
      <div class="desc">Используйте этот одноразовый код для авторизации в вашем аккаунте Skyrex Computers:</div>
      <div class="code-box">
        <div class="code">{code}</div>
      </div>
      <div class="notice">Срок действия кода — 15 минут.<br>Если вы не запрашивали авторизацию, просто проигнорируйте это письмо.</div>
    </div>
    <div class="footer">
      &copy; 2026 Skyrex Computers. Все права защищены.<br>
      Интерактивная платформа подбора компьютеров.
    </div>
  </div>
</body>
</html>"""

    msg.attach(MIMEText(text_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        if smtp_port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=15.0) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15.0) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        logger.info(f"Successfully sent OTP code to {to_email}")
        return True, None
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication error: {e}")
        return False, "Ошибка аутентификации почтового сервера."
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False, f"Не удалось отправить письмо: {str(e)}"

def create_verification_code(email: str) -> Tuple[bool, str, Optional[str]]:
    """Creates a 6-digit verification code with 60-second cooldown per email."""
    email = (email or "").strip().lower()
    if not email:
        return False, "", "Введите адрес электронной почты."
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return False, "", "Некорректный адрес электронной почты."
    if len(email) > 64:
        return False, "", "Адрес электронной почты слишком длинный."

    now = datetime.datetime.now(datetime.timezone.utc)
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        existing = cursor.execute("SELECT last_sent_at FROM verification_codes WHERE email = ?", (email,)).fetchone()
        if existing and existing["last_sent_at"]:
            try:
                last_dt = datetime.datetime.fromisoformat(existing["last_sent_at"].replace("Z", "+00:00"))
                elapsed = (now - last_dt).total_seconds()
                if elapsed < 60:
                    wait_sec = int(60 - elapsed)
                    return False, "", f"Подождите {wait_sec} сек. перед повторной отправкой кода."
            except Exception:
                pass

        code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = (now + datetime.timedelta(minutes=15)).isoformat()
        last_sent_at = now.isoformat()

        cursor.execute("""
            INSERT INTO verification_codes (email, code, attempts, last_sent_at, expires_at)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                code = excluded.code,
                attempts = 0,
                last_sent_at = excluded.last_sent_at,
                expires_at = excluded.expires_at;
        """, (email, code, last_sent_at, expires_at))
        conn.commit()

    return True, code, None

def verify_code_and_login(email: str, code: str) -> Dict[str, Any]:
    """Verifies 6-digit OTP code, registers user if new, creates 30-day session token."""
    email = (email or "").strip().lower()
    code = (code or "").strip()

    if not email or not code:
        return {"success": False, "error": "Введите email и код подтверждения."}

    now = datetime.datetime.now(datetime.timezone.utc)
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        row = cursor.execute("SELECT * FROM verification_codes WHERE email = ?", (email,)).fetchone()
        if not row:
            return {"success": False, "error": "Код не найден или срок его действия истек. Запросите код заново."}

        try:
            exp_dt = datetime.datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if now > exp_dt:
                cursor.execute("DELETE FROM verification_codes WHERE email = ?", (email,))
                conn.commit()
                return {"success": False, "error": "Срок действия кода истек (15 минут). Запросите новый код."}
        except Exception:
            pass

        attempts = row["attempts"] or 0
        if attempts >= 5:
            cursor.execute("DELETE FROM verification_codes WHERE email = ?", (email,))
            conn.commit()
            return {"success": False, "error": "Превышено максимальное число попыток ввода. Запросите новый код."}

        if not secrets.compare_digest(str(row["code"]).strip(), code):
            new_attempts = attempts + 1
            cursor.execute("UPDATE verification_codes SET attempts = ? WHERE email = ?", (new_attempts, email))
            conn.commit()
            remaining = max(0, 5 - new_attempts)
            return {"success": False, "error": f"Неверный код. Осталось попыток: {remaining}."}

        # Code matched successfully! Clean up used code
        cursor.execute("DELETE FROM verification_codes WHERE email = ?", (email,))
        
        # Check or create user
        user = cursor.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (email,)).fetchone()
        default_nick = email.split("@")[0][:24]
        if not user:
            # Auto-register new user by email with default nickname
            salt = secrets.token_hex(16)
            pwd_hash = hash_password(secrets.token_urlsafe(32), salt)
            cursor.execute("""
                INSERT INTO users (username, nickname, password_hash, salt, role, subscribed, subscription_expires)
                VALUES (?, ?, ?, ?, 'user', 0, NULL)
            """, (email, default_nick, pwd_hash, salt))
            user_id = cursor.lastrowid
            nick = default_nick
            role = "user"
            subscribed = False
            sub_exp = None
        else:
            user_id = user["id"]
            user_keys = user.keys()
            nick = user["nickname"] if "nickname" in user_keys and user["nickname"] else default_nick
            role = user["role"]
            subscribed = bool(user["subscribed"])
            sub_exp = user["subscription_expires"]

            if role == "admin" or email == "nicitachebotariow@yandex.ru":
                role = "admin"
                subscribed = True

        conn.commit()

    token = create_session(user_id)
    user_dict = {
        "id": user_id,
        "username": email,
        "nickname": nick,
        "role": role,
        "subscribed": subscribed,
        "subscriptionExpires": sub_exp
    }
    _TOKEN_CACHE[token] = {"user": user_dict, "expires_ts": time.time() + 30.0}
    return {
        "success": True,
        "token": token,
        "user": user_dict
    }

def update_user_nickname(user_id: int, new_nickname: str) -> Dict[str, Any]:
    """Updates user display nickname with strict validation and sanitization."""
    nick = (new_nickname or "").strip()
    if not nick:
        return {"success": False, "error": "Никнейм не может быть пустым."}
    if len(nick) < 2:
        return {"success": False, "error": "Никнейм должен содержать минимум 2 символа."}
    if len(nick) > 24:
        return {"success": False, "error": "Никнейм не должен превышать 24 символа."}
    if not re.match(r"^[a-zA-Z0-9а-яА-ЯёЁ\s_\-\.]+$", nick):
        return {"success": False, "error": "Никнейм может содержать только буквы, цифры, пробелы, дефис и подчеркивание."}

    with get_auth_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET nickname = ? WHERE id = ?", (nick, user_id))
        conn.commit()

        # Update cached profiles in-memory
        for t, val in list(_TOKEN_CACHE.items()):
            if val.get("user", {}).get("id") == user_id:
                val["user"]["nickname"] = nick

        user = cursor.execute("SELECT id, username, nickname, role, subscribed, subscription_expires FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return {"success": False, "error": "Пользователь не найден."}

        return {
            "success": True,
            "nickname": nick,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "nickname": nick,
                "role": user["role"],
                "subscribed": bool(user["subscribed"]),
                "subscriptionExpires": user["subscription_expires"]
            }
        }

# ==========================================
# 5. Helpdesk & Support Messaging System
# ==========================================

def add_support_message(email: str, message: str, sender: str = "user", user_id: Optional[int] = None) -> Dict[str, Any]:
    """Adds a new message to support dialogue (from customer or admin)."""
    email = (email or "").strip().lower()
    message = (message or "").strip()
    if not email or not message:
        return {"success": False, "error": "Email и текст сообщения обязательны."}
    if len(message) > 4000:
        return {"success": False, "error": "Текст сообщения превышает лимит (4000 символов)."}

    with get_auth_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO support_messages (user_id, email, sender, message, is_read)
            VALUES (?, ?, ?, ?, 0)
        """, (user_id, email, sender, message))
        conn.commit()
        msg_id = cursor.lastrowid
        row = cursor.execute("SELECT id, user_id, email, sender, message, is_read, created_at FROM support_messages WHERE id = ?", (msg_id,)).fetchone()
        return {"success": True, "message": dict(row) if row else {}}

def get_support_messages(email: str) -> List[Dict[str, Any]]:
    """Returns conversation history between a specific user and support."""
    email = (email or "").strip().lower()
    if not email:
        return []
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        rows = cursor.execute("""
            SELECT id, user_id, email, sender, message, is_read, created_at
            FROM support_messages
            WHERE email = ? COLLATE NOCASE
            ORDER BY created_at ASC
        """, (email,)).fetchall()
        return [dict(r) for r in rows]

def get_support_dialogs() -> List[Dict[str, Any]]:
    """Returns list of distinct user dialogues for admin support panel."""
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        rows = cursor.execute("""
            SELECT 
                sm.email,
                sm.user_id,
                MAX(sm.created_at) as last_time,
                (SELECT message FROM support_messages WHERE email = sm.email ORDER BY created_at DESC LIMIT 1) as last_message,
                (SELECT sender FROM support_messages WHERE email = sm.email ORDER BY created_at DESC LIMIT 1) as last_sender,
                SUM(CASE WHEN sm.sender = 'user' AND sm.is_read = 0 THEN 1 ELSE 0 END) as unread_count
            FROM support_messages sm
            GROUP BY sm.email
            ORDER BY last_time DESC
        """).fetchall()
        return [dict(r) for r in rows]

def mark_support_messages_read(email: str, by_sender: str = "admin"):
    """Marks messages as read for a given email thread."""
    email = (email or "").strip().lower()
    if not email:
        return
    target_sender = "user" if by_sender == "admin" else "admin"
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE support_messages 
            SET is_read = 1 
            WHERE email = ? COLLATE NOCASE AND sender = ? AND is_read = 0
        """, (email, target_sender))
        conn.commit()

def send_support_reply_email(to_email: str, reply_text: str) -> Tuple[bool, Optional[str]]:
    """Sends notification to customer when admin replies to their support ticket."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.mail.ru").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", "").strip() or f"Skyrex Computers <{smtp_user}>"

    if not smtp_user or not smtp_pass:
        return False, "SMTP credentials missing"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Ответ службы поддержки Skyrex Computers"
    msg["From"] = smtp_from
    msg["To"] = to_email

    text_content = (
        f"Здравствуйте!\n\n"
        f"Администратор службы поддержки Skyrex ответил на ваше обращение:\n\n"
        f"{reply_text}\n\n"
        f"Вы можете продолжить общение в онлайн-чате на сайте: https://skyrex.pro\n\n"
        f"С уважением,\nКоманда Skyrex Computers"
    )

    clean_reply_html = html.escape(reply_text).replace("\n", "<br>")
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ margin: 0; padding: 0; background-color: #0c1017; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0; }}
    .container {{ max-width: 540px; margin: 30px auto; background: #131923; border: 1px solid #1f2937; border-radius: 14px; overflow: hidden; }}
    .header {{ background: linear-gradient(135deg, #0a0f1d 0%, #1e1b4b 100%); padding: 24px; text-align: center; border-bottom: 2px solid #00ffcc44; }}
    .logo {{ font-size: 24px; font-weight: 800; letter-spacing: 3px; color: #00ffcc; text-transform: uppercase; margin: 0; }}
    .body {{ padding: 30px 25px; }}
    .title {{ font-size: 18px; font-weight: 600; color: #ffffff; margin-bottom: 16px; }}
    .reply-box {{ background: rgba(0, 255, 204, 0.05); border-left: 4px solid #00ffcc; border-radius: 6px; padding: 16px; margin: 20px 0; color: #f1f5f9; font-size: 14px; line-height: 1.6; }}
    .btn {{ display: inline-block; background: #00ffcc; color: #000; font-weight: 700; text-decoration: none; padding: 12px 24px; border-radius: 8px; margin-top: 15px; font-size: 14px; }}
    .footer {{ background: #080d14; padding: 16px; text-align: center; font-size: 11px; color: #475569; border-top: 1px solid #1e293b; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo">SKYREX</div>
      <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase; margin-top: 4px;">Служба поддержки клиентов</div>
    </div>
    <div class="body">
      <div class="title">Новый ответ по вашему обращению</div>
      <p style="font-size: 14px; color: #94a3b8; margin: 0 0 10px 0;">Здравствуйте! Администратор Skyrex ответил на ваш вопрос:</p>
      <div class="reply-box">{clean_reply_html}</div>
      <div style="text-align: center; margin-top: 25px;">
        <a href="https://skyrex.pro" class="btn" target="_blank">Перейти на сайт Skyrex</a>
      </div>
    </div>
    <div class="footer">
      ИП Чеботарёв Н.Д. | Skyrex Computers &bull; https://skyrex.pro
    </div>
  </div>
</body>
</html>"""

    part1 = MIMEText(text_content, "plain", "utf-8")
    part2 = MIMEText(html_content, "html", "utf-8")
    msg.attach(part1)
    msg.attach(part2)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=15) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, [to_email], msg.as_string())
        logger.info(f"Support reply email sent successfully to {to_email}")
        return True, None
    except Exception as e:
        logger.error(f"Failed to send support reply email to {to_email}: {e}")
        return False, str(e)

def delete_support_dialog(email: str) -> bool:
    """Deletes all messages for a specific email dialogue."""
    email = (email or "").strip().lower()
    if not email:
        return False
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM support_messages WHERE email = ? COLLATE NOCASE", (email,))
        conn.commit()
        return True

def get_admin_payments(limit: int = 50) -> List[Dict[str, Any]]:
    """Returns recent payments with customer email and details for admin panel."""
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        rows = cursor.execute("""
            SELECT p.id, p.user_id, u.username as email, u.nickname, p.amount, p.currency, p.status, p.description, p.created_at
            FROM payments p
            LEFT JOIN users u ON p.user_id = u.id
            ORDER BY p.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

def get_admin_users(limit: int = 50) -> List[Dict[str, Any]]:
    """Returns users list with subscription status for admin panel."""
    with get_auth_connection() as conn:
        cursor = conn.cursor()
        rows = cursor.execute("""
            SELECT id, username as email, nickname, role, subscribed, subscription_expires, created_at
            FROM users
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
