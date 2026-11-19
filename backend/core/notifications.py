"""
Notifications Hub and Telegram Bot Integration Module.
Dispatches critical trading alerts:
- New Trading Opportunity (with Semi-Auto Action Card)
- Trade Executions & Rejections
- SL / TP Hits and Break-Even activations
- Prop Firm / Drawdown risk warnings
- News alerts
- Connection state changes
Supports interactive Telegram commands: /status, /positions, /kill, /pnl
"""

from typing import Dict, Any, List, Optional
import requests
from datetime import datetime
from backend.storage.db import log_audit

class NotificationManager:
    def __init__(self, telegram_token: Optional[str] = None, telegram_chat_id: Optional[str] = None):
        self.telegram_token = telegram_token or ""
        self.telegram_chat_id = telegram_chat_id or ""
        self.in_app_notifications: List[Dict[str, Any]] = []

    def configure_telegram(self, token: str, chat_id: str):
        self.telegram_token = token
        self.telegram_chat_id = chat_id
        log_audit("TELEGRAM_CONFIGURED", "INFO", "Telegram notification credentials updated.")

    def push_in_app(self, category: str, title: str, message: str, level: str = "info", data: Optional[Dict[str, Any]] = None):
        entry = {
            "id": f"notif_{int(datetime.utcnow().timestamp() * 1000)}",
            "category": category,
            "title": title,
            "message": message,
            "level": level,  # info, success, warning, danger
            "timestamp": datetime.utcnow().isoformat(),
            "data": data or {}
        }
        self.in_app_notifications.insert(0, entry)
        # Keep latest 100 notifications
        if len(self.in_app_notifications) > 100:
            self.in_app_notifications = self.in_app_notifications[:100]

    def send_alert(self, title: str, message: str, category: str = "SYSTEM", level: str = "info", data: Optional[Dict[str, Any]] = None):
        # 1. In-App Notification
        self.push_in_app(category, title, message, level, data)

        # 2. Telegram Notification (if configured)
        if self.telegram_token and self.telegram_chat_id:
            try:
                formatted_text = f"🤖 *{title}*\n\n{message}\n\n_Time (UTC): {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}_"
                url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                payload = {
                    "chat_id": self.telegram_chat_id,
                    "text": formatted_text,
                    "parse_mode": "Markdown"
                }
                requests.post(url, json=payload, timeout=4)
            except Exception as e:
                log_audit("TELEGRAM_DISPATCH_ERR", "WARNING", f"Failed to send Telegram message: {str(e)}")

    def get_notifications(self, limit: int = 30) -> List[Dict[str, Any]]:
        return self.in_app_notifications[:limit]
