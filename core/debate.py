"""
core/debate.py — 3-call ICT/SMC bull/bear debate via NVIDIA NIM

Call 1: Bull makes the case FOR the trade
Call 2: Bear reads bull's argument and attacks it specifically
Call 3: Judge reads both, gives final verdict with no bias

Only triggered manually from dashboard — never runs automatically.
Never touches trades. Read-only second opinion.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_NIM_BASE = "https://integrate.api.nvidia.com/v1"
_MODEL    = "moonshotai/kimi-k2-instruct"

# ── SIGNAL CONTEXT BLOCK (shared across all 3 calls) ─────────────────────────

_SIGNAL_BLOCK = """\
SIGNAL DATA:
  Pair:           {pair}
  Direction:      {direction}
  Grade:          {grade} | Score: {score}/100
  Session:        {session} | Killzone: {killzone}
  H1 trend:       {h1_trend}
  M15 trend:      {m15_trend}
  M5 trend:       {m5_trend}
  Entry pattern:  {entry_pattern}
  Setup type:     {setup_type}
  Zone type:      {h1_zone_type} | Zone strength: {h1_zone_strength}/100
  Entry:          {entry_price} | SL: {sl_price} ({sl_pips} pips) | TP1: {tp1_price} ({tp1_pips} pips)
  Risk/Reward:    1:{rr}
  News safe:      {news_safe}
  Score breakdown — Zone:{score_zone} | TF:{score_tf} | Pattern:{score_pattern} | Session:{score_session} | News:{score_news}"""

# ── PROMPT 1: BULL ────────────────────────────────────────────────────────────

_BULL_PROMPT = """\
You are a senior ICT/SMC forex trader with 30 years of experience. \
You are reviewing this signal and your job is to make the STRONGEST possible case FOR taking this trade. \
Be specific to ICT concepts — do not be generic.

{signal_block}

Build the bull case. Cover:
- Is HTF (H1) structure aligned with direction? Is M15 confirming?
- Is the entry zone (OB/support/resistance) fresh and unmitigated?
- Is the session and killzone correct for this pair?
- Is the RR worth the risk?
- What does the entry pattern tell you about institutional intent?
- Is this a premium/discount entry in the right direction?

Be direct. Max 4 sentences. Do not mention weaknesses — that is the bear's job.
Write your argument as plain text, no JSON, no bullet points."""

# ── PROMPT 2: BEAR ────────────────────────────────────────────────────────────

_BEAR_PROMPT = """\
You are a ruthless ICT/SMC risk manager with 30 years of experience. \
You have just read the bull's argument below. Your job is to find every flaw in it \
and make the STRONGEST possible case AGAINST taking this trade. \
Be specific — attack the bull's points directly, don't give generic warnings.

{signal_block}

BULL'S ARGUMENT:
{bull_argument}

Now tear it apart. Cover:
- What is bull ignoring or glossing over? (session, killzone, trend conflict, zone strength)
- Is the zone actually clean or has price already tapped it (low strength = mitigated)?
- Is there a liquidity pool above/below entry that price will sweep first?
- Is the RR truly worth it or is the SL too wide?
- What could invalidate this setup in the next few candles?
- Is the score breakdown showing any weak link (low session score, low pattern score)?
- Even with news_safe flag — is there macro risk in this session?

Be brutal. Max 4 sentences. Only weaknesses. No praise for the setup.
Write your argument as plain text, no JSON, no bullet points."""

# ── PROMPT 3: JUDGE ───────────────────────────────────────────────────────────

_JUDGE_PROMPT = """\
You are a head of trading at a professional ICT/SMC forex firm with 30 years of experience. \
A bull and a bear just debated the signal below. You have no position — \
you are not bullish or bearish. Your only job is to give the most accurate verdict possible.

{signal_block}

BULL ARGUED:
{bull_argument}

BEAR ARGUED:
{bear_argument}

Apply these ICT rules strictly before deciding:
1. If H1 trend opposes direction → automatic PASS unless MSS is confirmed
2. If outside killzone → WAIT (wrong time, right setup)
3. If zone strength < 40 → zone is mitigated → PASS
4. If RR < 1.5 → not worth the risk → PASS
5. If news_safe is no → WAIT until news clears
6. If M15 and M5 both oppose direction → PASS (no LTF confirmation)
7. If bear made a point bull did not address → weight it heavily

Verdict must be one of: TAKE | PASS | WAIT

Respond in this exact JSON format, nothing else:
{{
  "verdict": "TAKE or PASS or WAIT",
  "reason": "one sentence — the single most decisive factor",
  "bull_score": "how strong was bull's case out of 10",
  "bear_score": "how strong was bear's case out of 10",
  "key_risk": "the one thing that could still kill this trade even if verdict is TAKE"
}}"""


# ── MAIN FUNCTION ─────────────────────────────────────────────────────────────

def debate_signal(signal: dict) -> dict:
    """
    3-call bull/bear debate on a signal dict from the DB.
    Returns: {ok, bull, bear, verdict, reason, bull_score, bear_score, key_risk}
    """
    api_key = os.getenv("NIM_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "error": "NIM_API_KEY not set"}

    try:
        from openai import OpenAI
        client = OpenAI(base_url=_NIM_BASE, api_key=api_key, timeout=90.0)

        sl   = float(signal.get("sl_pips")  or 0)
        tp   = float(signal.get("tp1_pips") or 0)
        rr   = round(tp / sl, 2) if sl > 0 else 0

        signal_block = _SIGNAL_BLOCK.format(
            pair             = signal.get("pair", "?"),
            direction        = signal.get("direction", "?"),
            grade            = signal.get("grade", "?"),
            score            = signal.get("score", "?"),
            session          = signal.get("session") or "unknown",
            killzone         = signal.get("killzone") or "outside killzone",
            h1_trend         = signal.get("h1_trend") or "unknown",
            m15_trend        = signal.get("m15_trend") or "unknown",
            m5_trend         = signal.get("m5_trend") or "unknown",
            entry_pattern    = signal.get("entry_pattern") or "unknown",
            setup_type       = signal.get("setup_type") or "unknown",
            h1_zone_type     = signal.get("h1_zone_type") or "unknown",
            h1_zone_strength = round(float(signal.get("h1_zone_strength") or 0), 1),
            entry_price      = signal.get("entry_price", "?"),
            sl_price         = signal.get("sl_price", "?"),
            sl_pips          = sl,
            tp1_price        = signal.get("tp1_price", "?"),
            tp1_pips         = tp,
            rr               = rr,
            news_safe        = "YES" if signal.get("news_safe") else "NO — NEWS RISK",
            score_zone       = signal.get("score_zone", 0),
            score_tf         = signal.get("score_tf", 0),
            score_pattern    = signal.get("score_pattern", 0),
            score_session    = signal.get("score_session", 0),
            score_news       = signal.get("score_news", 0),
        )

        def _call(prompt: str, max_tokens: int = 250) -> str:
            resp = client.chat.completions.create(
                model       = _MODEL,
                messages    = [{"role": "user", "content": prompt}],
                temperature = 0.4,
                max_tokens  = max_tokens,
            )
            return resp.choices[0].message.content.strip()

        # ── Call 1: Bull ──────────────────────────────────────────────────────
        bull_arg = _call(
            _BULL_PROMPT.format(signal_block=signal_block)
        )
        logger.info(f"Bull argument complete for {signal.get('signal_id')}")

        # ── Call 2: Bear (reads bull's argument) ─────────────────────────────
        bear_arg = _call(
            _BEAR_PROMPT.format(signal_block=signal_block, bull_argument=bull_arg)
        )
        logger.info(f"Bear argument complete for {signal.get('signal_id')}")

        # ── Call 3: Judge (reads both, no bias) ──────────────────────────────
        judge_raw = _call(
            _JUDGE_PROMPT.format(
                signal_block=signal_block,
                bull_argument=bull_arg,
                bear_argument=bear_arg,
            ),
            max_tokens=200,
        )
        logger.info(f"Judge verdict complete for {signal.get('signal_id')}")

        # Strip markdown fences if model wraps response
        if "```" in judge_raw:
            parts = judge_raw.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    judge_raw = part
                    break

        verdict_data = json.loads(judge_raw)

        return {
            "ok":         True,
            "bull":       bull_arg,
            "bear":       bear_arg,
            "verdict":    verdict_data.get("verdict", "WAIT"),
            "reason":     verdict_data.get("reason", ""),
            "bull_score": verdict_data.get("bull_score", "?"),
            "bear_score": verdict_data.get("bear_score", "?"),
            "key_risk":   verdict_data.get("key_risk", ""),
        }

    except json.JSONDecodeError as e:
        logger.error(f"debate judge JSON parse error: {e} | raw: {judge_raw[:300]}")
        # Still return bull/bear even if judge JSON failed
        return {
            "ok":       True,
            "bull":     bull_arg if "bull_arg" in dir() else "",
            "bear":     bear_arg if "bear_arg" in dir() else "",
            "verdict":  "WAIT",
            "reason":   "Judge failed to parse — read bull/bear manually",
            "bull_score": "?",
            "bear_score": "?",
            "key_risk":   "",
        }
    except Exception as e:
        logger.error(f"debate_signal error: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}
