# Us, Daily: Python version (Flask + SQLite)

A mobile-first web app you install on your home screen. Everything is Python (plus small HTML templates).
Tabs: Goals (with daily habits), Study, Check-in, Savings, Week.

## Run it on your computer first
    pip install flask
    python app.py
Open http://localhost:5000. To try it on your phone, connect both to the same Wi-Fi and open http://<your-computer-ip>:5000.

## Put it online free with PythonAnywhere (gives you yourname.pythonanywhere.com)
1. Sign up at pythonanywhere.com (free "Beginner" account). **Your username becomes your link**, so choose something like
   `kevandamy` -> https://kevandamy.pythonanywhere.com
2. **Files** tab: create a folder `us_daily` and upload everything from this project, keeping the `templates/` and `static/` folders.
3. **Web** tab > Add a new web app > Manual configuration > latest Python 3.x.
4. Click the WSGI configuration file link, delete its contents and paste (change YOURUSERNAME and the timezone):

       import os, sys
       path = '/home/YOURUSERNAME/us_daily'
       if path not in sys.path:
           sys.path.insert(0, path)
       os.environ['APP_TZ'] = 'UTC'   # your timezone, e.g. 'America/New_York' or 'Africa/Nairobi'
       from app import app as application

5. (Recommended) Web tab > Static files: URL `/static/`, directory `/home/YOURUSERNAME/us_daily/static`.
6. Press the green **Reload** button and open your link.

## First use
1. You: open the link > Create an account > "Create our space". The Goals page shows a 6-character invite code.
2. Her: open the same link > Create an account > enter the code > Join.
3. Install it: Android Chrome menu > Install app / Add to Home screen. iPhone Safari Share > Add to Home Screen.

The pages refresh themselves every 30 seconds (only when you're not typing) so you see each other's updates.

## Offline support
- **Pages:** every page you've opened is saved on the phone. With no signal, the app still opens and shows the last data it loaded.
- **Changes:** ticking goals, adding sessions, check-ins and savings still work offline. They're stored on the phone, a banner shows how many are waiting, and they send automatically (in order) when you reconnect.
- **Dates:** a goal added offline at 11pm still lands on that day, even if it syncs after midnight.
- **Limits:** you can't see your partner's new changes until you're back online. Open every tab once while online so it's saved for offline use. If you both change the same thing offline, the last sync wins. Don't clear browser data while changes are waiting, or they're lost.
- **HTTPS needed:** offline mode only works on PythonAnywhere (HTTPS) or `localhost`. Over plain `http://192.168...` on your Wi-Fi the app works but won't save pages.
- Signing out wipes the saved pages from that phone.
- After you update the files on the server, reload the web app. Phones pick up the new version the next time they're online. If changes to static files don't appear, change `V = 'us-daily-v1'` in `static/sw.js` to `v2`.

## Keep it healthy
- Free PythonAnywhere apps expire after 3 months unless you press **"Run until 3 months from today"** on the Web tab.
- Back up by downloading `us_daily.db` from the Files tab now and then. It holds all your data.
- Once you've both signed up, stop strangers creating accounts: in the WSGI file add `os.environ['ALLOW_REGISTER'] = '0'` and reload.
- Passwords are stored hashed. There is no email reset, so if one is forgotten, delete that row from the `users` table or ask me for a reset script.

## Project layout
    app.py              all the Python: database, routes, logic
    templates/          the pages (Jinja HTML)
    static/             manifest.json, icons, sw.js (offline pages), app.js (offline queue)
    requirements.txt

## Making changes
- New tab: add a table in SCHEMA, a route in app.py, and a template, then add it to the nav list in templates/base.html.
- Colours and layout: the CSS is at the top of templates/base.html.
