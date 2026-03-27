import requests
import logging
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Sends a standard Telegram message.
        """
        endpoint = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        response = requests.post(endpoint, json=payload)
        
        if response.status_code == 200:
            return True
        else:
            logger.error(f"Failed to send Telegram message: {response.text}")
            return False

    def send_confirmation_request(self, signal_id: str, pair: str, z_score: float, rationale: str) -> bool:
        """
        Sends a message with inline buttons for manual confirmation.
        """
        endpoint = f"{self.base_url}/sendMessage"
        text = (
            f"🎯 *Signal Detected: {pair}*\n"
            f"Z-Score: `{z_score:.2f}`\n\n"
            f"💡 *AI Analysis:*\n{rationale}\n\n"
            f"Do you want to proceed with the rebalance?"
        )
        
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": f"approve_{signal_id}"},
                    {"text": "❌ Reject", "callback_data": f"reject_{signal_id}"}
                ]
            ]
        }
        
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": reply_markup
        }
        
        response = requests.post(endpoint, json=payload)
        
        if response.status_code == 200:
            logger.info(f"Confirmation request sent for signal {signal_id}")
            return True
        else:
            logger.error(f"Failed to send confirmation request: {response.text}")
            return False
