import os
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone

# Robust import of yfinance
try:
    import yfinance as yf
except Exception as e:
    raise RuntimeError(
        "Failed to import yfinance. Ensure the GitHub Actions step 'pip install yfinance' succeeded."
    ) from e

# ====== Configure the watchlist here ==========================================
# Add/remove items freely. For indices, use Yahoo symbols like ^IXIC (Nasdaq), ^GSPC (S&P 500).
WATCHLIST = [
    {"symbol": "^IXIC", "name": "Nasdaq Composite (IXIC)", "thresholds": [0.85, 0.80, 0.75, 0.70]},  # -15,-20,-25,-30
    {"symbol": "^GSPC", "name": "S&P 500 (SPX)",            "thresholds": [0.85, 0.80, 0.75, 0.70]},
    {"symbol": "TSLA",  "name": "Tesla, Inc. (TSLA)",         "thresholds": [0.85, 0.80, 0.75, 0.70]},
    {"symbol": "ONDS",  "name": "Tesla, Inc. (TSLA)",         "thresholds": [0.70]},
]
# ==============================================================================

STATE_FILE = "state.json"  # per-ticker state stored under a single JSON
OUT_HTML   = "docs/index.html"

def send_email(subject, body):
    """Send an email via SMTP using secrets provided by the workflow."""
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    pwd  = os.environ["SMTP_PASS"]
    to   = os.environ["TO_EMAIL"]

    print(f"[EMAIL] Host={host} Port={port} User={user} To={to}")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.set_debuglevel(1)  # show SMTP conversation in logs
        s.starttls()
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())
    print("[EMAIL] Sent OK")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(st):
    with open(STATE_FILE, "w") as f:
        json.dump(st, f)

def fmt_pct(x):
    return f"{x*100:.2f}%"

def gather_ticker_status(symbol, thresholds):
    """Fetch daily close history, compute last close, ATH close, drawdown, threshold statuses."""
    df = yf.download(symbol, period="15y", interval="1d", auto_adjust=False, progress=False)
    if df.empty:
        return None
    last_close = float(df["Close"].iloc[-1])
    ath_close  = float(df["Close"].max())
    dd         = last_close / ath_close - 1.0

    rows = []
    for f in thresholds:
        label = f"{int((1 - f) * 100)}%"
        level = ath_close * f
        hit   = last_close <= level
        rows.append({"label": label, "factor": f, "level": level, "hit": hit})
    return {
        "last_close": last_close,
        "ath_close": ath_close,
        "drawdown": dd,
        "threshold_rows": rows
    }

def compose_dashboard_html(results):
    """Create an HTML dashboard with one section per ticker."""
    sections = []
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for r in results:
        name       = r["name"]
        symbol     = r["symbol"]
        last_close = r["status"]["last_close"]
        ath_close  = r["status"]["ath_close"]
        dd         = r["status"]["drawdown"]
        li_rows    = []
        for tr in r["status"]["threshold_rows"]:
            color = "#c33" if tr["hit"] else "#2a7"
            li_rows.append(
                f"<li>-{tr['label']}: {tr['level']:,.2f} "
                f"– <b style='color:{color}'>{'TRIGGERED' if tr['hit'] else 'not triggered'}</b></li>"
            )
        sections.append(f"""
<section style="margin-bottom:24px">
  <h2 style="margin:6px 0">{name} — {symbol}</h2>
  <div>Last close: <b>{last_close:,.2f}</b> &nbsp;|&nbsp; ATH close: <b>{ath_close:,.2f}</b> &nbsp;|&nbsp; Drawdown: <b>{fmt_pct(dd)}</b></div>
  <ul style="line-height:1.7;margin-top:8px">
    {''.join(li_rows)}
  </ul>
</section>
""")
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Multi-Asset Drawdown Dashboard</title>
<style>
body {{ font-family: system-ui, Segoe UI, Arial, sans-serif; max-width: 900px; margin: 32px auto }}
h1 {{ margin-bottom: 8px }}
small {{ color:#666 }}
hr {{ border:none; border-top:1px solid #eee; margin: 24px 0 }}
</style>
</head><body>
<h1>US Market Drawdown Dashboard <small>(updated {now_str})</small></h1>
{''.join(sections)}
<hr>
<p>Data source: Yahoo Finance (daily close). Thresholds are calculated from all-time closing highs.</p>
</body></html>"""
    return html

def compose_email(results, crossed):
    """Create a consolidated email (daily status + any threshold crossings)."""
    lines = []
    for r in results:
        name       = r["name"]
        symbol     = r["symbol"]
        last_close = r["status"]["last_close"]
        ath_close  = r["status"]["ath_close"]
        dd         = r["status"]["drawdown"]
        lines.append(f"{name} ({symbol})\n  Last: {last_close:,.2f} | ATH: {ath_close:,.2f} | DD: {fmt_pct(dd)}")
        for tr in r["status"]["threshold_rows"]:
            lines.append(f"  • -{tr['label']}: {tr['level']:,.2f} – {'TRIGGERED' if tr['hit'] else 'not triggered'}")

    crossed_lines = []
    if crossed:
        crossed_lines.append("Crossed thresholds today:")
        for c in crossed:
            crossed_lines.append(f"• {c['name']} ({c['symbol']}): -{c['label']} at {c['level']:,.2f}")
    else:
        crossed_lines.append("Crossed thresholds today: (none)")

    subject = "Daily status: US indices & stocks"
    body = (
        f"US Market — Daily Status ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')})\n\n"
        + "\n".join(lines) + "\n\n" + "\n".join(crossed_lines)
        + "\n\n(You are receiving this because the test-daily email block is enabled.)"
    )
    return subject, body

def main():
    state = load_state()  # { symbol: { '15%': 'sent'/'armed', ... }, ... }
    results = []
    crossed_today = []

    for item in WATCHLIST:
        symbol     = item["symbol"]
        name       = item.get("name", symbol)
        thresholds = item.get("thresholds", [0.85, 0.80, 0.75, 0.70])

        status = gather_ticker_status(symbol, thresholds)
        if status is None:
            print(f"[WARN] No data for {symbol}, skipping.")
            continue

        # initialize per-symbol state bucket
        bucket = state.get(symbol, {})

        # crossing logic
        for tr in status["threshold_rows"]:
            label = tr["label"]
            level = tr["level"]
            hit   = tr["hit"]
            prev  = bucket.get(label, "armed")  # armed → not yet sent

            if hit and prev != "sent":
                crossed_today.append({"symbol": symbol, "name": name, "label": label, "level": level})
                bucket[label] = "sent"
            if not hit and prev == "sent":
                bucket[label] = "armed"

        state[symbol] = bucket
        results.append({"symbol": symbol, "name": name, "status": status})

    save_state(state)

    # Write dashboard
    html = compose_dashboard_html(results)
    os.makedirs("docs", exist_ok=True)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    # Alerts when thresholds cross (optional; keep as-is)
    if crossed_today:
        subject = "Threshold alert(s): " + ", ".join([f"{c['name']} -{c['label']}" for c in crossed_today])
        body = "\n".join([f"• {c['name']} ({c['symbol']}) crossed -{c['label']} at {c['level']:,.2f}" for c in crossed_today])
        send_email(subject, body)

    # ================================================================================
    # === TEST DAILY EMAIL BLOCK (send a heartbeat email every run — delete later) ===
    # ================================================================================
    try:
        subject, body = compose_email(results, crossed_today)
        send_email(subject, body)
    except Exception as e:
        print(f"[TEST DAILY EMAIL] Failed to send status email: {e}")
    # ================================================================================
    # === END TEST DAILY EMAIL BLOCK ================================================
    # ===============================================================================

if __name__ == "__main__":
    main()
