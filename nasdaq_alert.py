import os, json, smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone
import yfinance as yf

TICKER = "^IXIC"
THRESHOLDS = [0.85, 0.80, 0.75, 0.70]  # -15%, -20%, -25%, -30%
STATE_FILE = "state.json"
OUT_HTML = "docs/index.html"

def send_email(subject, body):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    pwd  = os.environ["SMTP_PASS"]
    to   = os.environ["TO_EMAIL"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(st):
    with open(STATE_FILE, "w") as f:
        json.dump(st, f)

# ------------------------------------------------------------------------------------
# Helper: Compose a full daily-status email (for test/daily heartbeat messages)
# ------------------------------------------------------------------------------------
def compose_status_email(last_close, ath_close, dd, thresholds, alerts):
    """
    Returns a (subject, body) tuple with a concise status report.
    `thresholds` is a list of factors (e.g., [0.85, 0.80, 0.75, 0.70]).
    `alerts` is a list of tuples like: [("15%", level_float), ...] that crossed today.
    """
    lines = []
    for f in thresholds:
        name  = f"{int((1-f)*100)}%"
        level = ath_close * f
        status = "TRIGGERED" if last_close <= level else "not triggered"
        lines.append(f"• -{name}: {level:,.2f} — {status}")

    crossed = ""
    if alerts:
        crossed = "\nCrossed thresholds today:\n" + "\n".join(
            [f"• -{n} at {lvl:,.2f}" for (n, lvl) in alerts]
        )
    else:
        crossed = "\nCrossed thresholds today: (none)"

    subject = "IXIC daily status"
    body = (
        f"Nasdaq Composite (IXIC) — Daily Status\n"
        f"Timestamp (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Last close: {last_close:,.2f}\n"
        f"ATH (close): {ath_close:,.2f}\n"
        f"Drawdown: {dd*100:.2f}%\n\n"
        f"Thresholds from ATH:\n" + "\n".join(lines) + "\n" + crossed
        + "\n\n(You are receiving this because the test-daily email block is enabled.)"
    )
    return subject, body

def main():
    df = yf.download(TICKER, period="15y", interval="1d", auto_adjust=False, progress=False)
    if df.empty:
        print("No data downloaded")
        return

    last_close = float(df["Close"].iloc[-1])
    ath_close  = float(df["Close"].max())
    dd = last_close / ath_close - 1.0

    # Alert state
    st = load_state()
    alerts = []
    for f in THRESHOLDS:
        name = f"{int((1-f)*100)}%"   # e.g. "15%"
        level = ath_close * f
        hit = last_close <= level
        prev = st.get(name, "armed")

        if hit and prev != "sent":
            alerts.append((name, level))
            st[name] = "sent"
        if not hit and prev == "sent":
            st[name] = "armed"

    save_state(st)

    # Minimal HTML dashboard
    lines = []
    for f in THRESHOLDS:
        name  = f"{int((1-f)*100)}%"
        level = ath_close * f
        status = "TRIGGERED" if last_close <= level else "not triggered"
        color = "#c33" if status == "TRIGGERED" else "#2a7"
        lines.append(f"<li>{name}: {level:,.2f} – <b style='color:{color}'>{status}</b></li>")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Nasdaq Drawdown</title>
<style>body{{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:800px;margin:40px auto}}</style>
</head><body>
<h1>Nasdaq Composite (IXIC) – Drawdown Dashboard</h1>
<p>Last close: <b>{last_close:,.2f}</b><br>
ATH close: <b>{ath_close:,.2f}</b><br>
Drawdown: <b>{dd*100:.2f}%</b><br>
Updated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</p>
<h3>Thresholds</h3>
<ul>
{''.join(lines)}
</ul>
<p>Data source: Yahoo Finance (^IXIC daily close).</p>
</body></html>"""

    os.makedirs("docs", exist_ok=True)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    # Threshold-crossing alerts (original behavior)
    if alerts:
        msg = "\n".join([f"• -{n} at {level:,.2f} (last close {last_close:,.2f})" for (n, level) in alerts])
        subject = f"IXIC alert: {' & '.join(['-'+n for (n,_) in alerts])} crossed"
        body = f"Nasdaq Composite (IXIC)\nLast: {last_close:,.2f}\nATH (close): {ath_close:,.2f}\nDrawdown: {dd*100:.2f}%\n\n{msg}"
        send_email(subject, body)

    # ================================================================================
    # === TEST DAILY EMAIL BLOCK (send a heartbeat email every run — delete later) ===
    # ================================================================================
    # This block forces a daily status email so you can confirm the automation works
    # without waiting for thresholds to be crossed. Remove after testing.
    try:
        subject, body = compose_status_email(last_close, ath_close, dd, THRESHOLDS, alerts)
        send_email(subject, body)
    except Exception as e:
        # Keep failures non-fatal to avoid stopping the workflow
        print(f"[TEST DAILY EMAIL] Failed to send status email: {e}")
    # ================================================================================
    # === END TEST DAILY EMAIL BLOCK ================================================
    # ================================================================================

if __name__ == "__main__":
