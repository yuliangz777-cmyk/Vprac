"""本機網頁介面的前端（單一檔案，內嵌在 Python 裡以便手機安裝時一起帶走）。

設計沿用 NTU Course Hub 原型：手機優先的四分頁（首頁／課程／下載／設定）。
原型裡的「課表」與「今日課程」拿掉了——NTU COOL 沒有上課時段資料，
硬填只會變成假資料。
"""

PAGE = r'''<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#f7f7f9">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Course Hub">
<link rel="manifest" href="/manifest.webmanifest?k=__KEY__">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="icon" href="/icon-192.png">
<title>NTU Course Hub</title>
<style>
*{box-sizing:border-box}
:root{
  --bg:#eceef2; --shell:#f7f7f9; --card:#fff; --line:#e7e7eb; --line-soft:#eee;
  --text:#17171a; --muted:#777; --ink:#111; --on-ink:#fff;
  --accent:#5457d6; --ok-bg:#e8f7ed; --ok:#217a3c; --warn-bg:#fdf1dc; --warn:#8a5a00;
  --err-bg:#fff0ee; --err:#b42318; --bar:#eee;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#000; --shell:#111114; --card:#1b1b1f; --line:#2c2c32; --line-soft:#26262b;
    --text:#f2f2f5; --muted:#9a9aa2; --ink:#f2f2f5; --on-ink:#111114;
    --accent:#8e91ff; --ok-bg:#12331f; --ok:#5ed08a; --warn-bg:#3a2c10; --warn:#f0c064;
    --err-bg:#3a1a17; --err:#ff9b8f; --bar:#2c2c32;
  }
}
html{background:var(--bg)}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Noto Sans TC",sans-serif;
  color:var(--text);background:var(--bg)}
button,select,input{font:inherit}
select{background:var(--card);color:var(--text);border:1px solid var(--line);
  border-radius:11px;padding:9px 11px}
.app-shell{max-width:920px;min-height:100vh;margin:auto;background:var(--shell);
  padding:0 22px calc(104px + env(safe-area-inset-bottom))}
.topbar{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--shell) 88%,transparent);
  backdrop-filter:blur(18px);display:flex;align-items:center;justify-content:space-between;
  padding:calc(20px + env(safe-area-inset-top)) 0 14px}
.topbar h1{margin:2px 0 0;font-size:28px}
.eyebrow{font-size:11px;letter-spacing:.14em;color:var(--muted)}
.avatar{width:42px;height:42px;border-radius:50%;border:0;background:var(--ink);color:var(--on-ink);font-weight:700}
.page{display:none}
.page.active{display:block}
.hide{display:none !important}
.hero{padding:26px;border-radius:28px;background:var(--ink);color:var(--on-ink);margin:10px 0 26px}
.hero h2{font-size:28px;margin:4px 0}
.hero p{margin:6px 0;color:color-mix(in srgb,var(--on-ink) 72%,transparent)}
.hero .primary{margin-top:18px;width:100%}
.primary{border:0;border-radius:14px;background:var(--on-ink);color:var(--ink);padding:14px 17px;font-weight:700;cursor:pointer}
.hero .primary{background:var(--on-ink);color:var(--ink)}
.primary:disabled{opacity:.55;cursor:default}
.compact{padding:10px 13px;background:var(--ink);color:var(--on-ink);border-radius:12px;border:0;font-weight:700}
.secondary{border:0;border-radius:12px;background:var(--bar);color:var(--text);padding:11px 14px;font-weight:600;cursor:pointer}
.link,.back{border:0;background:none;color:var(--accent);font-weight:600;cursor:pointer;padding:0}
.section-head{display:flex;align-items:center;justify-content:space-between;margin-top:26px;gap:12px}
.section-head h2,.section-head h3{margin:0}
.muted,small{color:var(--muted);display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:20px;overflow:hidden;margin-top:12px}
.row{display:flex;align-items:center;gap:14px;padding:16px 18px;border-bottom:1px solid var(--line-soft)}
.row:last-child{border:0}
.row>div{flex:1;min-width:0}
.row b{display:block;overflow-wrap:anywhere}
.pill,.ok{font-size:12px;padding:6px 10px;border-radius:999px;background:var(--ok-bg);color:var(--ok);
  white-space:nowrap;flex:none;font-weight:600;display:inline-block}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.late{background:var(--err-bg);color:var(--err)}
.pill.plain{background:var(--bar);color:var(--muted)}
.storage{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:18px}
.course-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-top:14px}
@media (max-width:380px){.course-grid{grid-template-columns:1fr}}
.course-card{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:18px;
  font:inherit;
  min-height:150px;display:flex;flex-direction:column;justify-content:space-between;gap:12px;
  cursor:pointer;text-align:left;color:inherit}
.course-card h3{margin:8px 0 3px;font-size:16px;overflow-wrap:anywhere}
.course-card:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.course-dot{width:12px;height:12px;border-radius:50%;background:var(--accent);display:block}
.download-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0}
.download-summary>div{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px}
.download-summary strong{display:block;font-size:22px}
.empty{text-align:center;padding:55px 20px;color:var(--muted)}
.empty b{color:var(--text);display:block;margin-bottom:6px}
.file-icon{font-size:34px}
.download-item{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:15px;margin:10px 0}
.progress{height:7px;background:var(--bar);border-radius:10px;margin-top:12px;overflow:hidden}
.progress span{display:block;height:100%;background:var(--ink);width:0;transition:width .3s}
.progress span.failed{background:var(--err)}
.file-row{display:flex;align-items:center;gap:13px;padding:14px 18px;border-bottom:1px solid var(--line-soft)}
.file-row:last-child{border:0}
.file-row .icon{flex:none;width:40px;height:40px;border-radius:11px;background:var(--bar);color:var(--muted);
  display:grid;place-items:center;font-size:10px;font-weight:700}
.file-row a{color:inherit;text-decoration:none;overflow-wrap:anywhere}
.switch input{display:none}
.switch span{display:block;width:44px;height:26px;background:var(--bar);border-radius:20px;position:relative;
  transition:background .2s;flex:none}
.switch span:after{content:"";position:absolute;width:22px;height:22px;background:#fff;border-radius:50%;
  top:2px;left:2px;box-shadow:0 1px 3px #0005;transition:left .2s}
.switch input:checked+span{background:#34c759}
.switch input:checked+span:after{left:20px}
.storagebar{height:10px;background:var(--bar);border-radius:20px;margin:18px;overflow:hidden}
.storagebar span{display:block;height:100%;background:var(--ink)}
.danger-btn{margin:12px 18px 18px;width:calc(100% - 36px);border:0;border-radius:12px;padding:12px;
  color:var(--err);background:var(--err-bg);font-weight:600;cursor:pointer}
.note{font-size:12px;color:var(--muted);line-height:1.6;margin-top:16px}
.tabbar{position:fixed;bottom:calc(12px + env(safe-area-inset-bottom));left:50%;transform:translateX(-50%);
  z-index:10;width:min(700px,calc(100% - 28px));display:grid;grid-template-columns:repeat(4,1fr);
  background:color-mix(in srgb,var(--card) 92%,transparent);backdrop-filter:blur(20px);
  border:1px solid var(--line);border-radius:22px;padding:7px;box-shadow:0 10px 35px #0003}
.tab{border:0;background:none;padding:8px 3px;color:var(--muted);font-size:11px;cursor:pointer}
.tab span{display:block;font-size:19px;margin-bottom:3px}
.tab.active{color:var(--text);font-weight:700}
.modal-wrap{display:none;position:fixed;inset:0;z-index:20;background:#0007;align-items:end;justify-content:center}
.modal-wrap.show{display:flex}
.modal{background:var(--shell);width:min(620px,100%);border-radius:28px 28px 0 0;padding:24px;
  padding-bottom:calc(24px + env(safe-area-inset-bottom));max-height:88vh;overflow:auto}
.modal-head{display:flex;justify-content:space-between;align-items:start;gap:12px}
.modal-head h2{margin:3px 0}
.modal-head button{border:0;background:var(--bar);color:var(--text);border-radius:50%;width:34px;height:34px;font-size:22px;cursor:pointer}
.check-row{display:flex;align-items:center;gap:13px;background:var(--card);border:1px solid var(--line);
  border-radius:14px;padding:14px;margin:9px 0}
.check-row input{width:20px;height:20px;accent-color:var(--accent);flex:none}
.check-row div{flex:1;min-width:0}
.estimate{display:flex;justify-content:space-between;align-items:center;margin:16px 0;color:var(--muted)}
.full{width:100%}
#offline{background:var(--warn-bg);color:var(--warn);border-radius:14px;padding:11px 16px;
  margin-bottom:14px;font-size:.9rem;font-weight:600}
.steps{margin:10px 0 16px;padding-left:1.2em;color:var(--muted);font-size:.9rem;line-height:1.7}
.steps b{color:var(--text)}
#token{width:100%;padding:13px;border:1px solid var(--line);border-radius:12px;
  background:var(--card);color:var(--text)}
.err{color:var(--err);font-size:.9rem;margin-top:10px;min-height:1.2em}
#log{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px;
  font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;
  word-break:break-word;max-height:34vh;overflow:auto;margin-top:12px}
.status{font-weight:700;margin-top:14px}
.status.running{color:var(--accent)} .status.done{color:var(--ok)} .status.error{color:var(--err)}
.file-row input[type=checkbox]{width:20px;height:20px;accent-color:var(--accent);flex:none}
.iconbtn{border:0;background:var(--bar);color:var(--text);border-radius:11px;width:34px;height:34px;
  font-size:15px;cursor:pointer;flex:none}
.course-card .iconbtn{position:absolute;top:14px;right:14px}
.course-card{position:relative}
.actionbar{position:fixed;left:50%;transform:translateX(-50%);
  bottom:calc(84px + env(safe-area-inset-bottom));z-index:11;width:min(700px,calc(100% - 28px));
  background:var(--ink);color:var(--on-ink);border-radius:18px;padding:12px 16px;
  display:flex;align-items:center;gap:12px;box-shadow:0 10px 35px #0004}
.actionbar b{flex:1;font-size:.95rem}
.actionbar button{border:0;border-radius:11px;padding:10px 14px;font-weight:700;cursor:pointer;
  background:var(--on-ink);color:var(--ink)}
.actionbar .ghost{background:transparent;color:var(--on-ink);text-decoration:underline;padding:10px 4px}
.detail-head{margin:10px 0 18px}
.detail-head h2{margin:4px 0}
</style>
</head>
<body>
<div class="app-shell">
  <header class="topbar">
    <div>
      <div class="eyebrow">NTU COURSE HUB</div>
      <h1 id="pageTitle">首頁</h1>
    </div>
    <button class="avatar" id="avatar" aria-label="帳號" onclick="go('settings')">·</button>
  </header>

  <div id="offline" class="hide">離線中——顯示上次同步的資料</div>

  <main>
    <section class="page active" data-page="login" id="loginCard">
      <div class="hero">
        <p class="muted" style="color:inherit;opacity:.7">開始之前</p>
        <h2>先連結 NTU COOL</h2>
        <p>用存取權杖連結，不是你的學校帳號密碼。</p>
      </div>
      <div class="card" style="padding:18px">
        <ol class="steps">
          <li>在 NTU COOL 開啟 <a class="link" id="tokenLink" href="#" target="_blank" rel="noopener">帳戶 → 設定</a></li>
          <li>捲到「核准的整合」→ 按 <b>+ 新增存取權杖</b>，用途填 <b>ntucool</b></li>
          <li>把產生的權杖貼到下面（<b>只會顯示一次</b>）</li>
        </ol>
        <input type="password" id="token" placeholder="貼上存取權杖" autocomplete="off" spellcheck="false">
        <div class="err" id="loginErr"></div>
        <button class="compact full" id="login" style="padding:14px">連結並開始下載</button>
      </div>
      <p class="note">權杖只存在這台裝置（<code>~/.config/ntucool/.env</code>，權限 600），
        不會傳給任何人。隨時可以在 NTU COOL 的設定頁把它撤銷。</p>
    </section>

    <section class="page" data-page="home">
      <div class="hero">
        <p class="muted" style="color:inherit;opacity:.7" id="heroTerm">　</p>
        <h2 id="heroGreeting">你好</h2>
        <p id="heroSummary">還沒有資料，先同步一次。</p>
        <button class="primary" onclick="openBulkModal()">下載本學期文件</button>
      </div>

      <div class="section-head"><h3>近期作業</h3><button class="link" onclick="go('courses')">查看課程</button></div>
      <div id="upcoming"></div>

      <div class="section-head hide" id="eventsHead"><h3>近期行事曆</h3></div>
      <div id="events"></div>

      <div class="section-head"><h3>文件同步</h3><span class="muted" id="syncText">尚未同步</span></div>
      <div class="card">
        <div class="storage">
          <div><b>本機課程文件</b><small id="storageLine">0 個檔案</small></div>
          <button class="secondary" id="go" onclick="startSync()">同步新文件</button>
        </div>
      </div>
    </section>

    <section class="page" data-page="courses">
      <div class="section-head"><h2>我的課程</h2>
        <select id="termSelect" onchange="onTermChange()" aria-label="學期"></select></div>
      <p class="muted" id="courseCount" style="margin:8px 0 0"></p>
      <div class="course-grid" id="courseGrid"></div>
    </section>

    <section class="page" data-page="downloads">
      <div class="section-head"><h2>同步工作</h2><button class="compact" onclick="openBulkModal()">＋ 新增下載</button></div>
      <div class="card"><div class="storage">
        <div><b>打包全部課程</b><small>把已經抓下來的檔案壓成一個 zip 存到這台裝置</small></div>
        <button class="secondary" id="zipAll" onclick="downloadAll()">⤓ 下載</button>
      </div></div>
      <div class="download-summary">
        <div><strong id="dlRunning">0</strong><small>進行中</small></div>
        <div><strong id="dlFiles">0</strong><small>已完成檔案</small></div>
        <div><strong id="dlSize">0 B</strong><small>已使用</small></div>
      </div>
      <div class="status hide" id="statusLine"></div>
      <div id="downloadList"></div>
      <details id="logBox" class="card hide" style="padding:14px 18px">
        <summary style="cursor:pointer;font-weight:600">同步記錄</summary>
        <div id="log"></div>
      </details>
    </section>

    <section class="page" data-page="settings">
      <div class="card" style="margin-top:20px">
        <div class="row"><div><b>NTU COOL</b><small id="settingsAccount">未連結</small></div><span class="ok" id="settingsState">未連結</span></div>
        <div class="row"><div><b>只下載 PDF／簡報</b><small>略過影片與壓縮檔</small></div>
          <label class="switch"><input type="checkbox" id="pdfOnly"><span></span></label></div>
        <div class="row"><div><b>略過大檔</b><small>超過 50MB 不下載</small></div>
          <label class="switch"><input type="checkbox" id="skipBig"><span></span></label></div>
      </div>
      <div class="section-head"><h3>儲存空間</h3></div>
      <div class="card">
        <div class="storagebar"><span id="storageBar" style="width:0"></span></div>
        <div class="row"><span>課程文件</span><b id="storageSize">0 B</b></div>
        <div class="row"><div><b>存放位置</b><small id="outDir">—</small></div></div>
        <button class="danger-btn" id="logout">登出（清除這台裝置上的權杖）</button>
      </div>
      <p class="note">檔案存在上面那個資料夾裡，登出不會刪除已經下載的檔案。</p>
    </section>

    <section class="page" data-page="detail">
      <button class="back" onclick="go('courses')">‹ 所有課程</button>
      <div id="courseDetail"></div>
    </section>
  </main>

  <div class="actionbar hide" id="actionbar">
    <b id="pickedLabel">已選 0 個</b>
    <button class="ghost" onclick="clearPicks()">取消</button>
    <button id="pickedGo" onclick="downloadPicked()">⤓ 下載</button>
  </div>

  <nav class="tabbar hide" id="tabbar">
    <button class="tab active" data-target="home" onclick="go('home')"><span>⌂</span>首頁</button>
    <button class="tab" data-target="courses" onclick="go('courses')"><span>▤</span>課程</button>
    <button class="tab" data-target="downloads" onclick="go('downloads')"><span>↓</span>下載</button>
    <button class="tab" data-target="settings" onclick="go('settings')"><span>⚙</span>設定</button>
  </nav>
</div>

<div class="modal-wrap" id="bulkModal">
  <div class="modal">
    <div class="modal-head">
      <div><small>批次下載</small><h2>選擇要同步的課程</h2></div>
      <button onclick="closeBulkModal()" aria-label="關閉">×</button>
    </div>
    <p class="muted">留空代表全部。同步只會抓新增或更新過的檔案。</p>
    <div id="bulkCourses"></div>
    <div class="estimate"><span>已選</span><b><span id="selectedCount">全部</span></b></div>
    <button class="compact full" style="padding:15px" onclick="startSync()">開始同步</button>
  </div>
</div>

<script>
const KEY = new URLSearchParams(location.search).get('k') || '__KEY__';
const api = (path, opts) => fetch(path + (path.includes('?') ? '&' : '?') + 'k=' + encodeURIComponent(KEY), opts);
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const titles = {home:'首頁', courses:'課程', downloads:'下載', settings:'設定', detail:'課程', login:'連結帳號'};
let state = {authenticated:false, courses:[], term:''};
try{ state.term = localStorage.getItem('ntucool.term') || ''; }catch(e){}
const withTerm = path => state.term ? path + (path.includes('?') ? '&' : '?') + 'term=' + encodeURIComponent(state.term) : path;

function go(name){
  if(name !== 'detail' && document.getElementById('actionbar')) $('actionbar').classList.add('hide');
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.dataset.page === name));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.target === name));
  $('pageTitle').textContent = titles[name] || '';
  window.scrollTo({top:0, behavior:'smooth'});
}

function initials(name){
  const clean = String(name || '').trim();
  if(!clean) return '·';
  return /[A-Za-z]/.test(clean[0]) ? clean.split(/\s+/).map(w => w[0]).join('').slice(0,2).toUpperCase()
                                   : clean.slice(-2);
}

async function loadStatus(){
  let s;
  try{ s = await (await api('/api/status')).json(); }
  catch(e){ return null; }
  state.authenticated = s.authenticated;
  $('tokenLink').href = String(s.base_url || '').replace(/\/$/, '') + '/profile/settings';
  $('loginCard').classList.toggle('hide', s.authenticated);
  $('tabbar').classList.toggle('hide', !s.authenticated);
  if(!s.authenticated){ go('login'); return s; }
  if(document.querySelector('.page[data-page="login"]').classList.contains('active')) go('home');

  $('avatar').textContent = initials(s.user);
  $('heroTerm').textContent = s.term || '';
  $('heroGreeting').textContent = s.user ? `你好，${s.user}` : '你好';
  $('syncText').textContent = s.last_sync ? `上次同步：${s.last_sync}` : '尚未同步';
  $('storageLine').textContent = `${s.files} 個檔案 · ${s.size}`;
  $('storageSize').textContent = s.size;
  $('dlFiles').textContent = s.files;
  $('dlSize').textContent = s.size;
  $('outDir').textContent = s.out_dir;
  $('settingsAccount').textContent = s.user ? `已連結 · ${s.user}` : '已連結';
  $('settingsState').textContent = '已連結';
  const pct = Math.min(100, Math.round((s.bytes || 0) / (2 * 1024 * 1024 * 1024) * 100));
  $('storageBar').style.width = pct + '%';
  return s;
}

async function loadDashboard(){
  try{
    const d = await (await api(withTerm('/api/dashboard'))).json();
    renderEvents(d.events || []);
    const soon = d.upcoming.filter(i => !i.submitted).length;
    $('heroSummary').textContent = soon ? `有 ${soon} 份作業還沒交。` : '目前沒有待繳的作業。';
    $('upcoming').innerHTML = d.upcoming.length
      ? `<div class="card">${d.upcoming.map(i => {
          const cls = i.overdue ? 'late' : (i.submitted ? '' : (i.days < 3 ? 'warn' : 'plain'));
          const text = i.overdue ? '逾期未交' : (i.submitted ? '已繳交' :
                       (i.days < 1 ? '今天到期' : `還有 ${Math.ceil(i.days)} 天`));
          const title = i.url ? `<a class="link" href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.name)}</a>` : esc(i.name);
          return `<div class="row"><div><b>${title}</b><small>${esc(i.course)} · ${esc(i.due_at)}</small></div>
                  <span class="pill ${cls}">${text}</span></div>`;
        }).join('')}</div>`
      : '<div class="card"><div class="empty"><b>沒有近期作業</b><p>最近 30 天內沒有要交的東西。</p></div></div>';
  }catch(e){ /* 離線時沿用畫面上的內容 */ }
}

function groupByDate(items){
  const groups = new Map();
  for(const item of items){
    const day = String(item.start_at || '').slice(0, 10) || '未定';
    if(!groups.has(day)) groups.set(day, []);
    groups.get(day).push(item);
  }
  return [...groups.entries()];
}

function dayLabel(day){
  if(day === '未定') return '未定';
  const date = new Date(day + 'T00:00:00');
  if(isNaN(date)) return day;
  const today = new Date(); today.setHours(0,0,0,0);
  const diff = Math.round((date - today) / 86400000);
  if(diff === 0) return '今天';
  if(diff === 1) return '明天';
  const week = ['日','一','二','三','四','五','六'][date.getDay()];
  return `${date.getMonth() + 1}/${date.getDate()}（${week}）`;
}

function renderEvents(events){
  $('eventsHead').classList.toggle('hide', !events.length);
  if(!events.length){ $('events').innerHTML = ''; return; }
  $('events').innerHTML = groupByDate(events).map(([day, items]) => `
    <div class="section-head" style="margin-top:14px"><small><b>${esc(dayLabel(day))}</b></small></div>
    <div class="card">${items.map(e => {
      const time = String(e.start_at || '').slice(11, 16);
      const title = e.url ? `<a class="link" href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title)}</a>` : esc(e.title);
      return `<div class="row"><span class="time">${esc(time)}</span>
        <div><b>${title}</b><small>${esc(e.course)}${e.location ? ' · ' + esc(e.location) : ''}</small></div></div>`;
    }).join('')}</div>`).join('');
}

async function loadTerms(){
  try{
    const data = await (await api('/api/terms')).json();
    const select = $('termSelect');
    const options = [{term:'', label:'全部學期'}]
      .concat(data.terms.map(t => ({term:t.term, label:`${t.term}（${t.courses} 門）`})));
    select.innerHTML = options.map(o =>
      `<option value="${esc(o.term)}"${o.term === state.term ? ' selected' : ''}>${esc(o.label)}</option>`).join('');
    if(state.term && !data.terms.some(t => t.term === state.term)){
      state.term = '';             // 選過的學期已經不在資料裡
      select.value = '';
    }
  }catch(e){}
}

function onTermChange(){
  state.term = $('termSelect').value;
  try{ localStorage.setItem('ntucool.term', state.term); }catch(e){}
  loadCourses(); loadDashboard();
}

async function loadCourses(){
  try{
    const data = await (await api(withTerm('/api/courses'))).json();
    state.courses = data.courses;
    $('courseCount').textContent = data.courses.length ? `${data.courses.length} 門` : '';
    $('courseGrid').innerHTML = data.courses.length
      ? data.courses.map(c => `<article class="course-card" role="button" tabindex="0"
          onclick="openCourse('${esc(c.dir)}')"
          onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openCourse('${esc(c.dir)}')}">
          <button class="iconbtn" title="下載整門課" aria-label="下載整門課"
            onclick="event.stopPropagation();downloadCourse('${esc(c.dir)}')">⤓</button>
          <div><span class="course-dot"></span><h3>${esc(c.name)}</h3>
            <small>${esc(c.code)}${c.teacher ? ' · ' + esc(c.teacher) : ''}</small></div>
          <div><b>${c.files} 個文件</b><small>${esc(c.size)}${c.score != null ? ' · ' + esc(c.score) + ' 分' : ''}</small></div>
        </article>`).join('')
      : '<div class="card" style="grid-column:1/-1"><div class="empty"><b>還沒有課程</b><p>先回首頁按「同步新文件」。</p></div></div>';
    $('bulkCourses').innerHTML = data.courses.map(c =>
      `<label class="check-row"><input type="checkbox" value="${esc(c.code || c.name)}" onchange="updateEstimate()">
       <div><b>${esc(c.name)}</b><small>${c.files} 個文件 · ${esc(c.size)}</small></div></label>`).join('')
      || '<p class="muted">還沒有課程資料，直接按「開始同步」會抓全部。</p>';
    updateEstimate();
  }catch(e){ /* 離線 */ }
}

function folderLabel(folder){
  const clean = String(folder || '').replace(/^files\/?/, '').replace(/^\.$/, '');
  return clean ? esc(clean) + ' · ' : '';
}

async function openCourse(dir){
  go('detail');
  $('courseDetail').innerHTML = '<p class="muted">載入中…</p>';
  try{
    const c = await (await api('/api/course?dir=' + encodeURIComponent(dir))).json();
    $('pageTitle').textContent = c.code || '課程';
    const files = c.files.filter(f => f.folder.startsWith('files'));
    const docs = c.files.filter(f => !f.folder.startsWith('files'));
    const fileRow = f => `<div class="file-row">
        <input type="checkbox" data-path="${esc(f.path)}" data-bytes="${f.bytes}" onchange="onPick()">
        <span class="icon">${esc(f.ext)}</span>
        <div><a href="/files/${encodeURI(f.path)}?k=${encodeURIComponent(KEY)}" target="_blank" rel="noopener">${esc(f.name)}</a>
        <small>${folderLabel(f.folder)}${esc(f.size)}</small></div></div>`;
    $('courseDetail').innerHTML = `
      <div class="detail-head"><small>${esc(c.code)}${c.term ? ' · ' + esc(c.term) : ''}</small>
        <h2>${esc(c.name)}</h2><p class="muted">${esc(c.teacher)}</p>
        ${c.url ? `<a class="link" href="${esc(c.url)}" target="_blank" rel="noopener">在 NTU COOL 開啟 ›</a>` : ''}
        <button class="compact full" style="padding:14px;margin-top:16px"
          onclick="downloadCourse('${esc(c.dir)}')">⤓ 一鍵下載整門課（${c.files.length} 個檔案）</button></div>
      ${c.assignments.length ? `<div class="section-head"><h3>作業</h3></div><div class="card">${
        c.assignments.map(a => `<div class="row"><div><b>${esc(a.name)}</b>
          <small>${a.due_at ? '截止 ' + esc(a.due_at.slice(0,10)) : '未設截止日'}</small></div>
          <span class="pill ${a.submitted ? '' : 'plain'}">${a.submitted ? '已繳交' : '未繳交'}</span></div>`).join('')}</div>` : ''}
      <div class="section-head"><h3>課程文件</h3>
        ${files.length ? `<button class="link" onclick="toggleAll()">全選／取消</button>` : `<span class="muted">0 個</span>`}</div>
      <div class="card">${files.length ? files.map(fileRow).join('')
        : '<div class="empty"><b>沒有檔案</b><p>這門課可能關閉了檔案分頁。</p></div>'}</div>
      ${docs.length ? `<div class="section-head"><h3>整理好的資料</h3></div><div class="card">${docs.map(fileRow).join('')}</div>` : ''}`;
    onPick();
  }catch(e){ $('courseDetail').innerHTML = '<p class="muted">讀取失敗：' + esc(e) + '</p>'; }
}

// ---- 打包下載 ----
function humanSize(bytes){
  const units = ['B','KB','MB','GB'];
  let value = bytes, unit = 0;
  while(value >= 1024 && unit < units.length - 1){ value /= 1024; unit++; }
  return (unit === 0 ? value : value.toFixed(1)) + ' ' + units[unit];
}
function pickedBoxes(){ return [...document.querySelectorAll('#courseDetail input[type=checkbox]:checked')]; }
function onPick(){
  const picked = pickedBoxes();
  const bar = $('actionbar');
  if(!picked.length){ bar.classList.add('hide'); return; }
  const bytes = picked.reduce((sum, box) => sum + Number(box.dataset.bytes || 0), 0);
  bar.classList.remove('hide');
  $('pickedLabel').textContent = `已選 ${picked.length} 個 · ${humanSize(bytes)}`;
}
function toggleAll(){
  const boxes = [...document.querySelectorAll('#courseDetail input[type=checkbox]')];
  const turnOn = boxes.some(b => !b.checked);
  boxes.forEach(b => { b.checked = turnOn; });
  onPick();
}
function clearPicks(){
  document.querySelectorAll('#courseDetail input[type=checkbox]').forEach(b => { b.checked = false; });
  onPick();
}
function startZip(query){ location.href = '/api/zip?' + query + '&k=' + encodeURIComponent(KEY); }
function downloadCourse(dir){ startZip('dir=' + encodeURIComponent(dir)); }
function downloadAll(){ startZip('all=1'); }
async function downloadPicked(){
  const picked = pickedBoxes();
  if(!picked.length) return;
  const button = $('pickedGo');
  button.disabled = true;
  try{
    const res = await api('/api/zip-ticket', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({paths: picked.map(b => b.dataset.path), name: $('pageTitle').textContent + '-選取檔案'})});
    if(!res.ok){ alert('無法建立下載：' + await res.text()); return; }
    const data = await res.json();
    startZip('ticket=' + encodeURIComponent(data.ticket));
  }finally{ button.disabled = false; }
}

function openBulkModal(){ $('bulkModal').classList.add('show'); updateEstimate(); }
function closeBulkModal(){ $('bulkModal').classList.remove('show'); }
function selectedCourses(){
  return [...document.querySelectorAll('#bulkCourses input:checked')].map(i => i.value);
}
function updateEstimate(){
  const picked = selectedCourses();
  $('selectedCount').textContent = picked.length ? `${picked.length} 門課程` : '全部課程';
}

let polling = null, logFrom = 0;
async function startSync(){
  closeBulkModal();
  $('go').disabled = true;
  $('logBox').classList.remove('hide');
  $('statusLine').classList.remove('hide');
  $('log').textContent = '';
  logFrom = 0;
  const body = JSON.stringify({
    pdf_only: $('pdfOnly').checked,
    skip_big: $('skipBig').checked,
    courses: selectedCourses().join(','),
    term: state.term,
  });
  try{
    const res = await api('/api/sync', {method:'POST', headers:{'Content-Type':'application/json'}, body});
    if(!res.ok){
      $('statusLine').className = 'status error';
      $('statusLine').textContent = '無法開始：' + await res.text();
      $('go').disabled = false;
      return;
    }
  }catch(e){
    $('statusLine').className = 'status error';
    $('statusLine').textContent = '連不上本機伺服器（可能沒開著）';
    $('go').disabled = false;
    return;
  }
  clearTimeout(polling);
  go('downloads');
  poll();
}

async function poll(){
  let res;
  try{ res = await (await api('/api/progress?from=' + logFrom)).json(); }
  catch(e){ $('go').disabled = false; return; }
  if(res.lines.length){
    logFrom += res.lines.length;
    $('log').textContent += res.lines.join('\n') + '\n';
    $('log').scrollTop = $('log').scrollHeight;
  }
  renderDownloads(res.courses || [], res.status);
  const line = $('statusLine');
  line.className = 'status ' + res.status;
  line.textContent = {running:'同步中…', done:'同步完成', error:'發生錯誤', idle:''}[res.status] || '';
  if(res.status === 'running'){
    polling = setTimeout(poll, 700);
  }else{
    $('go').disabled = false;
    loadStatus(); loadTerms(); loadCourses(); loadDashboard();
  }
}

function renderDownloads(courses, status){
  $('dlRunning').textContent = courses.filter(c => c.state === 'running').length;
  if(!courses.length){
    $('downloadList').innerHTML = '<div class="card"><div class="empty"><div class="file-icon">↓</div>'
      + '<b>目前沒有下載工作</b><p>從首頁或上面的「＋ 新增下載」開始。</p></div></div>';
    return;
  }
  $('downloadList').innerHTML = courses.map(c => {
    const label = c.state === 'failed' ? '失敗'
      : c.state === 'done' ? (c.done ? `完成 · ${c.done} 個新檔案` : '完成 · 無新檔案')
      : (c.total ? `${c.done}/${c.total}` : '檢查中…');
    return `<div class="download-item">
      <div class="row" style="padding:0;border:0"><div><b>${esc(c.course)}</b>
        <small>${esc(c.error || label)}</small></div><span class="muted">${c.percent}%</span></div>
      <div class="progress"><span class="${c.state === 'failed' ? 'failed' : ''}" style="width:${c.percent}%"></span></div>
    </div>`;
  }).join('');
}

$('login').onclick = async () => {
  const token = $('token').value.trim();
  $('loginErr').textContent = '';
  if(!token){ $('loginErr').textContent = '請先貼上權杖'; return; }
  $('login').disabled = true;
  try{
    const res = await api('/api/login', {method:'POST', headers:{'Content-Type':'application/json'},
                                         body: JSON.stringify({token})});
    const data = await res.json();
    if(!res.ok){ $('loginErr').textContent = data.error || '連結失敗'; return; }
    $('token').value = '';
    await loadStatus();
    go('home');
    startSync();
  }catch(e){ $('loginErr').textContent = String(e); }
  finally{ $('login').disabled = false; }
};
$('token').addEventListener('keydown', e => { if(e.key === 'Enter') $('login').click(); });

$('logout').onclick = async () => {
  await api('/api/logout', {method:'POST'});
  clearTimeout(polling);
  loadStatus();
};

for(const id of ['pdfOnly','skipBig']){
  try{ $(id).checked = localStorage.getItem('ntucool.' + id) === '1'; }catch(e){}
  $(id).onchange = () => { try{ localStorage.setItem('ntucool.' + id, $(id).checked ? '1' : '0'); }catch(e){} };
}

function markOffline(){ $('offline').classList.toggle('hide', navigator.onLine); }
addEventListener('online', markOffline);
addEventListener('offline', markOffline);
markOffline();

if('serviceWorker' in navigator){
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

renderDownloads([], 'idle');
(async () => {
  const s = await loadStatus();
  if(s && s.authenticated){ loadTerms(); loadCourses(); loadDashboard(); }
})();
</script>
</body>
</html>
'''
