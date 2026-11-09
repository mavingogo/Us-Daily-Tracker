"""Us, Daily: a shared goals / study / check-in / savings tracker for two people.
Pure Python (Flask + SQLite). Run locally:  python app.py   then open http://localhost:5000
"""
import os, sqlite3, secrets
from datetime import datetime, timedelta
from functools import wraps
from zoneinfo import ZoneInfo
from flask import Flask, g, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "us_daily.db")
TZ = ZoneInfo(os.environ.get("APP_TZ", "UTC"))   # set APP_TZ to your timezone so "today" is correct
MOODS = ["", "😞", "😕", "😐", "🙂", "😄"]

def _secret():
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    p = os.path.join(BASE, ".secret_key")
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write(secrets.token_hex(32))
    return open(p).read()

app = Flask(__name__)
app.secret_key = _secret()
app.permanent_session_lifetime = timedelta(days=365)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
app.jinja_env.globals.update(MOODS=MOODS)

SCHEMA = """
CREATE TABLE IF NOT EXISTS couples(id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, pw TEXT NOT NULL,
  name TEXT NOT NULL, couple_id INTEGER REFERENCES couples(id));
CREATE TABLE IF NOT EXISTS goals(id INTEGER PRIMARY KEY, couple_id INT, user_id INT, date TEXT, text TEXT, done INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS habits(id INTEGER PRIMARY KEY, couple_id INT, user_id INT, text TEXT);
CREATE TABLE IF NOT EXISTS hdone(habit_id INT, date TEXT, PRIMARY KEY(habit_id, date));
CREATE TABLE IF NOT EXISTS study(id INTEGER PRIMARY KEY, couple_id INT, user_id INT, date TEXT, subject TEXT, minutes INT, notes TEXT);
CREATE TABLE IF NOT EXISTS checkins(couple_id INT, user_id INT, date TEXT, mood INT, good TEXT, thanks TEXT, tmr TEXT,
  PRIMARY KEY(user_id, date));
CREATE TABLE IF NOT EXISTS saves(id INTEGER PRIMARY KEY, couple_id INT, user_id INT, date TEXT, amount REAL, note TEXT);
CREATE TABLE IF NOT EXISTS savings(couple_id INTEGER PRIMARY KEY, name TEXT, target REAL, cur TEXT);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, couple_id INT, user_id INT, text TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""
with sqlite3.connect(DB) as _c:
    _c.executescript(SCHEMA)

# ---------- helpers ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def _close(_):
    d = g.pop("db", None)
    if d:
        d.close()

def today_d():
    return datetime.now(TZ).date()

def today():
    return today_d().isoformat()

def day():
    """Date a change belongs to. Changes queued while offline carry their original timestamp (_ts),
    so a goal added offline at 11pm still lands on that day when it syncs after midnight."""
    try:
        d = datetime.fromtimestamp(int(request.form.get("_ts", "")) / 1000, TZ).date()
        if 0 <= (today_d() - d).days <= 30:
            return d.isoformat()
    except (ValueError, OverflowError, OSError):
        pass
    return today()

def last_days(n=7):
    t = today_d()
    return [(t - timedelta(days=i)).isoformat() for i in range(n)]

@app.before_request
def load_user():
    uid = session.get("uid")
    g.user = db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone() if uid else None

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not g.user:
            return redirect(url_for("login"))
        if not g.user["couple_id"]:
            return redirect(url_for("pair"))
        return f(*a, **k)
    return w

def members():
    rows = db().execute("SELECT * FROM users WHERE couple_id=? ORDER BY id", (g.user["couple_id"],)).fetchall()
    return sorted(rows, key=lambda r: r["id"] != g.user["id"])  # me first

def new_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))

@app.template_filter("money")
def money(v):
    v = float(v or 0)
    return f"{v:,.0f}" if v.is_integer() else f"{v:,.2f}"

def mins(m):
    m = int(m or 0)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"
app.jinja_env.filters["mins"] = mins

def time_ago(ts):
    if not ts:
        return ""
    try:
        if isinstance(ts, str):
            ts_clean = ts.replace(" ", "T")
            if not ts_clean.endswith("Z") and "+" not in ts_clean:
                dt = datetime.fromisoformat(ts_clean).replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
            else:
                dt = datetime.fromisoformat(ts_clean).astimezone(TZ)
        else:
            dt = ts.astimezone(TZ)
        t = datetime.now(TZ)
        if dt.date() == t.date():
            return dt.strftime("%I:%M %p").lstrip("0")
        elif (t.date() - dt.date()).days == 1:
            return "Yesterday " + dt.strftime("%I:%M %p").lstrip("0")
        elif dt.year == t.year:
            return dt.strftime("%b %d, %I:%M %p").replace(" 0", " ")
        else:
            return dt.strftime("%b %d %Y, %I:%M %p")
    except Exception:
        return str(ts)[11:16] if len(str(ts)) >= 16 else str(ts)
app.jinja_env.filters["time_ago"] = time_ago

def streak(dates):
    t, d, n = today_d(), today_d(), 0
    while True:
        if d.isoformat() in dates:
            n += 1
        elif d != t:
            break
        d -= timedelta(days=1)
    return n

# ---------- accounts ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if os.environ.get("ALLOW_REGISTER", "1") == "0":
            flash("Sign-ups are closed.")
            return render_template("auth.html", mode="register")
        u = request.form["username"].strip().lower()
        name = request.form["name"].strip()
        pw = request.form["password"]
        if not u or not name or len(pw) < 6:
            flash("Fill in every field. Password needs 6+ characters.")
        elif db().execute("SELECT 1 FROM users WHERE username=?", (u,)).fetchone():
            flash("That username is taken.")
        else:
            cur = db().execute("INSERT INTO users(username,pw,name) VALUES(?,?,?)", (u, generate_password_hash(pw), name))
            db().commit()
            session.permanent = True
            session["uid"] = cur.lastrowid
            return redirect(url_for("pair"))
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        row = db().execute("SELECT * FROM users WHERE username=?", (request.form["username"].strip().lower(),)).fetchone()
        if row and check_password_hash(row["pw"], request.form["password"]):
            session.permanent = True
            session["uid"] = row["id"]
            return redirect(url_for("goals"))
        flash("Wrong username or password.")
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/pair", methods=["GET", "POST"])
def pair():
    if not g.user:
        return redirect(url_for("login"))
    if g.user["couple_id"]:
        return redirect(url_for("goals"))
    if request.method == "POST":
        d = db()
        if request.form["action"] == "create":
            code = new_code()
            cid = d.execute("INSERT INTO couples(code) VALUES(?)", (code,)).lastrowid
        else:
            row = d.execute("SELECT * FROM couples WHERE code=?", (request.form["code"].strip().upper(),)).fetchone()
            if not row:
                flash("That invite code was not found.")
                return redirect(url_for("pair"))
            if d.execute("SELECT COUNT(*) FROM users WHERE couple_id=?", (row["id"],)).fetchone()[0] >= 2:
                flash("That space already has two people.")
                return redirect(url_for("pair"))
            cid = row["id"]
        d.execute("UPDATE users SET couple_id=? WHERE id=?", (cid, g.user["id"]))
        d.commit()
        return redirect(url_for("goals"))
    return render_template("pair.html")

# ---------- goals + habits ----------
@app.route("/")
@login_required
def goals():
    d, t, cid = db(), today(), g.user["couple_id"]
    ppl, data = members(), []
    for p in ppl:
        gs = d.execute("SELECT * FROM goals WHERE couple_id=? AND user_id=? AND date=? ORDER BY id", (cid, p["id"], t)).fetchall()
        hs = d.execute("""SELECT h.*, EXISTS(SELECT 1 FROM hdone x WHERE x.habit_id=h.id AND x.date=?) AS done
                          FROM habits h WHERE couple_id=? AND user_id=? ORDER BY id""", (t, cid, p["id"])).fetchall()
        total = len(gs) + len(hs)
        done = sum(x["done"] for x in gs) + sum(x["done"] for x in hs)
        data.append(dict(p=p, goals=gs, habits=hs, total=total, done=done,
                         pct=round(done / total * 100) if total else 0, mine=p["id"] == g.user["id"]))
    invite = d.execute("SELECT code FROM couples WHERE id=?", (cid,)).fetchone()["code"] if len(ppl) < 2 else None
    return render_template("goals.html", data=data, invite=invite, label=today_d().strftime("%A, %B %d"))

@app.post("/goals/add")
@login_required
def goal_add():
    t = request.form["text"].strip()
    if t:
        db().execute("INSERT INTO goals(couple_id,user_id,date,text) VALUES(?,?,?,?)", (g.user["couple_id"], g.user["id"], day(), t[:120]))
        db().commit()
    return redirect(url_for("goals"))

@app.post("/goals/<int:gid>/toggle")
@login_required
def goal_toggle(gid):
    db().execute("UPDATE goals SET done=1-done WHERE id=? AND user_id=?", (gid, g.user["id"]))
    db().commit()
    return redirect(url_for("goals"))

@app.post("/goals/<int:gid>/delete")
@login_required
def goal_delete(gid):
    db().execute("DELETE FROM goals WHERE id=? AND user_id=?", (gid, g.user["id"]))
    db().commit()
    return redirect(url_for("goals"))

@app.post("/habits/add")
@login_required
def habit_add():
    t = request.form["text"].strip()
    if t:
        db().execute("INSERT INTO habits(couple_id,user_id,text) VALUES(?,?,?)", (g.user["couple_id"], g.user["id"], t[:80]))
        db().commit()
    return redirect(url_for("goals"))

@app.post("/habits/<int:hid>/toggle")
@login_required
def habit_toggle(hid):
    d, dd = db(), day()
    if d.execute("SELECT 1 FROM habits WHERE id=? AND user_id=?", (hid, g.user["id"])).fetchone():
        if d.execute("SELECT 1 FROM hdone WHERE habit_id=? AND date=?", (hid, dd)).fetchone():
            d.execute("DELETE FROM hdone WHERE habit_id=? AND date=?", (hid, dd))
        else:
            d.execute("INSERT INTO hdone VALUES(?,?)", (hid, dd))
        d.commit()
    return redirect(url_for("goals"))

@app.post("/habits/<int:hid>/delete")
@login_required
def habit_delete(hid):
    d = db()
    if d.execute("SELECT 1 FROM habits WHERE id=? AND user_id=?", (hid, g.user["id"])).fetchone():
        d.execute("DELETE FROM hdone WHERE habit_id=?", (hid,))
        d.execute("DELETE FROM habits WHERE id=?", (hid,))
        d.commit()
    return redirect(url_for("goals"))

# ---------- messages / chat ----------
@app.route("/messages")
@login_required
def messages():
    d, cid = db(), g.user["couple_id"]
    ppl = members()
    partner = next((p for p in ppl if p["id"] != g.user["id"]), None)
    rows = d.execute("""SELECT m.*, u.name, u.username
                        FROM messages m
                        JOIN users u ON u.id = m.user_id
                        WHERE m.couple_id = ?
                        ORDER BY m.id ASC""", (cid,)).fetchall()
    invite = d.execute("SELECT code FROM couples WHERE id=?", (cid,)).fetchone()["code"] if len(ppl) < 2 else None
    return render_template("messages.html", messages=rows, partner=partner, invite=invite)

@app.post("/messages/send")
@login_required
def message_send():
    text = request.form.get("text", "").strip()
    if text:
        db().execute("INSERT INTO messages(couple_id, user_id, text) VALUES(?,?,?)",
                     (g.user["couple_id"], g.user["id"], text[:1000]))
        db().commit()
    return redirect(url_for("messages"))

@app.post("/messages/<int:mid>/delete")
@login_required
def message_delete(mid):
    db().execute("DELETE FROM messages WHERE id=? AND user_id=?", (mid, g.user["id"]))
    db().commit()
    return redirect(url_for("messages"))

@app.route("/messages/poll")
@login_required
def message_poll():
    try:
        after_id = int(request.args.get("after", 0))
    except (ValueError, TypeError):
        after_id = 0
    d, cid = db(), g.user["couple_id"]
    rows = d.execute("""SELECT m.id, m.user_id, m.text, m.created_at, u.name
                        FROM messages m JOIN users u ON u.id = m.user_id
                        WHERE m.couple_id = ? AND m.id > ?
                        ORDER BY m.id ASC""", (cid, after_id)).fetchall()
    return [{
        "id": r["id"],
        "user_id": r["user_id"],
        "mine": r["user_id"] == g.user["id"],
        "name": r["name"],
        "text": r["text"],
        "time": time_ago(r["created_at"])
    } for r in rows]

# ---------- study ----------
@app.route("/study")
@login_required
def study():
    d, cid, days = db(), g.user["couple_id"], last_days(7)
    stats = []
    for p in members():
        rows = d.execute("SELECT date, minutes FROM study WHERE couple_id=? AND user_id=?", (cid, p["id"])).fetchall()
        stats.append(dict(p=p, mine=p["id"] == g.user["id"],
                          today=sum(r["minutes"] for r in rows if r["date"] == today()),
                          week=sum(r["minutes"] for r in rows if r["date"] in days),
                          streak=streak({r["date"] for r in rows})))
    sessions = d.execute("""SELECT s.*, u.name FROM study s JOIN users u ON u.id=s.user_id
                            WHERE s.couple_id=? AND s.date=? ORDER BY s.id DESC""", (cid, today())).fetchall()
    return render_template("study.html", stats=stats, sessions=sessions)

@app.post("/study/add")
@login_required
def study_add():
    subject, notes = request.form["subject"].strip(), request.form.get("notes", "").strip()
    try:
        m = int(request.form["minutes"])
    except ValueError:
        m = 0
    if subject and 0 < m <= 1440:
        db().execute("INSERT INTO study(couple_id,user_id,date,subject,minutes,notes) VALUES(?,?,?,?,?,?)",
                     (g.user["couple_id"], g.user["id"], day(), subject[:60], m, notes[:300]))
        db().commit()
    return redirect(url_for("study"))

@app.post("/study/<int:sid>/delete")
@login_required
def study_delete(sid):
    db().execute("DELETE FROM study WHERE id=? AND user_id=?", (sid, g.user["id"]))
    db().commit()
    return redirect(url_for("study"))

# ---------- check-in ----------
@app.route("/checkin", methods=["GET", "POST"])
@login_required
def checkin():
    d, cid = db(), g.user["couple_id"]
    if request.method == "POST":
        try:
            mood = max(0, min(5, int(request.form.get("mood", 0))))
        except ValueError:
            mood = 0
        d.execute("""INSERT INTO checkins(couple_id,user_id,date,mood,good,thanks,tmr) VALUES(?,?,?,?,?,?,?)
                     ON CONFLICT(user_id,date) DO UPDATE SET mood=excluded.mood, good=excluded.good,
                     thanks=excluded.thanks, tmr=excluded.tmr""",
                  (cid, g.user["id"], day(), mood, request.form["good"].strip()[:300],
                   request.form["thanks"].strip()[:300], request.form["tmr"].strip()[:300]))
        d.commit()
        flash("Saved ✓")
        return redirect(url_for("checkin"))
    mine = d.execute("SELECT * FROM checkins WHERE user_id=? AND date=?", (g.user["id"], today())).fetchone()
    recent = d.execute("""SELECT c.*, u.name, u.id AS uid FROM checkins c JOIN users u ON u.id=c.user_id
                          WHERE c.couple_id=? ORDER BY c.date DESC, u.id LIMIT 14""", (cid,)).fetchall()
    return render_template("checkin.html", mine=mine, recent=recent)

# ---------- savings ----------
@app.route("/savings")
@login_required
def savings():
    d, cid = db(), g.user["couple_id"]
    goal = d.execute("SELECT * FROM savings WHERE couple_id=?", (cid,)).fetchone()
    rows = d.execute("""SELECT s.*, u.name FROM saves s JOIN users u ON u.id=s.user_id
                        WHERE s.couple_id=? ORDER BY s.id DESC LIMIT 10""", (cid,)).fetchall()
    per = d.execute("""SELECT u.name, COALESCE(SUM(s.amount),0) AS total FROM users u
                       LEFT JOIN saves s ON s.user_id=u.id WHERE u.couple_id=? GROUP BY u.id ORDER BY u.id""", (cid,)).fetchall()
    total = sum(p["total"] for p in per)
    pct = min(100, round(total / goal["target"] * 100)) if goal and goal["target"] else 0
    return render_template("savings.html", goal=goal, rows=rows, per=per, total=total, pct=pct)

@app.post("/savings/goal")
@login_required
def savings_goal():
    try:
        target = float(request.form["target"])
    except ValueError:
        target = 0
    name = request.form["name"].strip()
    if name and target > 0:
        db().execute("""INSERT INTO savings(couple_id,name,target,cur) VALUES(?,?,?,?)
                        ON CONFLICT(couple_id) DO UPDATE SET name=excluded.name, target=excluded.target, cur=excluded.cur""",
                     (g.user["couple_id"], name[:60], target, request.form.get("cur", "").strip()[:6]))
        db().commit()
    return redirect(url_for("savings"))

@app.post("/savings/add")
@login_required
def savings_add():
    try:
        a = float(request.form["amount"])
    except ValueError:
        a = 0
    if a > 0:
        db().execute("INSERT INTO saves(couple_id,user_id,date,amount,note) VALUES(?,?,?,?,?)",
                     (g.user["couple_id"], g.user["id"], day(), a, request.form.get("note", "").strip()[:80]))
        db().commit()
    return redirect(url_for("savings"))

@app.post("/savings/<int:sid>/delete")
@login_required
def savings_delete(sid):
    db().execute("DELETE FROM saves WHERE id=? AND user_id=?", (sid, g.user["id"]))
    db().commit()
    return redirect(url_for("savings"))

# ---------- weekly summary ----------
@app.route("/week")
@login_required
def week():
    d, cid, days = db(), g.user["couple_id"], last_days(7)
    q = ",".join("?" * len(days))
    out = []
    for p in members():
        uid = p["id"]
        gs = d.execute(f"SELECT COUNT(*) n, COALESCE(SUM(done),0) dn FROM goals WHERE couple_id=? AND user_id=? AND date IN ({q})", (cid, uid, *days)).fetchone()
        hb = d.execute(f"SELECT COUNT(*) FROM hdone x JOIN habits h ON h.id=x.habit_id WHERE h.user_id=? AND x.date IN ({q})", (uid, *days)).fetchone()[0]
        st = d.execute(f"SELECT subject, SUM(minutes) m FROM study WHERE couple_id=? AND user_id=? AND date IN ({q}) GROUP BY subject ORDER BY m DESC", (cid, uid, *days)).fetchall()
        ck = d.execute(f"SELECT COUNT(*) n, AVG(NULLIF(mood,0)) a FROM checkins WHERE couple_id=? AND user_id=? AND date IN ({q})", (cid, uid, *days)).fetchone()
        sv = d.execute(f"SELECT COALESCE(SUM(amount),0) FROM saves WHERE couple_id=? AND user_id=? AND date IN ({q})", (cid, uid, *days)).fetchone()[0]
        out.append(dict(p=p, mine=uid == g.user["id"], goals_done=gs["dn"], goals_total=gs["n"], habits=hb,
                        study=sum(r["m"] for r in st), top=st[0]["subject"] if st else None,
                        checkins=ck["n"], mood=MOODS[round(ck["a"])] if ck["a"] else "", saved=sv))
    goal = d.execute("SELECT cur FROM savings WHERE couple_id=?", (cid,)).fetchone()
    return render_template("week.html", out=out, cur=(goal["cur"] if goal else "") or "")

# ---------- offline support ----------
@app.route("/sw.js")
def service_worker():
    r = send_from_directory(os.path.join(BASE, "static"), "sw.js", mimetype="application/javascript")
    r.headers["Cache-Control"] = "no-cache"
    return r

@app.route("/offline")
def offline():
    return render_template("offline.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
