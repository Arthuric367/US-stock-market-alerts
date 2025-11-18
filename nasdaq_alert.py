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

    if alerts:
        msg = "\n".join([f"• -{n} at {level:,.2f} (last close {last_close:,.2f})" for (n, level) in alerts])
        subject = f"IXIC alert: {' & '.join(['-'+n for (n,_) in alerts])} crossed"
        body = f"Nasdaq Composite (IXIC)\nLast: {last_close:,.2f}\nATH (close): {ath_close:,.2f}\nDrawdown: {dd*100:.2f}%\n\n{msg}"
        send_email(subject, body)

if __name__ == "__main__":
    main()
