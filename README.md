# Atlas

Atlas 是一個早期開發中的 agent harness 專案。

目標是把公司內部既有的網頁版 LLM（tGenie）包裝成可程式化操作的 agent harness，讓原本只能透過網頁操作的 tGenie，未來可以像 Codex CLI、Claude Code、opencode 一樣在本機 workspace 內協助讀檔、寫檔、整理文件與產出 LLM Wiki。

## 你現在需要知道的事

目前 Atlas 還不是完整 agent，但已經有兩個可用入口：

- `atlas`：正式互動入口，目前是最小 Textual TUI 殼。
- `scripts/probe_tgenie.py`：開發用 tGenie probe，負責校準真實網頁上的按鈕與輸入框。

**tGenie probe 是什麼**：
它是一個開發用腳本，會打開系統 Chrome、進入 tGenie，掃描網頁上的按鈕與輸入框，讓你用編號告訴 Atlas「哪個是 sidebar、哪個是 new conversation、哪個是輸入框、哪個是送出按鈕」。

**為什麼要先做 probe**：
tGenie 網頁的 CSS class 可能有 hash，不能直接猜 selector。先做 probe，後面正式 tGenie adapter 才知道要點哪個按鈕。

**這樣的影響與取捨**：
probe 需要你人在公司電腦前操作一次，比較慢；但它能把真實網頁結構記錄成 JSON、Markdown、screenshot，讓後續實作比較穩，不會只靠猜。

## 專案狀態

- 已有 Python 專案骨架。
- 已有開發用 `scripts/probe_tgenie.py`。
- 已有正式 `atlas` 指令與最小 Textual TUI。
- 尚未完成 tGenie adapter、tool loop、LLM Wiki。
- GitHub PRD: https://github.com/LesterCtw/Atlas/issues/1

## 名詞速查

- **Atlas**：這個專案，負責把 tGenie 包成 agent harness。
- **tGenie**：公司內部的網頁版 LLM。
- **probe**：用來確認 tGenie 網頁按鈕與輸入框的開發腳本。
- **selector**：Playwright 用來找到網頁元素的方法，例如按鈕文字、placeholder、ARIA label。
- **workspace**：Atlas 允許讀寫的資料夾。未來 Atlas 只會操作這個資料夾內的檔案。
- **Chrome profile**：Chrome 的登入狀態資料夾。tGenie 登入一次後，下次可重用。
- **HITL**：Human in the loop，需要人到公司電腦前實際操作或確認的步驟。

## 安裝

### 本機開發

本機開發可以使用 `uv`：

```bash
uv sync
uv run atlas --help
uv run python scripts/probe_tgenie.py --help
```

啟動最小 Atlas TUI：

```bash
uv run atlas
```

預設 workspace 是目前資料夾。也可以明確指定 workspace：

```bash
uv run atlas <workspace-path>
```

進入 TUI 後，目前支援：

- `/help`：列出可用命令。
- `/exit`：乾淨結束程式。
- 其他 slash command：顯示清楚錯誤訊息。

執行 probe：

```bash
uv run python scripts/probe_tgenie.py --url "https://your-company-tgenie-url"
```

### 部署或公司電腦

公司電腦不假設有 `uv`，使用標準 Python venv 與 pip。

在 Windows PowerShell 中：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

確認安裝成功：

```powershell
.\.venv\Scripts\atlas --help
.\.venv\Scripts\python scripts\probe_tgenie.py --help
```

成功時會看到 `Probe tGenie UI elements with system Chrome.` 和一串參數說明。

#### 從任何 PowerShell 直接執行 `atlas`

專案決定：公司電腦採用 **User PATH** 方式，讓使用者可以在任意 PowerShell 位置直接輸入 `atlas` 開啟 TUI。這不需要管理員權限，因為只修改目前使用者的 PATH。

在 Atlas 專案資料夾安裝完成後，執行一次：

```powershell
$atlasScripts = "$PWD\.venv\Scripts"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
[Environment]::SetEnvironmentVariable("Path", "$atlasScripts;$userPath", "User")
```

接著關掉 PowerShell，重新開一個新的 PowerShell。之後可以在任何資料夾執行：

```powershell
atlas
```

或指定 workspace：

```powershell
atlas <workspace-path>
```

這個方式的取捨是：日常使用最方便，但 Atlas 專案資料夾和 `.venv` 不能移走。若移動資料夾，需要重新設定 User PATH。

啟動最小 Atlas TUI：

```powershell
.\.venv\Scripts\atlas
```

指定 workspace：

```powershell
.\.venv\Scripts\atlas <workspace-path>
```

如果沒有指定 path，預設 workspace 是目前資料夾。TUI 會在畫面上顯示目前 workspace。

Atlas 使用系統已安裝的 Chrome，不使用 `playwright install` 下載的瀏覽器。

## 測試

本機開發：

```bash
uv run python -m unittest discover -s tests
uv run python -m compileall atlas scripts tests
```

部署或公司電腦可以先確認 Python 檔案語法：

```powershell
.\.venv\Scripts\python -m compileall atlas scripts
```

成功時會看到類似 `Compiling` 或沒有錯誤訊息。

## tGenie Probe 操作手冊

### 1. 啟動 probe

本機開發：

```bash
uv run python scripts/probe_tgenie.py --url "https://your-company-tgenie-url"
```

部署或公司電腦：

```powershell
.\.venv\Scripts\python scripts\probe_tgenie.py --url "https://your-company-tgenie-url"
```

如果不想把 URL 放在指令中，也可以直接執行後依提示輸入：

```powershell
.\.venv\Scripts\python scripts\probe_tgenie.py
```

### 2. 登入 tGenie

腳本會開啟 Chrome。

你要做：

1. 在 Chrome 裡完成 tGenie 登入。
2. 確認畫面停在 tGenie 主對話頁。
3. 回到 PowerShell。
4. 按 Enter 繼續。

成功時 PowerShell 會列出很多像這樣的元素：

```text
[00] button role=- type=- box=... label=...
[01] textarea role=- type=- box=... label=...
```

### 3. 校準按鈕與輸入框

probe 會進入這個提示：

```text
probe>
```

常用指令：

```text
targets
list
set sidebar_toggle <元素編號>
click <元素編號>
set new_conversation <元素編號>
type <元素編號> 測試訊息
set prompt_input <元素編號>
set send_button <元素編號>
set attach_button <元素編號>
set model_selector <元素編號>
set web_search_toggle <元素編號>
shot
done
```

建議照這個順序做：

1. 輸入 `targets`，看有哪些項目還沒設定。
2. 找出 sidebar 展開按鈕的編號。
3. 輸入 `set sidebar_toggle <編號>`。
4. 輸入 `click <編號>`，真的點開 sidebar。
5. 輸入 `list`，重新掃描目前畫面。
6. 找出 new conversation 按鈕的編號。
7. 輸入 `set new_conversation <編號>`。
8. 輸入 `click <編號>`，真的建立新對話。
9. 輸入 `list`。
10. 找出 prompt input 對話輸入框的編號。
11. 輸入 `set prompt_input <編號>`。
12. 輸入 `type <編號> 測試訊息`，確認文字真的進入輸入框。
13. 找出 send button 的編號。
14. 輸入 `set send_button <編號>`。
15. 找出 attach 按鈕的編號。
16. 輸入 `set attach_button <編號>`。
17. 找出 model selector 的編號。
18. 輸入 `set model_selector <編號>`。
19. 找出 web search 開關的編號。
20. 輸入 `set web_search_toggle <編號>`。
21. 輸入 `shot`，留一張人工截圖。
22. 輸入 `done`，結束並輸出報告。

### 4. 輸出檔案

成功完成後，`probe-output/` 會出現：

- `tgenie_probe_*.json`：完整元素資料與校準結果。
- `tgenie_probe_*.md`：人比較好讀的報告。
- `tgenie_probe_*.png`：當下頁面的 screenshot。

這三個檔案很重要。後續要寫正式 tGenie adapter 時，主要會看這些檔案。

## 明天在公司要驗證什麼

這一段是 HITL 驗證清單。照著做，不需要先懂整個專案架構。

### HITL 1：Python 專案與 probe 能不能在公司電腦跑

對應 issue: #2

要驗證：

- Windows 11 上能建立 `.venv`。
- 能用 pip 安裝專案。
- 能跑 `probe_tgenie.py --help`。
- 能打開系統 Chrome，而不是 Playwright 下載的瀏覽器。

指令：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python scripts\probe_tgenie.py --help
```

成功標準：

- 沒有 Python traceback。
- `--help` 會顯示 probe 參數。

失敗時要記錄：

- PowerShell 完整錯誤訊息。
- `py --version` 的輸出。
- `.\.venv\Scripts\python --version` 的輸出。

### HITL 2：Chrome profile 與手動登入能不能重用

對應 issue: #4

要驗證：

- 第一次開 Chrome 可以手動登入 tGenie。
- 關掉 probe 後再跑一次，tGenie 仍然保持登入。

指令：

```powershell
.\.venv\Scripts\python scripts\probe_tgenie.py --url "https://your-company-tgenie-url"
```

成功標準：

- 第一次可以登入。
- 第二次不用重新登入，或至少登入流程明顯比第一次少。
- Chrome 是可視視窗，不是背景 headless。

失敗時要記錄：

- Chrome 是否有打開。
- 是否跳到登入頁。
- 是否公司 SSO 擋住。
- `probe-output/` 內有沒有 screenshot。

### HITL 3：tGenie 基本對話流程能不能被手動 probe 出來

對應 issue: #5

要驗證：

- sidebar 按鈕找得到。
- new conversation 按鈕找得到。
- prompt input 找得到。
- send button 找得到。
- 輸入測試訊息後，畫面真的有文字。
- send button 在送出後是否會變成 stop generating。
- 回覆完成後是否會變回 send。

成功標準：

- `tgenie_probe_*.md` 裡面有 `sidebar_toggle`、`new_conversation`、`prompt_input`、`send_button`。
- screenshot 看得出來停在 tGenie 對話頁。

失敗時要記錄：

- 哪個 target 找不到。
- `list` 輸出的相關元素編號。
- screenshot。
- 你手動看到的按鈕文字。

### HITL 4：真實 tGenie tool loop 能不能跑

對應 issue: #8

目前這個功能尚未完成。等 #8 實作後再驗證。

要驗證：

- tGenie 能輸出 Atlas 指定格式的 tool call。
- Atlas 能執行工具。
- Atlas 能把 tool result 貼回同一個 tGenie 對話。
- tGenie 能根據 tool result 繼續回答。

成功標準：

- 可以完成一個簡單任務，例如「搜尋 workspace 裡哪個檔案提到某個關鍵字」。
- TUI 或 log 可以看到 tool call 與 tool result。

失敗時要記錄：

- tGenie 原始回覆。
- Atlas 解析到的 tool call。
- Atlas 的錯誤訊息。
- 當時 workspace 內測試檔案名稱。

### HITL 5：PDF attach 能不能透過 tGenie UI 上傳

對應 issue: #9

目前正式 attach tool 尚未完成，但 probe 階段可以先驗證 attach 按鈕。

要驗證：

- attach 按鈕找得到。
- 點擊後會打開檔案選擇流程，或網頁有上傳入口。
- tGenie 支援上傳 `.pdf`。

成功標準：

- `tgenie_probe_*.md` 裡面有 `attach_button`。
- screenshot 看得到 attach 按鈕或上傳入口。

失敗時要記錄：

- attach 按鈕看起來叫什麼名字。
- 點擊後畫面發生什麼事。
- PDF 是否被公司政策或 tGenie 限制。

### HITL 6：單 PDF 到 LLM Wiki 的端到端 ingestion

對應 issue: #12

目前這個功能尚未完成。等 #12 實作後再驗證。

要驗證：

- `/llm-wiki ingest <pdf>` 能上傳 PDF。
- tGenie 能整理 PDF。
- Atlas 能更新 wiki Markdown。
- Atlas 能輸出 HTML。
- Atlas 能輸出 PyVis graph。

成功標準：

- 有 `wiki/index.md`。
- 有 `wiki/log.md`。
- 有至少一個 wiki knowledge page。
- 有可用瀏覽器打開的 HTML。
- 有 graph HTML。

失敗時要記錄：

- PDF 檔名與大小。
- tGenie 是否成功讀到 PDF。
- 最後成功產生到哪個檔案。
- 錯誤訊息與 screenshot。

## 問公司 AI 時請貼這段

如果你明天遇到錯誤，可以把下面這段貼給公司 AI，然後補上錯誤訊息。

```text
我在 Windows 11 + Python 3.12.8 上測試 Atlas。
Atlas 是一個用 Playwright 控制系統 Chrome 操作公司 tGenie 網站的 Python 專案。
現在不是要用 playwright install 的瀏覽器，而是要用系統 Chrome。
我正在跑 scripts/probe_tgenie.py，目標是打開 tGenie、手動登入、掃描頁面按鈕與輸入框，輸出 probe-output 裡的 json/md/png。

我執行的指令是：
<貼上指令>

我看到的錯誤是：
<貼上完整錯誤>

請幫我判斷這是 Python/venv/pip/Playwright/Chrome/tGenie 登入/公司權限/網頁 selector 哪一類問題，並給我下一步排除方式。
```

## 常見問題

### 看到 `ModuleNotFoundError: No module named 'playwright'`

代表還沒安裝專案依賴。

請跑：

```powershell
.\.venv\Scripts\python -m pip install -e .
```

### Chrome 沒有打開

可能原因：

- 公司電腦沒有安裝 Google Chrome。
- Playwright 找不到 Chrome channel。
- 公司安全政策阻擋自動開啟瀏覽器。

請記錄完整錯誤訊息，丟給公司 AI。

### tGenie 打開但沒有列出元素

可能原因：

- 還停在登入頁。
- tGenie 主畫面還沒載入完成。
- 畫面被彈窗遮住。

請先在 Chrome 裡完成登入，關掉彈窗，停在主對話頁，再回 PowerShell 按 Enter。

### `list` 出現很多元素，不知道選哪個

先用肉眼看 Chrome 畫面，找目標按鈕的大概位置。`list` 會顯示 `box=x,y,widthxheight`，`y` 越小越靠上，`x` 越小越靠左。

不確定時可以：

1. 先輸入 `shot` 截圖。
2. 用 `click <編號>` 試點。
3. 如果點錯，手動在 Chrome 回復畫面。
4. 再輸入 `list` 重新掃描。

### 點錯元素怎麼辦

不用緊張。probe 只是校準工具。

可以：

1. 在 Chrome 手動回到 tGenie 主畫面。
2. 回 PowerShell 輸入 `list`。
3. 重新選正確的元素。
4. 最後 `done` 前確認 `targets` 裡重要項目都有 done。

## 後續方向

完成最小 TUI 與 probe 後，下一步才是正式實作：

1. tGenie adapter。
2. tool-call protocol。
3. workspace file tools 與受控 shell。
4. PDF attach。
5. slash skill loader。
6. LLM Wiki Markdown、HTML、PyVis graph。

這些工作已拆成 GitHub issues #2 到 #12。
