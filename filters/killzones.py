"""
filters/killzones.py — ICT Killzones

Killzones are the only windows where ICT setups are reliable.
Outside them = scanner stays quiet unless A+ setup.

Killzone     EST             UTC             Best For
─────────────────────────────────────────────────────
Asian        8pm – 12am      01:00 – 05:00   USDJPY, range builds
London Open  2am – 5am       07:00 – 10:00   GBP pairs, EUR pairs
NY Open      7am – 10am      12:00 – 15:00   Gold, all pairs
London Close 10am – 12pm     15:00 – 17:00   Reversals

All times UTC.
"""

from datetime import datetime, time
import logging

logger = logging.getLogger(__name__)

# Killzone definitions (UTC)
KILLZONES = {
    "asian": {
        "start":       time(1,  0),
        "end":         time(5,  0),
        "label":       "Asian Killzone",
        "best_pairs":  ["USD_JPY", "GBP_JPY", "EUR_JPY", "CHF_JPY", "CAD_JPY", "NZD_JPY"],
        "character":   "range",
        "description": "Range builds, JPY pairs most active",
    },
    "london_open": {
        "start":       time(7,  0),
        "end":         time(10, 0),
        "label":       "London Open Killzone",
        "best_pairs":  ["GBP_JPY", "GBP_USD", "EUR_USD", "EUR_GBP", "EUR_JPY"],
        "character":   "trend",
        "description": "Strongest moves of the day, GBP/EUR pairs",
    },
    "ny_open": {
        "start":       time(12, 0),
        "end":         time(15, 0),
        "label":       "NY Open Killzone",
        "best_pairs":  ["XAU_USD", "GBP_USD", "EUR_USD", "USD_JPY", "GBP_JPY", "XAG_USD"],
        "character":   "trend",
        "description": "Gold and USD pairs, high volatility, strong trends",
    },
    "london_close": {
        "start":       time(15, 0),
        "end":         time(17, 0),
        "label":       "London Close Killzone",
        "best_pairs":  ["GBP_USD", "EUR_USD", "EUR_GBP", "GBP_JPY"],
        "character":   "reversal",
        "description": "Reversal setups as London positions close",
    },
}


def get_active_killzone() -> dict:
    """
    Return the currently active killzone, or None if outside all killzones.
    """
    now = datetime.utcnow().time()

    for name, kz in KILLZONES.items():
        if kz["start"] <= now <= kz["end"]:
            # Calculate minutes remaining
            end_dt   = datetime.utcnow().replace(
                hour=kz["end"].hour, minute=kz["end"].minute, second=0
            )
            now_dt   = datetime.utcnow()
            mins_left = max(0, int((end_dt - now_dt).total_seconds() / 60))

            return {
                "name":        name,
                "label":       kz["label"],
                "best_pairs":  kz["best_pairs"],
                "character":   kz["character"],
                "description": kz["description"],
                "mins_left":   mins_left,
                "active":      True,
            }

    return {"active": False, "name": None, "label": "Outside Killzones", "mins_left": 0}


def get_killzone_context(pair: str) -> dict:
    """
    Return killzone context for a specific pair.
    Used by scorer to adjust signal filtering.

    Returns:
      in_killzone:    bool
      pair_favored:   bool — this pair is in the best_pairs list
      score_modifier: float — multiplier for scoring (0.5 outside KZ, 1.0 inside)
      note:           str
    """
    kz = get_active_killzone()

    if not kz["active"]:
        mins_to_next, next_kz = minutes_to_next_killzone()
        return {
            "in_killzone":    False,
            "pair_favored":   False,
            "score_modifier": 0.5,   # outside KZ = dampen score
            "killzone":       None,
            "note":           (
                f"Outside killzones — {next_kz['label']} in {mins_to_next} min. "
                f"Only A+ setups matter here."
            ),
            "mins_to_next":   mins_to_next,
            "next_killzone":  next_kz,
        }

    pair_favored = pair in kz["best_pairs"]

    if pair_favored:
        score_modifier = 1.0
        note = f"{kz['label']} — {pair} is a prime pair here. {kz['description']}. {kz['mins_left']} min remaining."
    else:
        score_modifier = 0.8
        note = f"{kz['label']} — {pair} is not the primary pair for this killzone ({kz['mins_left']} min left)."

    return {
        "in_killzone":    True,
        "pair_favored":   pair_favored,
        "score_modifier": score_modifier,
        "killzone":       kz,
        "note":           note,
        "mins_to_next":   0,
        "next_killzone":  None,
    }


def should_suppress_signal(grade: str, kz_context: dict) -> bool:
    """
    Outside a killzone, suppress B and C signals.
    Only A+ passes through when outside killzones.
    """
    if kz_context["in_killzone"]:
        return False  # Inside killzone — never suppress

    # Outside killzone — only A+ passes
    return grade in ["B", "C"]


def minutes_to_next_killzone() -> tuple:
    """
    Returns (minutes_until, killzone_dict) for the next killzone to open.
    """
    now    = datetime.utcnow()
    now_t  = now.time()
    best   = None
    best_m = 9999

    for name, kz in KILLZONES.items():
        # Build target datetime for today
        target = now.replace(
            hour=kz["start"].hour,
            minute=kz["start"].minute,
            second=0, microsecond=0
        )

        # If already passed today, look at tomorrow
        if kz["start"] <= now_t:
            from datetime import timedelta
            target += timedelta(days=1)

        mins = int((target - now).total_seconds() / 60)
        if mins < best_m:
            best_m = mins
            best   = {"name": name, **kz, "mins_away": mins}

    return best_m, best or {}


def format_killzone_banner(kz_context: dict) -> str:
    """
    One-line banner for alert output.
    Example: "🕐 NY Open Killzone — 14 min remaining"
    """
    if not kz_context.get("in_killzone"):
        mins   = kz_context.get("mins_to_next", 0)
        next_kz = kz_context.get("next_killzone", {})
        label  = next_kz.get("label", "next killzone") if next_kz else "next killzone"
        return f"🕐 Outside killzones — {label} in {mins} min"

    kz    = kz_context["killzone"]
    label = kz["label"]
    mins  = kz.get("mins_left", 0)
    return f"🕐 {label} — {mins} min remaining"