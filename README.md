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
- 已有文字型 tool-call protocol parser 與 fake adapter 測試回路。
- 已有 workspace tool runtime，可在單一 workspace 內執行 file tools 與受控 shell tool。
- 已有最小 skill loader，可用 slash command 載入內建 skills 或 workspace-local skills。
- 已有本機 LLM Wiki 初始化、lint、HTML mirror 與 graph HTML 輸出。
- 已有首次 tGenie 設定流程：儲存 tGenie URL、開啟系統 Chrome、重用 Chrome profile，並等待使用者手動登入。
- 已有真實 tGenie 對話 adapter、真實 tGenie tool loop，以及 workspace PDF attach tool。
- 已有 `/llm-wiki ingest <path>`，可將 workspace 內單一 PDF 或 PDF 資料夾匯入 LLM Wiki，並重新產生 HTML mirror 與 graph HTML。
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

TUI 啟動後會自動聚焦輸入框，可以直接輸入 prompt 或 slash command；送出後也會回到輸入框，不用點選輸入框。如果焦點跑到 transcript，直接開始打字也會回到輸入框。輸入框維持 3 行高度，輸入英文或中文時都會直接顯示在底部欄位，但不會佔太多畫面。輸入 prompt 時按 `Shift+Enter` 可以插入換行，按 `Enter` 才會送出。當輸入框是空白且 slash command 選單沒有開啟時，可以用上下方向鍵瀏覽過去送出的文字；`Up` 會找較舊的內容，`Down` 會找較新的內容，回到最新後會清空輸入框。

輸入框刻意不放 placeholder。macOS 中文 IME 在還沒按 Enter 選字前，composition 文字可能會先畫在 terminal 上；如果輸入框底下同時有 placeholder，就可能看到 `Enter...` 的第一個 `E` 和中文疊在一起。現在 slash command 提示改成輸入 `/` 時才出現的選單，避免中文輸入時疊字。

輸入框游標使用 underline，不使用白色 block cursor。這樣做是為了避免中文輸入時，閃爍白框把正在輸入的文字視覺切開。Atlas 也會把 terminal cursor 對齊文字插入點，避免 macOS 中文 IME 還在 composition 階段時，預組字和前面的文字中間被多隔一格。

Atlas TUI 目前使用單欄深色 TUI，TUI 畫面文案使用英文：上方 header 顯示 Atlas 與目前 workspace，中間是訊息區，底部是輸入框。header 使用上下對稱 padding，避免文字貼齊 terminal 邊緣或看起來偏上偏下。配色參考 [`DESIGN.md`](DESIGN.md)：近黑 canvas、白色主要文字、灰色 muted 文字、charcoal surface，以及單一藍色 `#0099ff` 作為使用者提示與選取狀態。畫面不保留 footer status bar；tool loop 執行時會直接在 transcript 顯示 `Working:` 狀態，例如 `Waiting for model`、`Parsing tool call`、`Executing tool`、`Final response` 或 `Tool call error`。

TUI 採鍵盤優先操作。滑鼠點 transcript 不會讓 transcript 取得 focus，點輸入框也不會改變框線 highlight；這樣可以避免滑鼠操作造成多餘的視覺狀態。輸入 `/` 時會顯示 slash command 選單，可以用上下方向鍵選擇 `/help`、`/exit` 或現有 skills，例如 `/llm-wiki`、`/skill-creator`。

中間訊息區是簡潔 transcript，訊息區保留適度 padding，但不會在每則訊息後強制加空行。畫面用不同色塊分割 header、transcript、slash 選單和輸入框，不使用邊框。Atlas 發言和使用者發言都留在同一個 transcript 色塊裡，不再用訊息背景色塊分開；transcript 會用固定前綴區分不同內容，並用延伸到訊息區可用寬度的水平線分隔不同發言者區塊。同一個來源連續輸出時會留在同一個區塊，例如連續 Atlas 訊息之間不會再插入水平線：

- `› You  prompt`：你送出的 prompt，使用者輸入會用亮色前綴與粗體文字標示，不使用背景色塊。
- `Atlas:`：Atlas 啟動訊息、slash command 回覆，或模型最後回覆。
- `Working:`：tool loop 狀態，例如等待模型、解析 tool call、執行 tool、收到最終回覆。
- `Error:`：tool call 解析或執行時的錯誤訊息。

**為什麼這樣做**：用文字前綴即可讓 prompt、回覆、狀態和錯誤容易掃描，不需要把 TUI 做成聊天卡片或完整 event inspector。

**影響與取捨**：transcript 會比純文字 log 更清楚，也比較容易測試；使用者輸入會更醒目，不同發言者區塊也會被水平線清楚隔開。取捨是連續 Atlas 輸出會合併成同一區塊，視覺上更像同一段回覆，但不會逐筆框出每個系統訊息。

**為什麼這樣做**：Atlas 想接近 opencode 這類 terminal-first agent 的使用感，但第一版先保持單欄與少量提示，避免加入 theme、autocomplete、diff viewer 或多 session 造成複雜度。

**影響與取捨**：畫面會比原本最小 Textual 殼更清楚，也更適合鍵盤操作；取捨是目前還不是完整 opencode clone，slash 選單也先只支援現有 slash command 和 skills。

進入 TUI 後，目前支援：

- `/help`：列出可用命令。
- `/exit`：乾淨結束程式。
- `/login-done`：只有 Atlas 正在等待 tGenie 手動登入時使用；登入完成後回到 TUI 輸入它，Atlas 會繼續流程。
- `/llm-wiki`：初始化本機 LLM Wiki，並載入內建 LLM Wiki skill instructions。
- `/llm-wiki ingest <path>`：匯入 workspace 內單一 PDF 或 PDF 資料夾，更新 LLM Wiki，並輸出 HTML mirror 與 graph。
- `/skill-creator`：載入內建 skill creator instructions。
- 其他 slash command：顯示清楚錯誤訊息。

## 首次 tGenie 設定

第一次執行 `atlas` 時，如果 Atlas 找不到已儲存的 tGenie URL，TUI 會提示你貼上 tGenie URL。送出後，Atlas 會把 URL 儲存在使用者全域設定，不放在 workspace。

後續啟動會重用已儲存的 URL，不會每次都重新詢問。Chrome profile 也會放在使用者全域設定目錄，不放在 workspace：

- Windows：`%APPDATA%\Atlas\chrome-profile`
- macOS：`~/Library/Application Support/Atlas/chrome-profile`
- Linux：`$XDG_CONFIG_HOME/Atlas/chrome-profile`，沒有 `XDG_CONFIG_HOME` 時使用 `~/.config/Atlas/chrome-profile`

儲存 URL 後，Atlas 會用系統 Chrome channel 開啟 tGenie，並使用 headed mode，也就是會看到真正的 Chrome 視窗。你需要在 Chrome 裡手動完成 tGenie 登入，回到 Atlas TUI 後輸入：

```text
/login-done
```

**這個做法是什麼**：Atlas 只負責儲存 tGenie URL、開 Chrome、重用 Chrome profile，然後等待你確認登入完成。

**為什麼這樣做**：公司登入流程和 SSO 通常只能由使用者本人操作，讓 Atlas 自動處理帳密風險太高。

**影響與取捨**：第一次使用需要多一步手動登入；好處是登入狀態可由 Chrome profile 保留，之後通常不用重新登入。Atlas 不會要求、儲存或處理密碼、token 或 SSO 憑證。

如果 Chrome 沒有安裝，或公司政策阻擋 Playwright 開啟系統 Chrome，Atlas 會在 TUI 顯示錯誤訊息。這時請先確認公司電腦有 Google Chrome，且允許本機 Python 程式開啟 Chrome。

## 真實 tGenie 單輪對話

Atlas 目前已有 #5 的最小真實 tGenie conversation adapter。你在 TUI 完成 tGenie 登入並輸入 `/login-done` 後，一般 prompt 會送到已開啟的 tGenie 頁面，等待 tGenie 完成生成，再把最新回覆顯示回 Atlas transcript。

**這個做法是什麼**：
adapter 使用 async Playwright 操作既有 tGenie 網頁。它會先等待 `textarea[name="chat-input-textarea"]` 可用，預設沿用目前對話，不強制點 `New Conversation`。如果呼叫端明確要求 fresh conversation，才會在需要時點 `svg.tabler-icon-layout-sidebar` 打開 sidebar，然後點 `button:has-text("New Conversation")`。

送出 prompt 時，Atlas 會把使用者任務包在 bootstrap instructions 裡一起貼進 tGenie。bootstrap 會告訴 tGenie：它正在 Atlas agent harness 裡、不能直接操作本機檔案、需要本機工具時必須輸出 `atlas.tool_call` fenced JSON，且一次只能要求一個 tool call。後續 tool 執行結果會用 `atlas.tool_result` 回貼。

目前 adapter 使用的主要 selector：

- textarea：`textarea[name="chat-input-textarea"]`
- new conversation：`button:has-text("New Conversation")`
- sidebar toggle：`svg.tabler-icon-layout-sidebar`
- attach：`button[data-tooltip-id="attach-button-tooltip"]`
- attach success：`page.get_by_text(file_name, exact=False)`
- send：`button:has(svg.tabler-icon-circle-arrow-up-filled)`
- stop generating：`img[alt="stop icon"]`
- reply：`div.prose`

除了 attach success 和 reply 之外，adapter 會取 `.first`；reply 會取 `.last`，也就是最新的 tGenie 回覆。

**為什麼這樣做**：
這些 selector 來自公司環境已驗證的 tGenie UI。預設不強制開新對話，可以避免 Atlas 意外切走你目前正在看的 tGenie conversation；bootstrap 仍會在每次 Atlas 任務送出時一起提供必要上下文。

**影響與取捨**：
#5 只負責真實單輪對話與 bootstrap prompt injection。它會等待 stop generating icon 出現再消失；如果 tGenie 回覆太快、stop icon 沒來得及出現，adapter 會改用「最新 reply 文字已變更」判斷完成。#5 不會執行 tool call，也不會把 `atlas.tool_result` 貼回 tGenie；這是 #8 的責任。

## 真實 tGenie Tool Loop

Atlas 目前也有 #8 的最小真實 tGenie tool loop。完成 `/login-done` 後，TUI 的一般 prompt 不只會送到 tGenie，還會檢查 tGenie 回覆中是否包含 `atlas.tool_call`。如果 tGenie 要求工具，Atlas 會在目前 workspace 內執行工具，把 `atlas.tool_result` 回貼到同一個 tGenie conversation，然後繼續等 tGenie 下一輪回覆，直到 tGenie 產出不含 tool call 的 final answer。

**這個做法是什麼**：
tool loop 把三個既有部分接起來：真實 tGenie conversation adapter、文字型 `atlas.tool_call` parser、以及 workspace tool runtime。adapter 只負責把訊息送進同一個 tGenie conversation 並讀最新回覆；tool loop 負責判斷回覆是 final answer、合法 tool call，或需要 tGenie 修正的 tool-call error。

目前真實 tool loop 支援的工具：

- `file.list`
- `file.read`
- `file.search`
- `file.write`
- `pdf.attach`
- `shell.run`

`shell.run` 會保留 runtime 的安全政策。低風險命令可執行；`confirmation-required` 和 `rejected` 不會被繞過，而是以 structured `atlas.tool_result` 回貼給 tGenie，讓 tGenie 說明下一步。

`pdf.attach` 是 workspace PDF attach tool。它只接受 workspace 內的 `.pdf` 檔案，例如 `docs/report.pdf`。Atlas 會先 normalize path，確認檔案仍在 workspace 內，才會透過 tGenie 網頁原生 attach UI 上傳。

安全規則很保守：

- 接受 workspace 內的 `.pdf`。
- 拒絕非 PDF。
- 拒絕 workspace 外路徑，例如 absolute path、`..` escape，或指向 workspace 外的 symlink。
- 拒絕不存在的 path 或資料夾。

PDF attach 時，TUI 會顯示這些狀態：

- `Working: Uploading PDF`
- `Working: PDF uploaded`
- `Working: PDF upload failed`
- `Working: PDF upload timed out`

**這個做法是什麼**：`pdf.attach` 把「path validation」和「瀏覽器 attach 操作」分開。workspace safety 仍由 Atlas runtime 負責；tGenie adapter 只拿已驗證過的 PDF path 去操作網頁。

**為什麼這樣做**：tGenie 是網頁工具，模型可能會產生錯誤 path。先在 Atlas 端拒絕危險或不支援的 path，可以避免把 workspace 外的文件誤上傳。

**影響與取捨**：目前 attach tool 只支援單一 PDF，不支援 Word、Excel、PowerPoint、圖片。LLM Wiki ingestion 會在較高層使用這個單檔 attach 能力，對 PDF 資料夾採每批 1 個 PDF 的保守策略。

如果 tGenie 回傳 malformed JSON、missing `tool`、unknown tool、missing `args`、invalid `args`，或同一輪多個 tool calls，Atlas 不會執行任何工具。Atlas 會把 `atlas.tool_call_error` 回貼到同一個 conversation，要求 tGenie 下一輪只重送一個修正後的 `atlas.tool_call`。

**為什麼這樣做**：
tGenie 是網頁版 LLM，不一定有 native function calling。用文字型 fenced JSON 可以先建立穩定 protocol；把解析、工具執行、回貼結果放在 Atlas 端，則能維持 workspace 邊界和 shell safety policy。

**影響與取捨**：
#8 讓 tGenie 可以透過 Atlas 讀 workspace、搜尋檔案、寫檔，並執行受控 shell command。#9 讓 tGenie 可以透過 `pdf.attach` 上傳 workspace-local PDF。取捨是 shell confirmation 目前還沒有互動式確認 UI；需要確認的命令會回傳 `confirmation-required`，不會真的執行。LLM Wiki PDF ingestion 會沿用這條 tool loop。

手動 smoke test 可以在 workspace 放一個含有固定字串的文字檔，例如 `atlas-smoke.txt`，內容寫 `needle-from-workspace`。啟動 Atlas、完成 `/login-done` 後，請 tGenie 搜尋 workspace 裡哪個檔案包含 `needle-from-workspace`，並根據 tool result 回答檔名與該行文字。

PDF attach 手動 demo 可以在 workspace 放一份不含敏感資料的小 PDF，例如 `demo.pdf`。啟動 Atlas、完成 `/login-done` 後，請 tGenie 摘要 `demo.pdf`。tGenie 應該先要求 `pdf.attach`，Atlas 會上傳 PDF，再把 `atlas.tool_result` 回貼到同一個 conversation。

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

## HITL 實機驗證

如果需要到公司 Windows 電腦驗證 tGenie URL、手動登入、Chrome profile、probe selector 或 PDF attach UI，請使用 [`hitl.md`](hitl.md)。

**這個做法是什麼**：`hitl.md` 是人工實機驗證 runbook，包含沒有 git 時只能用 GitHub issue 留言的回報格式。

**為什麼這樣做**：tGenie 登入、SSO、真實 UI selector 和公司 Windows 環境無法由 AFK agent 自行驗證。

**影響與取捨**：人工回報會多一步，但可以避免 agent 依靠猜測實作真實 tGenie adapter。

## 文字型 tool-call protocol

Atlas v1 先使用文字型 protocol，讓沒有 native function calling 的 tGenie 也能要求 Atlas 執行工具。

**這個做法是什麼**：
tGenie 在回覆中輸出一個 fenced JSON block。Atlas 只接受 `type` 是 `atlas.tool_call` 的 JSON，並要求裡面有 `tool` 和 `args`。

```json
{
  "type": "atlas.tool_call",
  "tool": "echo",
  "args": {
    "text": "hello"
  }
}
```

**為什麼這樣做**：
tGenie 目前是公司內部網頁版 LLM，不能假設它有 API 或 function calling。用 fenced JSON 可以先把「模型要求工具」這件事穩定下來，之後再接真實 tGenie UI。

**重要限制**：
一次只能有一個 tool call。Atlas v1 不支援同一回覆內多個 tool call，也不支援 parallel tool execution。

**錯誤處理原則**：

- malformed JSON：不執行任何工具，要求模型重送合法 JSON。
- missing tool：不執行任何工具，要求模型補上 `tool` name。
- unknown tool name：不執行任何工具，回報目前不支援該工具。
- missing args：不執行任何工具，要求模型補上 `args` object。
- invalid args：不執行任何工具，要求 `args` 必須是 JSON object。
- 多個 tool call：不執行任何工具，要求模型拆成單次 tool call。

工具結果會用 `atlas.tool_result` 回貼給下一輪模型：

```json
{
  "type": "atlas.tool_result",
  "tool": "echo",
  "result": {
    "text": "hello"
  }
}
```

**fake adapter 測試方式**：
目前 fake adapter 是開發測試用，不會打開 Chrome，也不會連真實 tGenie。它用固定回覆模擬「模型要求 tool → Atlas 執行 tool → 回貼 tool result → 模型回覆下一輪」。

本機開發可以跑：

```bash
uv run python -m unittest tests.test_tool_protocol tests.test_fake_tool_loop
```

這個方式的取捨是：它不能驗證真實 tGenie 網頁 selector 或登入狀態，但可以先保證 protocol、錯誤處理和回路狀態是穩定可測的。

## Workspace Tool Runtime

Atlas 目前已有 workspace tool runtime。它是模型要求本機工具時的安全執行層。

**這個做法是什麼**：
runtime 只接受一個 workspace。所有 file path 都會先 normalize，最後必須仍然留在 workspace 內。`..`、absolute path、指向 workspace 外的 symlink 都會被拒絕或略過。

**為什麼這樣做**：
tGenie 的 tool call 是模型產生的文字。Atlas 不能信任模型提供的 path 或 shell command，所以所有本機操作都先經過 runtime 檢查。

目前支援的 file tools：

- `file.list`：列出 workspace 內的檔案與資料夾。
- `file.read`：讀取 workspace 內的 UTF-8 文字檔。
- `file.search`：搜尋 workspace 內的檔名或文字內容。
- `file.write`：寫入 workspace 內的文字檔，必要時建立 parent directories。

目前支援的 shell tool：

- `shell.run`：執行受控 shell command，回傳 `stdout`、`stderr`、`exit_code`。

Shell policy 分成三種結果：

- `ok`：低風險命令可直接執行。
- `confirmation-required`：高風險但可能合理的命令不會直接執行，必須等使用者確認。
- `rejected`：明顯危險的命令會直接拒絕，例如 `curl ... | sh` 這類網路腳本直接 pipe 進 shell 的模式。

**這樣的影響與取捨**：
這個 runtime 已經可以測試 file tools 和 shell policy，但還沒有完整互動式確認 UI。遇到 `confirmation-required` 時，目前只會回傳狀態，讓後續 TUI 或真實 tool loop 接手處理。

本機開發可以跑：

```bash
uv run python -m unittest tests.test_tool_runtime
```

## Skill Loader

Atlas 目前已有最小 skill loader。它讓使用者在 TUI 輸入 slash command，就能把一段 skill instructions 注入目前對話或 fake adapter 測試回路。

**這個做法是什麼**：
skill 是一段 Markdown instructions。內建 skills 由 Atlas 提供；workspace-local skills 放在目前 workspace 的 `.atlas/skills/<skill-name>/SKILL.md`。

目前內建 skills：

- `/llm-wiki`：初始化本機 LLM Wiki，並載入 LLM Wiki 工作流 instructions。
- `/skill-creator`：載入建立新 skill 的 instructions。

workspace-local skill 範例：

```text
your-workspace/
└── .atlas/
    └── skills/
        └── repair-notes/
            └── SKILL.md
```

建立上面的檔案後，在 TUI 輸入：

```text
/repair-notes
```

Atlas 會讀取 `.atlas/skills/repair-notes/SKILL.md`，並用固定格式注入：

```text
<atlas.skill_instructions name="repair-notes">
...SKILL.md content...
</atlas.skill_instructions>
```

**為什麼這樣做**：
Atlas v1 先用文字格式跟 tGenie 溝通，不假設 tGenie 有 native skill API。固定的 `atlas.skill_instructions` 區塊讓 fake adapter 和未來真實 tGenie adapter 都能用同一種方式測試。

**這樣的影響與取捨**：
新增 workspace-local skill 不需要改 Atlas core code，只要新增 `SKILL.md`。取捨是目前不支援遠端 skill registry、版本管理、同時啟用多個 skills，或一般 plugin marketplace。

本機開發可以跑：

```bash
uv run python -m unittest tests.test_skills tests.test_commands tests.test_tui
```

## LLM Wiki 初始化、lint 與輸出

Atlas 目前已有本機 LLM Wiki 初始化、lint、HTML mirror 與 graph HTML 輸出。

**這個做法是什麼**：
在 TUI 輸入 `/llm-wiki` 後，Atlas 會在目前 workspace 建立 `wiki/` 結構：

```text
wiki/
├── raw-sources/
├── schema/
│   └── page.md
├── index.md
├── log.md
├── pages/
│   ├── concepts/
│   ├── sources/
│   └── contradictions/
└── output/
    ├── html/
    └── graph/
```

`wiki/raw-sources` 是 immutable source of truth。Lint、HTML renderer、graph renderer 都不會修改這個資料夾。

Wiki knowledge pages 放在 `wiki/pages/` 底下，使用 Markdown 加 YAML frontmatter：

- `wiki/pages/concepts`：概念頁。
- `wiki/pages/sources`：來源摘要頁。
- `wiki/pages/contradictions`：矛盾或衝突紀錄頁。

```markdown
---
title: Pump Failure
type: concept
tags: [failure, pump]
confidence: high
contradiction: false
---
# Pump Failure

Related to [[Motor Current|current signature]].
```

目前公開的 Python 介面：

- `initialize_wiki(workspace)`：建立 wiki 目錄與必要檔案。
- `load_wiki_pages(workspace)`：讀取 pages、frontmatter、body、wikilinks。
- `lint_wiki(workspace)`：檢查缺 frontmatter、broken wikilink、孤立頁面與基本 metadata 問題。
- `render_html_mirror(workspace)`：輸出 `wiki/output/html/*.html`，並把 wikilinks 轉成本機 HTML links。
- `render_graph_html(workspace)`：使用 `pyvis` 輸出 `wiki/output/graph/index.html`，用 wikilinks 產生 nodes/edges 與接近 Obsidian 的深色 graph HTML。

**為什麼這樣做**：
LLM Wiki 先做成 deterministic 本機 module，比直接綁真實 tGenie UI 穩定。這樣可以先測 wiki schema、link 檢查、HTML 與 graph 輸出，後續 PDF ingestion 才有穩定落點。

**這樣的影響與取捨**：
目前 graph 會新增 `pyvis` dependency，換來較接近 Obsidian 的互動式 graph HTML。取捨是安裝依賴變多，但 `render_graph_html` 介面保持很小，後續仍可替換內部 renderer。

本機開發可以跑：

```bash
uv run python -m unittest tests.test_wiki
```

## LLM Wiki PDF ingestion

Atlas 目前支援 `/llm-wiki ingest <path>`，可以把 workspace 內的單一 PDF 或 PDF 資料夾匯入 LLM Wiki。

```text
/llm-wiki ingest docs/report.pdf
/llm-wiki ingest docs/pdf-folder
```

**這個做法是什麼**：
Atlas 會先確認 `<path>` 留在 workspace 內。如果它是單一 PDF，就請 tGenie 透過既有 `pdf.attach` tool 上傳該 PDF；如果它是 PDF 資料夾，就依檔名排序，採每批 1 個 PDF 的保守批次策略逐一處理。每次 ingestion 都會把 LLM Wiki skill instructions 和任務指令送給 tGenie，要求 tGenie 用 file tools 更新 `wiki/pages/`、`wiki/index.md` 和 `wiki/log.md`，並保留來源追蹤，例如記錄內容來自哪個 PDF。

完成後 Atlas 會重新產生：

- `wiki/output/html/`：可閱讀 HTML wiki。
- `wiki/output/graph/index.html`：PyVis graph HTML。

**為什麼這樣做**：
tGenie 是網頁 UI，PDF 上傳與長文件整理都可能失敗。先保證單一 PDF 端到端成功，再用每批 1 個 PDF 處理資料夾，可以降低上傳失敗或模型 context 過載時的損失。

**這樣的影響與取捨**：
每批 1 個 PDF 很穩，但大量 PDF 會比較慢。好處是如果後面的 batch 失敗，前面已完成的 wiki 檔案、HTML mirror 和 graph 仍會保留，Atlas 也會顯示失敗的是哪個 PDF。

限制：

- 只接受 workspace 內的 `.pdf`。
- 拒絕非 PDF、workspace 外路徑、不存在的路徑。
- 目前不支援 Word、Excel、PowerPoint、圖片或任意 binary file。

手動 demo：匯入 PDF

1. 在 workspace 放一個不含敏感資料的 PDF，例如 `demo.pdf`。
2. 啟動 Atlas 並完成 tGenie 登入。
3. 在 TUI 輸入：

```text
/llm-wiki ingest demo.pdf
```

成功時應該會看到 Atlas 上傳 PDF、等待 tGenie 整理內容，最後產生可閱讀 HTML wiki 與 graph。輸出位置是 `wiki/output/html/` 和 `wiki/output/graph/index.html`。

本機開發可以跑：

```bash
uv run python -m unittest tests.test_llm_wiki_ingest
```

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
notes
list
texts
highlight_text <文字區塊編號>
clear_highlights
inspect <元素編號>
set sidebar_toggle <元素編號>
click <元素編號>
hover <元素編號>
wait <毫秒>
note <欄位> <觀察內容>
set_text latest_response <文字區塊編號>
set new_conversation <元素編號>
type <元素編號> 測試訊息
replace <元素編號> 測試訊息
smoke <prompt_input 編號> <send_button 編號>
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
3. 輸入 `inspect <編號>`，讓 probe 往父層找 button、ARIA、title、test id 等 stable selector candidates。
4. 輸入 `set sidebar_toggle <編號>`，新版 probe 會把 stable selector candidates 寫進報告。
5. 輸入 `click <編號>`，真的點開 sidebar。
6. 輸入 `list`，重新掃描目前畫面。
7. 找出 new conversation 按鈕的編號。
8. 輸入 `set new_conversation <編號>`。
9. 輸入 `click <編號>`，真的建立新對話。
10. 輸入 `list`。
11. 找出 prompt input 對話輸入框的編號。
12. 輸入 `set prompt_input <編號>`。
13. 找出 send button 的編號。
14. 輸入 `inspect <編號>`，讓 probe 往父層找 button、ARIA、title、test id 等 stable selector candidates。
15. 輸入 `set send_button <編號>`，新版 probe 會把 stable selector candidates 寫進報告。
16. 找出 attach 按鈕的編號。
17. 輸入 `set attach_button <編號>`。
18. 找出 model selector 的編號。
19. 輸入 `set model_selector <編號>`。
20. 找出 web search 開關的編號。
21. 輸入 `set web_search_toggle <編號>`。
22. 輸入 `notes`，看 #5 還缺哪些觀察欄位。
23. 輸入 `note target_model Gemini-3.1-Pro Preview`，記錄 #5 目前要使用的模型。
24. 輸入 `note default_model Gemini-3.0-flash Preview (All around help)`，記錄新對話預設模型。
25. 點開 model selector，確認 `Gemini-3.1-Pro Preview` 能被選到。
26. 輸入 `note selected_model Gemini-3.1-Pro Preview`。
27. 在還沒輸入前，輸入 `note send_before_typing <你看到的 send 狀態>`。
28. 輸入 `replace <prompt_input 編號> 測試訊息`，確認文字真的進入輸入框。
29. 輸入 `note send_after_typing <你看到的 send 狀態>`。
30. 輸入 `smoke <prompt_input 編號> <send_button 編號>`，送出固定測試 prompt：`Atlas smoke test. Reply with exactly: atlas-ok`。
31. 生成中把滑鼠移到 send/stop button：`hover <send_button 編號>`。
32. 如果畫面顯示 `Stop generating`，輸入 `note stop_generating_hover_label Stop generating`。
33. 輸入 `note send_while_generating <生成中 send/stop 狀態>`。
34. 等回覆完成後輸入 `note send_after_completion <完成後 send 狀態>`。
35. 輸入 `texts`，列出可見文字區塊。
36. 找到包含 `atlas-ok` 的候選編號，輸入 `highlight_text <文字區塊編號>`。
37. 看 Chrome 畫面，確認粉紅框線圈住的是最新 assistant 回覆那段文字。
38. 如果框錯位置，輸入 `clear_highlights`，換下一個包含 `atlas-ok` 或最接近最新回覆的編號再跑 `highlight_text`。
39. 確認後輸入 `set_text latest_response <文字區塊編號>`；新版 probe 會再高亮一次並記錄。
40. 輸入 `note latest_response_text atlas-ok`。
41. 輸入 `note latest_response_rule <你如何判斷這是最新 assistant 回覆>`。
42. 輸入 `note smoke_result success`。
43. 輸入 `shot`，留一張人工截圖。
44. 輸入 `done`，結束並輸出報告。

**這個做法是什麼**：probe 不只記錄 selector，也會用 `inspect` 從元素座標往 DOM 父層找穩定 selector candidates；對 `latest_response` 這種不能點擊的文字區塊，`texts` 會先標上 probe-only id，`highlight_text` 再用這個 id 在 Chrome 畫面上加粉紅框線確認。

**為什麼這樣做**：tGenie 有些狀態是 hover tooltip、生成中短暫狀態，或純文字回覆；Playwright 不一定能自動判斷語意，讓 probe 用 id 找回同一個候選節點並框出來，可以避免只靠 index 或座標猜。

**影響與取捨**：公司畫面和截圖不用帶出來，只要把非敏感文字、selector hint、狀態描述寫進 `tgenie_probe_*.md`。取捨是多一步 `highlight_text` 可視確認，且 probe 會暫時在本機瀏覽器 DOM 加 `data-atlas-probe-text-id`；這只影響當次 probe 頁面，不會送回公司系統。

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
- model selector 找得到，且目前 #5 目標模型是 `Gemini-3.1-Pro Preview`。
- 輸入測試訊息後，畫面真的有文字。
- send button 在送出後是否會變成 stop generating。
- 回覆完成後是否會變回 send。
- smoke test 送出 `Atlas smoke test. Reply with exactly: atlas-ok` 後，tGenie 回覆 `atlas-ok`。
- `texts` 能列出最新 assistant 回覆，並可用 `highlight_text <編號>` 在 Chrome 高亮確認後，再用 `set_text latest_response <編號>` 記錄。

成功標準：

- `tgenie_probe_*.md` 裡面有 `sidebar_toggle`、`new_conversation`、`prompt_input`、`send_button`、`model_selector`、`latest_response`。
- `sidebar_toggle` 和 `send_button` 底下有 `Stable selector candidates`，或明確記錄沒有可用 parent button / ARIA / title / test id。
- `tgenie_probe_*.md` 的「#5 必填觀察」裡有 `target_model`、`selected_model`、`stop_generating_hover_label`、`latest_response_text`、`smoke_result`。
- screenshot 看得出來停在 tGenie 對話頁。

失敗時要記錄：

- 哪個 target 找不到。
- `list` 輸出的相關元素編號。
- `texts` 輸出的相關文字區塊編號。
- `highlight_text <編號>` 是否有在 Chrome 框到候選文字區塊。
- 如果框錯，記錄錯的編號與最後正確的編號。
- screenshot。
- 你手動看到的按鈕文字。

### HITL 4：真實 tGenie tool loop 能不能跑

對應 issue: #8

目前這個功能已完成最小版本。實機驗證重點是確認真實 tGenie conversation 能照 Atlas bootstrap instructions 產生 tool call，Atlas 能執行工具並把結果回貼。

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

目前正式 `pdf.attach` tool 已完成最小版本。實機驗證重點是確認 workspace-local PDF 真的能透過 tGenie 網頁 attach UI 上傳，且 TUI 狀態與錯誤訊息清楚。

要驗證：

- attach 按鈕找得到，並能打開檔案選擇流程。
- workspace 內的 `.pdf` 可以透過 `pdf.attach` 上傳。
- 非 PDF、workspace 外路徑、不存在的檔案會被拒絕，不會打開檔案選擇流程。
- 上傳時 TUI 會顯示 `Working: Uploading PDF`。
- 成功時 TUI 會顯示 `Working: PDF uploaded`。
- 失敗或逾時時 TUI 會顯示 `Working: PDF upload failed` 或 `Working: PDF upload timed out`。

成功標準：

- 使用不含敏感資料的小 PDF，例如 `demo.pdf`。
- 請 tGenie 摘要該 PDF 時，Atlas 能完成 `pdf.attach` 並把 `atlas.tool_result` 回貼到同一個 conversation。
- tGenie 能根據已 attach 的 PDF 回答。

失敗時要記錄：

- attach 按鈕看起來叫什麼名字。
- 點擊後畫面發生什麼事。
- PDF 是否被公司政策或 tGenie 限制。
- TUI 顯示的 `Working:` 或 `Error:` 訊息。

### HITL 6：單 PDF 到 LLM Wiki 的端到端 ingestion

對應 issue: #12

目前這個功能已完成最小版本。實機驗證重點是確認 tGenie 能依 LLM Wiki skill instructions 整理 PDF，並透過 Atlas file tools 寫入 wiki。

要驗證：

- `/llm-wiki ingest <path>` 能上傳單一 PDF。
- `/llm-wiki ingest <path>` 可接受 PDF 資料夾。
- tGenie 能整理 PDF。
- Atlas 能更新 wiki Markdown。
- Atlas 能輸出 HTML。
- Atlas 能輸出 PyVis graph。
- PDF 資料夾使用每批 1 個 PDF 的保守策略；後面 batch 失敗時，前面已完成結果仍保留。

成功標準：

- 有 `wiki/index.md`。
- 有 `wiki/log.md`。
- 有至少一個 wiki knowledge page。
- 有可用瀏覽器打開的 HTML，例如 `wiki/output/html/index.html`。
- 有 graph HTML：`wiki/output/graph/index.html`。

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
