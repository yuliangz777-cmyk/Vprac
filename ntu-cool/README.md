# ntucool — NTU COOL 課程檔案與資訊自動擷取

把你在 **NTU COOL** 修的每一門課，自動整理成一個本機資料夾：投影片、講義、附件全部抓下來，
課程資訊、公告、作業截止日、單元大綱整理成 Markdown 與 JSON。第二次之後只抓「新的／改過的」，
可以掛 cron 或 GitHub Actions 每天自動跑。

> **為什麼不爬網頁？** NTU COOL 是 **Canvas LMS**，有官方 REST API（`/api/v1`）。
> 走 API 代表：不用模擬登入、不會被改版弄壞、拿得到網頁上看不到的欄位（例如作業成績與繳交狀態），
> 也對伺服器比較友善。本工具**只用標準函式庫**，不需要 `pip install` 任何東西。

---

## 一、先拿到存取權杖（只需做一次）

1. 登入 <https://cool.ntu.edu.tw>
2. 左側 **帳戶（Account）→ 設定（Settings）**
3. 捲到 **核准的整合（Approved Integrations）→ + 新增存取權杖（New Access Token）**
4. 用途填 `ntucool`，到期日可留空，按下產生
5. **權杖只會顯示這一次**，複製起來

把它交給工具（擇一）：

```bash
read -rs NTU_COOL_TOKEN && export NTU_COOL_TOKEN   # 最推薦：不進 shell 歷史紀錄
echo "NTU_COOL_TOKEN=貼上你的權杖" > .env   # 或寫進 .env（已被 .gitignore 忽略）
python3 -m ntucool init                     # 或產生 ntucool.config.json 再填進去
```

> 權杖等同於你的帳號，**不要**提交到 git、不要貼給別人。真的外流時，回同一個設定頁把它刪掉即可。

---

## 二、開始用

不需要安裝，只要 Python 3.10 以上（3.10 / 3.11 / 3.12 / 3.13 都實測過）：

```bash
cd ntu-cool
python3 -m ntucool whoami     # 驗證權杖，顯示你的名字
python3 -m ntucool courses    # 列出這學期的課
python3 -m ntucool sync       # 全部抓下來
```

想要 `ntucool` 這個指令的話：`pip install -e .`（一樣沒有任何相依套件）。

### 常用組合

```bash
# 只抓某幾門課（比對課號／課名／課程 ID，可重複）
python3 -m ntucool sync -c CSIE1212 -c 演算法

# 只抓某個學期，而且只要簡報和 PDF
python3 -m ntucool sync -t 113-2 --ext pdf,pptx,docx

# 只更新課程資訊，不下載檔案（很快）
python3 -m ntucool sync --skip-files

# 先看看會做什麼，不寫任何檔案
python3 -m ntucool sync --dry-run

# 略過 50MB 以上的大檔、同時下 8 個
python3 -m ntucool sync --max-file-mb 50 -j 8

# 包含已結束的課程（預設只抓進行中的）
python3 -m ntucool sync --enrollment-state all

# 常駐：每 6 小時自動同步一次
python3 -m ntucool sync --watch 6h
```

`--only` 可以指定要抓哪些區塊，逗號分隔：
`info,syllabus,files,assignments,announcements,modules,pages`。

---

## 三、輸出長什麼樣子

```
ntu-cool-data/
├── README.md                          # 所有課程總表：檔案數、本次更新、作業／公告數
├── .ntucool-state.json                # 同步紀錄（增量同步靠它）
└── CSIE1212-資料結構與演算法-101/
    ├── course.md                      # 課程總覽：教師、大綱、單元、作業表、公告、檔案清單
    ├── course.json                    # 同樣的內容，但給程式讀
    ├── assignments.md                 # 每份作業的說明、截止日、我的繳交狀態與分數
    ├── announcements.md               # 公告全文
    ├── pages/課程公告.md               # 課程頁面
    └── files/
        ├── 講義/第一週/week1-投影片.pdf
        ├── 講義/補充教材.zip
        └── 附件/公告附件.pdf
```

檔案會**照 NTU COOL 上的資料夾結構**放好。除了「檔案」分頁，工具也會把
**課程單元裡連結的檔案**、**公告的附件**、以及**作業／頁面內文中嵌入的檔案連結**一起抓回來
——老師常常只把講義貼在公告裡，不放進檔案區。

---

## 四、增量同步

每個檔案的 `id`、`updated_at`、大小都會記在 `.ntucool-state.json`。下次執行時：

| 情況 | 行為 |
| --- | --- |
| 檔案沒變 | 跳過（不發下載請求） |
| 老師更新了檔案 | 重新下載，**覆寫原檔**（不會變成 `-2`） |
| 你手動刪掉本機檔案 | 重新下載 |
| `--force` | 全部重抓 |

所以排程每天跑一次幾乎不花流量，也不會對 NTU COOL 造成負擔。
把 `ntu-cool-data/` 整包搬走或改名也沒關係，狀態檔跟著資料夾走。

---

## 五、自動化

### A. GitHub Actions（本 repo 已附好）

`.github/workflows/ntu-cool.yml` 每天自動跑一次，結果放在 Actions 的 artifact。
用法：到 **Settings → Secrets and variables → Actions → New repository secret**，
新增 `NTU_COOL_TOKEN`。沒設定這個 secret 時，排程會直接略過（不會失敗）。
同一個 workflow 也會在你改動 `ntu-cool/**` 時跑測試。

> 課程教材多半受著作權保護，**不要**把 `ntu-cool-data/` commit 進公開 repo。
> 上面的流程只把結果放進有保留期限的 artifact，且 `.gitignore` 已經擋掉這個資料夾。

### B. macOS / Linux 的 cron

```bash
crontab -e
# 每天早上 8 點同步
0 8 * * * cd ~/ntu-cool && NTU_COOL_TOKEN=... /usr/bin/python3 -m ntucool sync -q >> ~/ntucool.log 2>&1
```

### C. 常駐模式

`python3 -m ntucool sync --watch 6h`——適合放在一直開著的電腦上，按 Ctrl+C 結束。

---

## 五之二、在 iPhone 上一鍵同步

整個工具只用 Python 標準函式庫，所以 iPhone 上用 **a-Shell**（App Store 免費、內建 Python 3.11）就能跑，
再用**捷徑**做成主畫面上的一個圖示，點一下就同步完。

### 1. 裝 a-Shell

App Store 搜尋 **a-Shell**（作者 Nicolas Holzschuch）安裝，打開它。

### 2. 下載並安裝

在 a-Shell 裡依序貼上這三行（可以直接整段複製貼上）：

```bash
curl -sL https://codeload.github.com/yuliangz777-cmyk/Vprac/tar.gz/refs/heads/claude/ntu-cool-auto-scraper-9i7paw -o ntucool.tgz
tar xzf ntucool.tgz
python3 Vprac-claude-ntu-cool-auto-scraper-9i7paw/ntu-cool/mobile/ios_setup.py --archive ntucool.tgz
```

它會把程式碼裝到 `~/Documents/ntucool`、問你要貼上的**存取權杖**（輸入時不會顯示）、
立刻打一次 API 確認權杖有效，然後把要貼進捷徑的那一行指令印出來。

> 這段合併進 `main` 之後，把上面兩處的
> `refs/heads/claude/ntu-cool-auto-scraper-9i7paw` 換成 `refs/heads/main`、
> 資料夾名換成 `Vprac-main` 即可。
>
> 權杖存在 `~/Documents/ntucool/.ntucool-token`，權限設為只有你自己讀得到，待在 a-Shell 的沙箱內。
> 之後想換權杖或更新程式碼，重跑一次 `python3 ~/Documents/ntucool/ios_setup.py`
> （不加 `--archive` 就會自己去抓最新版）。

### 3. 先手動跑一次

做捷徑之前，先在 a-Shell 直接執行安裝腳本印給你的那一行，確認一切正常：

```bash
python3 ~/Documents/ntucool/ios_sync.py
```

看到「完成：N 門課程…」就代表成功了，捷徑只是把這一行包起來而已。

### 4. 做成一鍵捷徑

1. 打開**捷徑** App → 右上角 **+** → **新增動作**
2. 搜尋 `a-Shell`，選 **Execute Command**
3. 指令欄位貼上安裝腳本印給你的那一行：
   ```
   python3 ~/Documents/ntucool/ios_sync.py
   ```
4. 命名為「同步 NTU COOL」→ 完成
5. 長按捷徑 → **加入主畫面** → 從此就像一個 App

> 如果捷徑裡找不到 a-Shell 的動作，備案是用「**打開 URL**」動作，網址填
> `ashell://python3%20~/Documents/ntucool/ios_sync.py`。
> 這個備案我沒辦法在這裡實測，沒反應的話請用上面的 Execute Command 方式。

### 5.（選用）每天自動跑

捷徑 App → **自動化** → **新增** → **特定時間** → 選時間 → 執行剛才的捷徑，
並**關掉「執行前先詢問」**。iOS 會在該時間自動叫醒 a-Shell 同步。

### 抓完的檔案在哪裡

「**檔案**」App → **我的 iPhone** → **a-Shell** → **NTUCool** → 每門課一個資料夾。
PDF 直接點開就能看，也可以長按分享到 GoodNotes、Notability 或存到 iCloud。

### iPhone 上的注意事項

- **同步時讓 a-Shell 保持在前景**。iOS 會凍結背景 App，切出去可能讓同步中斷；
  中斷也不會壞掉——下次再點一次，已抓好的檔案會直接跳過，只補沒抓完的。
- 第一次同步會抓全部，建議**連 Wi-Fi**。之後每次都只抓新的／更新過的，通常幾秒就結束。
- 想省流量與空間：捷徑指令後面可以加參數，例如
  `python3 ~/Documents/ntucool/ios_sync.py --ext pdf --max-file-mb 30`
- `--watch` 常駐模式在 iOS 上沒有意義（App 一被凍結就停），請改用上面的「自動化」。
- 預設輸出位置可以用環境變數 `NTU_COOL_OUT` 換掉。

---

## 六、疑難排解

| 訊息 | 原因與處理 |
| --- | --- |
| `權杖驗證失敗`（離開碼 3） | 權杖打錯或已過期／被刪除，重新產生一個 |
| 某門課「沒有可下載的檔案」 | 老師關閉了「檔案」分頁。工具仍會從單元／公告／作業內文把檔案撈出來；真的沒有就是沒開放 |
| 「被鎖定或沒有下載網址」 | 檔案被設定在未來才解鎖，或只允許線上檢視 |
| `被 Canvas 限流` | 短時間請求太多。工具會自動退避重試；可以把 `-j` 調小 |
| 課程沒出現在清單 | 預設只列進行中的課，加 `--enrollment-state all`；學期尚未開放的課 Canvas 本來就讀不到 |
| 中文檔名變成底線 | `/ : ? * " < > \|` 這些字元在檔名裡不合法，會被換成 `_`（中文本身會保留） |

離開碼：`0` 成功、`1` 一般錯誤、`2` 設定問題、`3` 權杖無效、`130` 使用者中斷。

---

## 七、開發

```bash
cd ntu-cool
python3 -m unittest discover -s tests -v
```

測試會在本機起一個**假的 Canvas 站台**（`tests/fake_canvas.py`），真的跑 HTTP：
分頁（`Link` 標頭）、401／403／限流的分類、500 退避重試、下載被截斷後重試、
增量同步、副檔名與大小過濾、`--dry-run` 不落地，全部都有涵蓋。不需要網路，也不需要真的權杖。

```
ntucool/
├── cli.py        指令列介面
├── config.py     設定載入（CLI > 環境變數 > .env > 設定檔）
├── client.py     Canvas API 用戶端：分頁、重試、限流退避、下載
├── scraper.py    擷取流程主體
├── models.py     把 Canvas JSON 收斂成穩定欄位
├── manifest.py   同步狀態（增量同步）
├── naming.py     跨平台安全的檔名／資料夾名
├── htmlutil.py   HTML → 純文字、挖出內嵌檔案連結
└── report.py     產生 Markdown
```

## 使用規範

這個工具用**你自己的權杖**、抓**你自己有權限看的課程**，就像你手動一個一個按下載一樣。
請不要拿去大量抓取、也不要把老師的教材散布出去。
