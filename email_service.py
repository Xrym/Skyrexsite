import os
import smtplib
import asyncio
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any

logger = logging.getLogger("skyrex_email")

def send_smtp_email_sync(to_email: str, subject: str, html_content: str, text_content: str = "") -> Dict[str, Any]:
    """Synchronous SMTP mail delivery with configurable host, port and TLS."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@skyrex.ru").strip()
    
    if not smtp_user or not smtp_password:
        logger.warning("SMTP credentials not configured (SMTP_USER or SMTP_PASSWORD empty). Email not sent.")
        return {
            "success": False,
            "error": "Почтовый сервер не настроен в файле .env (укажите SMTP_USER и SMTP_PASSWORD)"
        }

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Skyrex Computers <{smtp_from}>"
        msg["To"] = to_email

        if text_content:
            part_text = MIMEText(text_content, "plain", "utf-8")
            msg.attach(part_text)

        part_html = MIMEText(html_content, "html", "utf-8")
        msg.attach(part_html)

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

        logger.info(f"Verification email successfully sent to {to_email}")
        return {"success": True}
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication error for {smtp_user}: {e}")
        return {
            "success": False,
            "error": "Ошибка авторизации почты: для Gmail требуется 'Пароль приложения' (App Password), а не обычный пароль от аккаунта Google."
        }
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return {"success": False, "error": f"Ошибка отправки письма: {str(e)}"}

async def send_verification_email(to_email: str, code: str) -> Dict[str, Any]:
    """Sends stylized verification code email asynchronously."""
    subject = f"{code} — Код подтверждения Skyrex Computers"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="margin: 0; padding: 0; background-color: #0b0a10; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f4f4f7;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0b0a10; padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table width="100%" max-width="560px" style="max-width: 560px; background: #13121d; border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.08); padding: 36px; text-align: center; box-shadow: 0 10px 40px rgba(0,0,0,0.5);">
                        <tr>
                            <td>
                                <div style="font-size: 26px; font-weight: 800; letter-spacing: 2px; color: #00f2fe; margin-bottom: 8px;">
                                    ⚡ SKYREX COMPUTERS
                                </div>
                                <h2 style="font-size: 20px; font-weight: 600; color: #ffffff; margin-top: 15px; margin-bottom: 10px;">
                                    Подтверждение регистрации
                                </h2>
                                <p style="font-size: 14px; line-height: 1.6; color: #9d9cb0; margin-bottom: 25px;">
                                    Вы запросили регистрацию в сервисе подбора компьютеров <b>Skyrex Computers</b>.<br>
                                    Используйте следующий проверочный код:
                                </p>
                                
                                <div style="display: inline-block; background: rgba(0, 242, 254, 0.08); border: 2px solid #00f2fe; border-radius: 12px; padding: 16px 36px; margin: 10px 0 25px 0;">
                                    <span style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #00f2fe;">{code}</span>
                                </div>
                                
                                <p style="font-size: 13px; color: #76758a; margin-bottom: 5px;">
                                    Код действителен в течение <b>10 минут</b>.
                                </p>
                                <p style="font-size: 12px; color: #525164; margin-top: 25px; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 20px;">
                                    Если вы не отправляли запрос на регистрацию, просто проигнорируйте это письмо.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    text_content = f"Код подтверждения регистрации в Skyrex Computers: {code}\nКод действителен 10 минут."
    
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, send_smtp_email_sync, to_email, subject, html_content, text_content)
