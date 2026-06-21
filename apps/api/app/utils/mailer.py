"""
邮件发送（可插拔，正式 SMTP）。

- 未配置 settings.smtp_host 时走「开发桩」：把邮件内容打印到日志，便于本地联调；
- 配置 SMTP 后自动改走真实发送：
  - 端口 465 → 直连 SSL；端口 587（或其它）→ STARTTLS；可用 smtp_use_ssl 强制覆盖；
  - 支持纯文本 + 可选 HTML（multipart/alternative）；
  - send_email 同步发送；send_email_async 丢到后台线程，避免阻塞注册/找回密码请求
    （SMTP 握手可能耗时数秒）。
任何异常只记录日志、不向上抛，保证发信失败不影响主流程。
"""

import smtplib
import threading
from email.message import EmailMessage

from ..settings import settings
from .logger import get_logger

logger = get_logger("superfish.mailer")


def _use_ssl() -> bool:
    """是否直连 SSL：显式配置优先，否则按端口 465 自动判定。"""
    if settings.smtp_use_ssl is not None:
        return settings.smtp_use_ssl
    return settings.smtp_port == 465


def _build_message(to: str, subject: str, body: str, html: str | None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def send_email(to: str, subject: str, body: str, html: str | None = None) -> None:
    """同步发送邮件；未配置 SMTP 时仅打印到日志（开发桩）。异常只记录不抛。"""
    if not settings.smtp_host:
        logger.info(
            "[DEV-EMAIL] 未配置 SMTP，邮件未真正发送（开发桩）：\n"
            f"  收件人: {to}\n  主题: {subject}\n  正文:\n{body}"
        )
        return

    try:
        msg = _build_message(to, subject, body, html)
        host, port = settings.smtp_host, settings.smtp_port
        if _use_ssl():
            with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        logger.info(f"邮件已发送: to={to} subject={subject}")
    except Exception as e:
        logger.error(f"邮件发送失败: to={to} err={e}")


def send_email_async(to: str, subject: str, body: str, html: str | None = None) -> None:
    """后台线程异步发送，立即返回，不阻塞请求。失败已在 send_email 内吞掉并记录。"""
    threading.Thread(
        target=send_email,
        args=(to, subject, body, html),
        kwargs={},
        daemon=True,
    ).start()
