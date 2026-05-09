"""
core/debate.py — Bull/Bear debate for A+ signals via NVIDIA NIM

Single LLM call, both perspectives + verdict.
Only called from /api/debate_signal — never runs automatically.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_NIM_BASE = "https://integrate.api.nvidia.com/v1"
_MODEL    = "nvidia/kimi-k2-instruct"

_PROMPT = """\
You are a disciplined ICT/SMC forex risk analyst. A scanner has flagged the following signal.
Give an honest bull case, an honest bear case, then a final verdict.

Signal data:
- Pair: {pair}
- Direction: {direction}
- Grade: {grade}
- Score: {score}/100
- Session: {session} | Killzone: {killzone}
- Entry pattern: {entry_pattern}
- H1 trend: {h1_trend} | M15 trend: {m15_trend} | M5 trend: {m5_trend}
- SL: {sl_pips} pips | TP1: {tp1_pips} pips | RR: {rr:.1f}
- Zone type: {h1_zone_type} | Zone strength: {h1_zone_strength}
- News safe: {news_safe}
- Setup type: {setup_type}

Respond in this exact JSON format, nothing else:
{{
  "bull": "<2 sentences max — strongest case FOR taking this trade>",
  "bear": "<2 sentences max — strongest case AGAINST taking this trade>",
  "verdict": "<TAKE or PASS or WAIT>",
  "reason": "<one short sentence explaining the verdict>"
}}

Be brutally honest. Do not hype the trade. If the bear case is stronger, say PASS."""


def debate_signal(signal: dict) -> dict:
    """
    Run bull/bear debate on a signal dict from the DB.
    Returns: {bull, bear, verdict, reason, ok} or {ok: False, error: str}
    """
    api_key = os.getenv("NIM_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "error": "NIM_API_KEY not set"}

    try:
        from openai import OpenAI
        client = OpenAI(base_url=_NIM_BASE, api_key=api_key)

        sl   = float(signal.get("sl_pips")  or 0)
        tp   = float(signal.get("tp1_pips") or 0)
        rr   = round(tp / sl, 2) if sl > 0 else 0

        prompt = _PROMPT.format(
            pair            = signal.get("pair", "?"),
            direction       = signal.get("direction", "?"),
            grade           = signal.get("grade", "?"),
            score           = signal.get("score", "?"),
            session         = signal.get("session", "?"),
            killzone        = signal.get("killzone") or "outside killzone",
            entry_pattern   = signal.get("entry_pattern", "?"),
            h1_trend        = signal.get("h1_trend", "?"),
            m15_trend       = signal.get("m15_trend", "?"),
            m5_trend        = signal.get("m5_trend", "?"),
            sl_pips         = sl,
            tp1_pips        = tp,
            rr              = rr,
            h1_zone_type    = signal.get("h1_zone_type", "?"),
            h1_zone_strength= signal.get("h1_zone_strength", "?"),
            news_safe       = "yes" if signal.get("news_safe") else "no",
            setup_type      = signal.get("setup_type", "?"),
        )

        resp = client.chat.completions.create(
            model    = _MODEL,
            messages = [{"role": "user", "content": prompt}],
            temperature = 0.3,
            max_tokens  = 300,
        )

        raw = resp.choices[0].message.content.strip()

        # Strip markdown code fences if model wraps it
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        data = json.loads(raw)
        return {
            "ok":     True,
            "bull":   data.get("bull", ""),
            "bear":   data.get("bear", ""),
            "verdict": data.get("verdict", "WAIT"),
            "reason": data.get("reason", ""),
        }

    except json.JSONDecodeError as e:
        logger.error(f"debate_signal JSON parse error: {e} | raw: {raw[:200]}")
        return {"ok": False, "error": "Model returned invalid JSON"}
    except Exception as e:
        logger.error(f"debate_signal error: {e}")
        return {"ok": False, "error": str(e)}
