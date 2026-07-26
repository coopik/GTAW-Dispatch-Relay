from __future__ import annotations


def elevenlabs_credits(api_key: str, timeout: int = 12) -> dict:
    if not api_key:
        return {"ok": False, "error": "no API key"}
    try:
        import requests

        r = requests.get(
            "https://api.elevenlabs.io/v1/user/subscription",
            headers={"xi-api-key": api_key},
            timeout=timeout,
        )
        r.raise_for_status()
        d = r.json()
        used = int(d.get("character_count", 0) or 0)
        limit = int(d.get("character_limit", 0) or 0)
        remaining = max(limit - used, 0)
        tier = d.get("tier") or d.get("subscription_tier") or ""
        return {
            "ok": True,
            "used": used,
            "limit": limit,
            "remaining": remaining,
            "tier": tier,
            "reset": d.get("next_character_count_reset_unix"),
        }
    except Exception as e:  # noqa: BLE001 - surfaced to the UI as a note
        return {"ok": False, "error": _short_error(e)}


def openai_credits(base_url: str, api_key: str, timeout: int = 12) -> dict:
    if not api_key:
        return {"ok": False, "error": "no API key"}
    base = (base_url or "https://api.openai.com/v1").rstrip("/")
    try:
        import requests

        r = requests.get(
            f"{base}/dashboard/billing/credit_grants",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        if r.status_code == 200:
            d = r.json()
            avail = d.get("total_available")
            if avail is not None:
                return {
                    "ok": True,
                    "remaining": avail,
                    "used": d.get("total_used"),
                    "limit": d.get("total_granted"),
                    "unit": "USD",
                }
    except Exception:  # noqa: BLE001
        pass
    return {"ok": False, "error": "provider does not expose a balance"}


def _short_error(e: Exception) -> str:
    msg = str(e)
    if "401" in msg or "403" in msg:
        return "invalid API key"
    if "Timeout" in type(e).__name__ or "timed out" in msg.lower():
        return "request timed out"
    if "ConnectionError" in type(e).__name__:
        return "no internet connection"
    return msg[:80]
