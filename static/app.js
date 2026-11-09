/* Us, Daily: offline queue + auto refresh.
   Every form POST goes through fetch(). If the network is down the change is saved on this phone
   and replayed (in order) as soon as the connection is back. */
(function () {
  var KEY = 'us_queue';
  var net = document.getElementById('net');
  var flushing = false;

  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(function () {});

  function q() { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { return []; } }
  function save(a) { try { localStorage.setItem(KEY, JSON.stringify(a)); } catch (e) {} }

  function banner() {
    if (!net) return;
    var n = q().length, off = !navigator.onLine;
    if (!off && !n) { net.hidden = true; return; }
    net.hidden = false;
    net.textContent = (off ? '\uD83D\uDCF4 You\u2019re offline. Showing saved data. ' : '') +
      (n ? '\u23F3 ' + n + ' change' + (n > 1 ? 's' : '') + ' waiting to sync.' : 'Changes you make will sync when you\u2019re back online.');
  }

  // redirect:'manual' -> the server answered (it redirects after saving). Only a network failure throws.
  function post(url, body) {
    return fetch(url, { method: 'POST', credentials: 'same-origin', redirect: 'manual',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: body });
  }

  async function flush() {
    if (flushing || !navigator.onLine) return;
    var a = q();
    if (!a.length) return;
    flushing = true;
    var sent = 0;
    try {
      while (a.length) {
        await post(a[0].url, a[0].body + '&_ts=' + a[0].ts);
        a.shift(); sent++; save(a);
      }
    } catch (e) { /* still offline: keep the rest for later */ }
    flushing = false;
    banner();
    if (sent && !a.length) location.reload();
  }

  // Instant visual feedback for changes saved offline.
  function optimistic(f, url) {
    var chk = f.querySelector('.chk'), item = f.closest('.item');
    if (chk && item) { item.classList.toggle('done'); chk.textContent = chk.textContent.trim() === '\u2610' ? '\u2611' : '\u2610'; return; }
    if (f.querySelector('.x')) { var it = f.closest('.item,.entry'); if (it) it.style.opacity = '.35'; return; }
    if (/\/add$/.test(url)) {
      [].forEach.call(f.querySelectorAll('input[type=text],input[type=number],textarea'), function (i) { i.value = ''; });
    }
  }

  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (e.defaultPrevented || (f.method || '').toLowerCase() !== 'post') return;
    e.preventDefault();
    var url = f.getAttribute('action') || location.pathname;
    var body = new URLSearchParams(new FormData(f)).toString();
    var ts = Date.now();
    post(url, body).then(function () { location.reload(); }).catch(function () {
      var a = q(); a.push({ url: url, body: body, ts: ts }); save(a);
      optimistic(f, url); banner();
    });
  });

  // Signing out wipes saved pages so the next person on this phone can't see them.
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href="/logout"]');
    if (!a) return;
    if (q().length && !confirm('You have changes that haven\u2019t synced yet. Sign out anyway and lose them?')) { e.preventDefault(); return; }
    try { localStorage.removeItem(KEY); } catch (x) {}
    if (navigator.serviceWorker && navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage('clear');
  });

  window.addEventListener('online', function () { banner(); flush(); });
  window.addEventListener('offline', banner);
  setInterval(flush, 15000);

  // Pick up your partner's changes: refresh every 30s, but only when online and not typing.
  setInterval(function () {
    if (!navigator.onLine || q().length) return;
    var f = [].slice.call(document.querySelectorAll('input[type=text],input[type=number],textarea'));
    if (f.every(function (x) { return !x.value; })) location.reload();
  }, 30000);

  banner();
  flush();
})();
