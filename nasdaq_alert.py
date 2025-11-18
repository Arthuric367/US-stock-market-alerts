import os, sys, math, json, smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone
import yfinance as yf
import pandas as pd

TICKER = "^IXIC"
THRESHOLDS = [0.85, 0.80, 0.75, 0.70]  # -15, -20, -25, -30%
STATE_FILE = "state.json"
OUT_HTML = "docs/index.html"  # publish as GitHub Pages

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
        return json.load(open(STATE_FILE))
    return {}

def save_state(st):
    json.dump(st, open(STATE_FILE, "w"))

def main():
    # Get at least 15 years of daily closes
    df = yf.download(TICKER, period="15y", interval="1d", auto_adjust=False, progress=False)
    if df.empty:
        print("No data")
        sys.exit(1)

    last_close = float(df["Close"].iloc[-1])
    ath_close  = float(df["Close"].max())
    dd = last_close / ath_close - 1.0

    st = load_state()
    alerts = []
    for f in THRESHOLDS:
        name = f"{int((1-f)*100)}%"
        level = ath_close * f
        hit = last_close <= level
        prev = st.get(name, "armed")
        if hit and prev != "sent":
            alerts.append((name, level))
            st[name] = "sent"
        if not hit and prev == "sent":  # reset after recovery
            st[name] = "armed"

    save_state(st)

    # Create a minimal HTML dashboard
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Nasdaq Drawdown</title>
    <style>body{{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:800px;margin:40px auto}}
    .ok{{color:#2a7}} .hit{{color:#c33}}</style></head><body>
    <h1>Nasdaq Composite (IXIC) – Drawdown Dashboard</h1>
    <p>Last close: <b>{last_close:,.2f}</b><br>
       ATH close: <b>{ath_close:,.2f}</b><br>
       Drawdown: <b>{dd*100:.2f}%</b><br>
       Updated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</p>
    <h3>Thresholds</h3>
    <ul>
    {"".join(f"<li>{name}: {level:,.2f} – " + ("<span class='hit'>TRIGGERED</span>" if last_close<=level else "<span class='ok'>not triggered</span>") + "</li>" for name, level in [(f"{int((1-f)*100)}%", ath_close*f) for f in THRESHOLDS])}
    </ul>
    <p>Data source: Yahoo Finance (^IXIC daily close). All-time closing high: {ath_close:,.2f}.</p>
    </body></html>"""
    os.makedirs("docs", exist_ok=True)
    open(OUT_HTML, "w").write(html)

    if alerts:
        lines = [f"• -{n} at {level:,.2f} (last close {last_close:,.2f})" for (n, level) in alerts]
        subject = f"IXIC alert: {' & '.join(['-'+n for (n,_) in alerts])} crossed"
        body = f"Nasdaq Composite (IXIC)\nLast: {last_close:,.2f}\nATH (close): {ath_close:,.2f}\nDrawdown: {dd*100:.2f}%\n\n" + "\n".join(lines)
        send_email(subject, body)

if __name__ == "__main__":
    main()
