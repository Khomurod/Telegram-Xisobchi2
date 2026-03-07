"""
Telegram Mini App initData validation.

Validates the HMAC-SHA256 signature that Telegram injects into every
Mini App launch.  Uses timing-safe comparison (hmac.compare_digest).

Reference: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Optional

from app.utils.logger import setup_logger

logger = setup_logger("telegram_auth")

# initData is valid for 1 hour (3600 seconds)
_MAX_AGE_SECONDS = 3600


def validate_init_data(
    init_data: str, bot_token: str, max_age: int = _MAX_AGE_SECONDS
) -> Optional[dict]:
    """
    Validate Telegram Mini App initData string.

    Returns the user dict on success, None on failure.
    """
    if not init_data or not bot_token:
        return None

    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        logger.warning("Failed to parse initData query string")
        return None

    check_hash = parsed.pop("hash", "")
    if not check_hash:
        logger.warning("initData missing 'hash' field")
        return None

    # Check age — reject stale tokens
    auth_date_str = parsed.get("auth_date", "")
    if auth_date_str:
        try:
            auth_date = int(auth_date_str)
            if time.time() - auth_date > max_age:
                logger.warning("initData expired (auth_date too old)")
                return None
        except ValueError:
            pass

    # Build data-check-string (sorted key=value pairs joined by \n)
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    # HMAC-SHA256: secret = HMAC("WebAppData", bot_token), hash = HMAC(secret, data_check_string)
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, check_hash):
        logger.warning("initData HMAC validation failed")
        return None

    # Extract user object
    user_str = parsed.get("user", "{}")
    try:
        user = json.loads(user_str)
    except json.JSONDecodeError:
        logger.warning("Failed to parse user JSON from initData")
        return None

    return user
