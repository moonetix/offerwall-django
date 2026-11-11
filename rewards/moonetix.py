"""
Signs offerwall links and checks postback hashes. Server side only.
Docs: https://docs.moonetix.com/offerwall-link and https://docs.moonetix.com/postbacks
"""

import hashlib
import hmac
import re
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

WALL_BASE = "https://wall.moonetix.com/"
MICRO = 1_000_000  # rewards are stored in millionths of a coin

USER_ID_RE = re.compile(r"[A-Za-z0-9._@:+\-]{1,100}")
SUB_ID_RE = re.compile(r"[A-Za-z0-9._~:@+\-]{1,100}")
AMOUNT_RE = re.compile(r"([0-9]{1,12})(?:\.([0-9]{1,6}))?")


def _secret(name):
    # Read when used, so a missing key answers 500 (and Moonetix retries) instead of signing with "".
    value = getattr(settings, name, "")
    if not isinstance(value, str) or not value:
        raise ImproperlyConfigured(f"{name} is not set")
    return value


def wall_url(user_id, subs=None):
    """The signed offerwall link for one of YOUR user IDs. sub1 to sub5 are optional and not signed."""
    user_id = str(user_id)
    if not USER_ID_RE.fullmatch(user_id):
        raise ValueError("The user ID must be 1 to 100 characters from A-Z a-z 0-9 . _ @ : + -")
    sig = hmac.new(_secret("MOONETIX_LINK_SALT").encode(), user_id.encode(), hashlib.sha256).hexdigest()
    url = f"{WALL_BASE}{quote(_secret('MOONETIX_APP_ID'), safe='')}?user_id={quote(user_id, safe='')}&hash={sig}"
    for key, value in (subs or {}).items():
        if re.fullmatch(r"sub[1-5]", key) and isinstance(value, str) and SUB_ID_RE.fullmatch(value):
            url += f"&{key}={quote(value, safe='~')}"
    return url


def valid_postback_hash(tx, user_id, reward, status, given):
    """Constant-time check of the postback hash, over the values exactly as they arrived."""
    msg = f"{tx}:{user_id}:{reward}:{status}".encode()
    expected = hmac.new(_secret("MOONETIX_POSTBACK_KEY").encode(), msg, hashlib.sha256).hexdigest()
    # Bytes, not str: compare_digest raises TypeError on non-ASCII str input.
    return hmac.compare_digest(expected.encode(), given.encode())


def to_micro(amount):
    """'150' -> 150000000, '0.75' -> 750000. None for anything else. No floats."""
    m = AMOUNT_RE.fullmatch(amount)
    if not m:
        return None
    return int(m.group(1)) * MICRO + int((m.group(2) or "").ljust(6, "0"))


def format_micro(micro):
    """151984560 -> '151.98456'."""
    sign = "-" if micro < 0 else ""
    whole, frac = divmod(abs(micro), MICRO)
    frac_s = str(frac).rjust(6, "0").rstrip("0")
    return f"{sign}{whole}" + (f".{frac_s}" if frac_s else "")
