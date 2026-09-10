# LectureFlow

即時聽講轉錄、自動筆記與逐字稿問答。麥克風持續收音，在語句停頓處切段送出辨識，
文字一段一段接回逐字稿；筆記與問答都只以逐字稿為依據。

API 金鑰只存在本機後端的環境變數，不會出現在網頁、localStorage 或任何前端程式碼裡。

---

## 1. 安裝與啟動

需要 Python 3.10 以上。

**macOS / Linux**

```bash
cd lectureflow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows PowerShell**

```powershell
cd lectureflow
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

設定金鑰（擇一，或兩者都設）：

```bash
cp .env.example .env      # 然後把金鑰填進去
```

啟動：

```bash
python app.py
```

瀏覽器開啟 <http://127.0.0.1:8000>，按「開始聽講」並允許麥克風權限。

雙擊 `start_mac.command`（macOS）或 `start_windows.bat`（Windows）會自動建立虛擬環境、
安裝套件並啟動。

---

## 2. 設定

所有設定都可以放在 `.env` 或環境變數裡；環境變數優先。

| 變數 | 預設 | 說明 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | — | 筆記與問答使用 Claude |
| `OPENAI_API_KEY` | — | 語音辨識，以及未設 Anthropic 金鑰時的筆記與問答 |
| `LECTUREFLOW_TEXT_PROVIDER` | `auto` | `auto` / `anthropic` / `openai` |
| `LECTUREFLOW_ANTHROPIC_MODEL` | `claude-opus-5` | |
| `LECTUREFLOW_ANTHROPIC_EFFORT` | `low` | 課堂筆記屬於簡單任務，低 effort 反應較快 |
| `LECTUREFLOW_OPENAI_TEXT_MODEL` | `gpt-4o-mini` | |
| `LECTUREFLOW_TRANSCRIBE_MODEL` | `gpt-4o-mini-transcribe` | |
| `LECTUREFLOW_TRANSCRIBE_BASE_URL` | `https://api.openai.com/v1` | 指向本機服務即可離線辨識 |
| `LECTUREFLOW_TRANSCRIBE_API_KEY` | 沿用 `OPENAI_API_KEY` | |
| `LECTUREFLOW_LANGUAGE` | `zh` | 留空則自動偵測語言 |
| `LECTUREFLOW_HOST` / `LECTUREFLOW_PORT` | `127.0.0.1` / `8000` | |

### 完全離線 / 零成本

語音辨識端點只要相容 OpenAI 格式即可，把 base URL 指到本機的
whisper.cpp 或 faster-whisper server：

```bash
LECTUREFLOW_TRANSCRIBE_BASE_URL=http://127.0.0.1:8080/v1
```

沒有設定任何金鑰時，介面仍可運作：轉錄改用瀏覽器內建的 Web Speech API，
筆記與問答改用本機規則（關鍵字排序），品質較低但不需要網路或費用。

---

## 3. 運作方式

### 收音與切段

瀏覽器用 AudioWorklet **連續**擷取音訊，重取樣成 16 kHz 單聲道，交給一個能量式
VAD 判斷每 20 ms 是否有人在說話：

- **在停頓處切段**。累積到至少 1.5 秒且出現 0.7 秒靜音才送出，所以每一段通常
  是一句完整的話，接回去的逐字稿讀起來是連貫的句子而不是碎片。
- **沒人說話就不送**。純靜音不會產生請求，既省錢，也避開 Whisper 類模型
  對著靜音幻覺出「謝謝觀看」「字幕由 Amara.org 社群提供」這類固定句子的問題
  （後端與前端都另外再過濾一次）。
- **有人一直講不停**時，最長 14 秒強制切段，並刻意讓前後兩段重疊 0.4 秒，
  避免壓在切點上的字被切掉；重疊造成的重複文字由 `joinTranscript` 去除。
- 噪音門檻取最近 5 秒音量的低百分位數。說話有音節間隙，所以這個估計會落在
  間隙上而不是人聲上——門檻因此能跟著冷氣或風扇聲上升，卻不會被講者自己
  的聲音一路推高到聽不見自己。

音訊擷取全程不中斷：轉錄請求在背景進行時麥克風仍在錄音。

### 上傳與接合

每段音訊編成一個完整的 WAV 檔上傳。上傳佇列最多兩個併發請求，
但依序號重組後才寫回逐字稿，所以文字順序不會亂。單段失敗會自動重試三次
（600 ms / 1.5 s / 3.75 s）；三次都失敗只會丟掉那幾秒，課堂其餘部分照常進行。

### 筆記與問答

逐字稿每增加約 320 字、且距離上次整理超過 30 秒，就重新整理一次筆記
（摘要、名詞、考點、待追問）。問答走 SSE 串流，回答逐字浮現。
兩者的提示詞都明確要求「只能依逐字稿作答，沒有就說沒有」。

---

## 4. 開發

```bash
# 後端測試
.venv/bin/python -m pytest

# 前端純函式測試（在 repo 根目錄）
npm test
```

`static/audio.js` 與 `static/text.js` 刻意不碰 DOM 與 Web Audio 全域物件，
所以重取樣、WAV 編碼、VAD 切段與逐字稿接合都能在 Node 裡直接測。

---

## 5. 注意事項

- 建議使用 Chrome、Edge 或最新版 Safari，並讓分頁保持在前景。
  程式會嘗試取得 Screen Wake Lock 以避免螢幕休眠。
- iPhone / iPad 鎖屏或讓瀏覽器進入背景時，系統仍可能暫停麥克風。
- 課堂內容暫存在瀏覽器 localStorage，重新整理後可復原，按「清空」移除。
- 錄音前請確認你有錄製該課程的許可。
