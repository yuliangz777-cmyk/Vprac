# Violin Quest Pro

一個**完整、可離線、可加到 iPhone 主畫面**的小提琴訓練 App。沒有帳號、沒有伺服器、沒有追蹤，所有資料只存在你自己的裝置上。

原型是單一 `index.html + app.js`；這個版本把它做成真正的 App：模組化程式碼、Service Worker 離線快取、真正的 App icon、練習工具（節拍器／持續音／調音器／計時器）、錄音驗收，以及自動化測試。

---

## 一、怎麼裝到 iPhone 主畫面（Safari）

### 方法 A：用 GitHub Pages（推薦，可離線、可自動更新）

1. 這個 repo 已內建部署流程 `.github/workflows/pages.yml`。
2. 到 GitHub 專案頁 → **Settings → Pages → Build and deployment → Source** 選 **GitHub Actions**，存檔。
3. 推送後 Actions 會自動跑測試並部署，網址是：
   `https://<你的帳號>.github.io/<repo 名稱>/`
   （本 repo 即 `https://yuliangz777-cmyk.github.io/Vprac/`）
4. 用 **iPhone Safari** 打開那個網址（必須是 Safari，Chrome/Line 內建瀏覽器不能加主畫面）。
5. 按下方中間的**分享**按鈕 → 往下捲 → **加入主畫面** → **加入**。
6. 從主畫面點開：全螢幕、沒有網址列、離線也能用。

> 第一次打開時請保持連線幾秒，讓 Service Worker 把整個 App 存進裝置。之後就算飛航模式也能開。

### 方法 B：先在電腦本機試用

```bash
git clone <repo>
cd Vprac
npm run serve          # 或 python3 -m http.server 8080
# 瀏覽器打開 http://localhost:8080
```

手機要連同一個 Wi-Fi 時，把 `localhost` 換成電腦的區域網路 IP 即可。
注意：**直接雙擊 `index.html`（file://）不會運作**——ES modules 與 Service Worker 都需要 http(s)。

### 更新 App

部署新版後，開啟 App 會自動偵測並跳出「有新版本可用 → 立即更新」。也可以到「設定 → 檢查更新」手動觸發。

---

## 二、功能

### 今日
- **自適應每日任務**：依能力面板最低分項目、最近沒完成的任務、可練時間自動排 6–8 項菜單；「重新派發」可換一批（已完成的會保留）。
- **每項任務都能計時**：計時器會漂浮在畫面下方，切到節拍器頁面也繼續跑；實際練習時間會取代預估時間計入統計。
- **任務直通工具**：任務上的「節拍器／持續音／調音器／錄音」按鈕會直接開對應工具並開始計時。
- **今日 Boss**：不中斷錄影驗收，含自評分數與檢討筆記。
- **昨天的第一優先**：昨天結束前寫下的修正項目，今天會出現在最上面。
- 14 天練習量長條圖、本週練習天數、XP／等級／連勝。

### 練習工具（全部離線可用）
- **節拍器**：Web Audio 前瞻排程（不會因為畫面卡頓而飄），30–240 BPM、2–8 拍、八分／三連音／十六分細分、重音、Tap Tempo、視覺拍點。
- **速度階梯**：每 N 小節自動 +X BPM 直到目標速度，用來把慢練推上台速。
- **持續音 Drone**：四條空弦快選＋十二半音＋八度，帶泛音的音色好聽得出拍音。
- **調音器**：麥克風即時測音高（自相關法），顯示音名與音分偏差，±5 分內轉綠；A4 可校正 432–446 Hz。
- **計時器**：自由練習碼錶＋倒數計時（時間到會響）。

### 訓練管理
- **能力面板**：八項能力雷達圖、滑桿調整、每週快照與趨勢箭頭。
- **曲目庫**：新增／編輯／刪除，狀態與成熟度追蹤。
- **驗收與回顧**：每日／每週驗收清單（可自訂條文）、今日筆記、週回顧紀錄。
- **國際賽任務線**：LV.1–LV.7，每階的晉級條件會用你的能力分數、曲目成熟度、最佳連勝**自動判定**。
- **比賽中心**：比賽倒數，並反推「主曲目每週要進步幾 %」；比賽紀錄與評審回饋。
- **訓練日曆**：月曆熱區圖，點任一天看當天完成的任務、筆記與 Boss 檢討。
- **錄音庫**：直接在 App 內錄 take，存在裝置的 IndexedDB，可播放、評分、寫問題筆記。
- **成就**：14 個以實際紀錄計算的成就。
- **設定**：個人資料、主題（淺色／深色／跟隨系統）、A4 基準音、驗收條文、**匯出／匯入 JSON 備份**、重置。

---

## 三、資料與隱私

- 訓練資料存在 `localStorage`，錄音存在 `IndexedDB`，**都不會離開你的裝置**，沒有任何後端。
- 麥克風只在你按下「開始調音」或「開始錄音」時啟用，離開頁面就會關閉。
- 換手機、清除 Safari 資料前，請先到**設定 → 匯出備份 JSON**；新裝置用「匯入備份」還原。
- 舊版原型（`violinQuestProV1`）的存檔會在第一次開啟時自動升級，不會遺失。

---

## 四、開發

```
index.html                 App 外殼
manifest.webmanifest       PWA manifest（含 maskable icon 與捷徑）
sw.js                      Service Worker：離線快取與更新提示
assets/css/app.css         設計系統（淺／深色、iOS 安全區）
assets/js/
  main.js                  啟動、導覽、Service Worker、跨日換日
  state.js                 狀態、schema 遷移、統計、XP（由紀錄推導）
  content.js               任務池、能力、任務線、成就（純函式，可測試）
  audio.js                 節拍器／持續音／調音器引擎
  recorder.js  db.js       錄音與 IndexedDB
  session.js               全域練習計時器
  router.js  theme.js  components.js  util.js
  views/                   12 個頁面
tools/make_icons.py        產生所有 icon（純 Python，無相依套件）
tests/app.test.js          單元測試（node --test）
tests/smoke.mjs            真實瀏覽器煙霧測試（Playwright）
```

```bash
npm test          # 24 項單元測試：日期、XP 曲線、任務派發、遷移、連勝、音高偵測、PWA 檔案完整性
npm run smoke     # 用 iPhone 視窗尺寸實際開 App，走過每個頁面與離線啟動
npm run icons     # 重新產生 icon
```

改版本時，`assets/js/version.js` 的 `APP_VERSION` 與 `sw.js` 的 `CACHE_VERSION` 要一起改（測試會擋）。

---

## 五、已知限制

- iOS 的靜音實體開關會讓 Web Audio 沒聲音，節拍器沒聲音時請先確認側邊開關。
- 錄音格式在 iOS 是 `audio/mp4`，其他瀏覽器多為 `webm`；檔案只在本機播放，不需轉檔。
- 網頁版無法傳送系統推播通知，練習提醒請用 iOS「捷徑／提醒事項」自行設定。
