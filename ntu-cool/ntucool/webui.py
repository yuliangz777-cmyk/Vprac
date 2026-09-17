"""本機網頁介面的前端（單一檔案，內嵌在 Python 裡以便手機安裝時一起帶走）。"""

PAGE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%93%9A%3C/text%3E%3C/svg%3E">
<title>NTU COOL 同步</title>
<style>
:root{
  --bg:#f6f6f7; --card:#fff; --text:#16161a; --muted:#6b6b76; --line:#e3e3e8;
  --accent:#0b62d6; --accent-text:#fff; --ok:#0a7d46; --warn:#9a5b00; --err:#b3261e;
  --radius:14px;
}
@media (prefers-color-scheme:dark){
  :root{ --bg:#101014; --card:#191920; --text:#eceaf0; --muted:#9a9aa6; --line:#2c2c36;
         --accent:#5c9dff; --accent-text:#0b1220; --ok:#4ade80; --warn:#fbbf24; --err:#ff6b6b; }
}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:var(--bg);color:var(--text);
  font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC",sans-serif;
  padding-bottom:calc(16px + env(safe-area-inset-bottom))}
.wrap{max-width:820px;margin:0 auto}
h1{font-size:1.35rem;margin:.2rem 0 1rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px;margin-bottom:14px}
.meta{display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--muted);font-size:.85rem;margin-bottom:12px}
.meta b{color:var(--text);font-weight:600}
button{font:inherit;font-weight:600;border:0;border-radius:10px;padding:13px 18px;
  background:var(--accent);color:var(--accent-text);cursor:pointer;width:100%}
button:disabled{opacity:.5;cursor:default}
button.ghost{background:transparent;color:var(--accent);border:1px solid var(--line);margin-top:8px}
label.opt{display:flex;align-items:center;gap:9px;margin:9px 0;font-size:.95rem}
input[type=text]{font:inherit;width:100%;padding:11px 12px;border:1px solid var(--line);
  border-radius:10px;background:var(--bg);color:var(--text);margin-top:4px}
input[type=checkbox]{width:19px;height:19px;accent-color:var(--accent);flex:none}
#log{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px;
  font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;
  word-break:break-word;max-height:46vh;overflow:auto;margin-top:12px}
.hide{display:none}
.status{font-weight:600;margin-bottom:4px}
.status.running{color:var(--accent)} .status.done{color:var(--ok)} .status.error{color:var(--err)}
details{border-top:1px solid var(--line);padding-top:10px;margin-top:10px}
summary{cursor:pointer;font-weight:600}
ul.files{list-style:none;padding-left:0;margin:8px 0 0}
ul.files li{padding:7px 0;border-bottom:1px solid var(--line);font-size:.92rem}
ul.files li:last-child{border-bottom:0}
ul.files a{color:var(--accent);text-decoration:none;word-break:break-all}
.size{color:var(--muted);font-size:.8rem;margin-left:6px}
.empty{color:var(--muted);font-size:.9rem}
</style>
</head>
<body><div class="wrap">
<h1>NTU COOL 同步</h1>

<div class="card">
  <div class="meta" id="meta"><span>載入中…</span></div>
  <label class="opt"><input type="checkbox" id="pdfOnly"> 只下載 PDF／簡報</label>
  <label class="opt"><input type="checkbox" id="skipBig"> 略過 50MB 以上的大檔</label>
  <label class="opt" style="display:block">
    只同步這些課程（留空＝全部，可用課號或課名，逗號分隔）
    <input type="text" id="filter" placeholder="例如：CSIE1212, 演算法">
  </label>
  <button id="go">開始同步</button>
  <button class="ghost" id="refresh">重新整理檔案清單</button>
</div>

<div class="card hide" id="logCard">
  <div class="status" id="status"></div>
  <div id="log"></div>
</div>

<div class="card">
  <b>已抓下來的課程</b>
  <div id="courses"><p class="empty">還沒有資料，按上面的「開始同步」。</p></div>
</div>
</div>
<script>
const KEY = new URLSearchParams(location.search).get('k') || '';
const api = (path, opts) => fetch(path + (path.includes('?') ? '&' : '?') + 'k=' + encodeURIComponent(KEY), opts);
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function loadStatus(){
  try{
    const s = await (await api('/api/status')).json();
    $('meta').innerHTML = [
      s.user ? `帳號 <b>${esc(s.user)}</b>` : '',
      `站台 <b>${esc(s.base_url)}</b>`,
      `輸出 <b>${esc(s.out_dir)}</b>`,
      s.last_sync ? `上次同步 <b>${esc(s.last_sync)}</b>` : '尚未同步過',
    ].filter(Boolean).map(h => `<span>${h}</span>`).join('');
  }catch(e){ $('meta').textContent = '無法連上本機伺服器：' + e; }
}

async function loadCourses(){
  const box = $('courses');
  try{
    const data = await (await api('/api/files')).json();
    if(!data.courses.length){ box.innerHTML = '<p class="empty">還沒有資料，按上面的「開始同步」。</p>'; return; }
    box.innerHTML = data.courses.map(c => `
      <details>
        <summary>${esc(c.name)} <span class="size">${c.files.length} 個檔案</span></summary>
        <ul class="files">${c.files.map(f =>
          `<li><a href="/files/${encodeURI(f.path)}?k=${encodeURIComponent(KEY)}" target="_blank" rel="noopener">${esc(f.name)}</a><span class="size">${esc(f.size)}</span></li>`
        ).join('')}</ul>
      </details>`).join('');
  }catch(e){ box.innerHTML = '<p class="empty">讀取失敗：' + esc(e) + '</p>'; }
}

let polling = null;
async function poll(from){
  const res = await (await api('/api/progress?from=' + from)).json();
  if(res.lines.length){
    $('log').textContent += res.lines.join('\\n') + '\\n';
    $('log').scrollTop = $('log').scrollHeight;
  }
  const st = $('status');
  st.className = 'status ' + res.status;
  st.textContent = {running:'同步中…', done:'完成', error:'發生錯誤', idle:''}[res.status] || '';
  if(res.status === 'running'){
    polling = setTimeout(() => poll(from + res.lines.length), 700);
  }else{
    $('go').disabled = false;
    loadStatus(); loadCourses();
  }
}

$('go').onclick = async () => {
  $('go').disabled = true;
  $('logCard').classList.remove('hide');
  $('log').textContent = '';
  const body = JSON.stringify({
    pdf_only: $('pdfOnly').checked,
    skip_big: $('skipBig').checked,
    courses: $('filter').value,
  });
  const res = await api('/api/sync', {method:'POST', headers:{'Content-Type':'application/json'}, body});
  if(!res.ok){ $('status').className='status error'; $('status').textContent = '無法開始：' + await res.text(); $('go').disabled = false; return; }
  clearTimeout(polling); poll(0);
};
$('refresh').onclick = loadCourses;
loadStatus(); loadCourses();
</script>
</body></html>
"""
