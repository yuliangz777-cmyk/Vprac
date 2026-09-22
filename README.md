# Ethan Academic Office

單一檔案的學術辦公室規格，給 **ChatGPT** 使用。

## 用法

1. 把 `ACADEMIC_OFFICE.md` 丟進 ChatGPT（上傳或整份貼上）。
2. 輸入 `BOOTSTRAP`。

它會讀取畢業進度表與 NTU COOL，為每一門在修的課建立一個分支，
產出主截止日追蹤表與課程狀態登錄表，最後回一份主管簡報。

之後日常用：`SYNC_ALL`、`DAILY_BRIEF`、`DEADLINES`、`COURSE <課名> UPDATE`、
`PREP_EXAM <課名>`、`PROJECT <課名>`、`PROGRESS_AUDIT`、`WEEKLY_REVIEW`、`DOWNLOAD_SYNC`。

## 為什麼是一個檔案

原本是 33 個檔案、約 8,800 tokens，**每次對話都要重讀一遍**。
合併去重之後約 2,960 tokens，**省下約 66%**，而且模型不必在多檔之間跳來跳去，
`BOOTSTRAP` 可以一次把狀態模型建起來。

規格本身就是「程式碼」：§4 是唯一的狀態結構，§5 是指令表，§6 是工作流，
§2 是不可違反的規則。

## 改了規格之後

```bash
python3 check_spec.py
```

它會檢查 104 個必要元素（指令、狀態欄位、來源階層、門檻、鐵律、種子課程……）
是否都還在，避免精簡時不小心刪掉一條規則。

## 注意

NTU COOL 與 Webmail 需要經過認證的校內存取，上傳這份檔案**不會**產生背景爬蟲。
`SYNC_ALL` 是可靠的同步單位，而且必須據實回報「上一次真的存取到來源」的時間。
