# Atlas HITL Runbook

日期：2026-05-27  
地點：公司 Windows 電腦  
目標：盡可能推進 `ready-for-human` / 真實 tGenie 相關 issue，並把 AFK agent 不能取得的環境資訊收集完整。

## 公司端沒有 git 的重要前提

明天不要假設公司電腦有 `git clone` 或 `git pull`。

你在公司端有兩種可能路線：

1. **可以從 GitHub 網頁下載 ZIP**：下載 Atlas repo ZIP、解壓縮，然後可以跑本文件的 PowerShell 腳本。這條路可以驗 `#2`。
2. **只能在 GitHub issue 留言**：不能下載 repo、不能跑 Atlas 腳本。這條路不能完整驗 `#2`，但仍然可以手動收集 `#4` / `#5` / `#9` 的 tGenie 資訊。

如果明天真的只能 issue 留言，請直接跳到「Issue-only 模式」。

## 先回答：#4 有沒有被 #2 擋住？

正式 issue dependency 來看，`#4` 沒有被 `#2` 擋住。

- `#4` 寫的是 `Blocked by #3`
- `#3` 已經 closed
- 所以 `#4` 可以開始

但實務上，`#2` 和 `#4` 共用同一批公司環境驗證：Windows、系統 Chrome、tGenie URL、手動登入、Chrome profile。因此明天順序應該是：

1. 先驗 `#2`
2. 接著驗 `#4`
3. 有時間才收集 `#5` 的 UI 行為
4. `#8`、`#9`、`#12` 不優先實作，只做觀察

## 這份 runbook 的做法

**做法是什麼**：  
用一個 PowerShell 腳本收集公司電腦環境、Python 安裝、Atlas editable install、CLI help、compile 結果，然後啟動 tGenie probe 讓你手動登入和校準 selector。

**為什麼這樣做**：  
AFK agent 可以寫程式，但不能進公司網路、不能手動 SSO 登入、不能看真實 tGenie UI。所以明天最有價值的工作是把這些真實環境資訊和 probe 報告帶回來。

**影響與取捨**：  
這會多花一點時間收集 log，但後面 `#4` / `#5` 的實作會少很多猜測。這份流程不會自動處理帳密或 SSO，也不要把公司機密文件上傳到 GitHub。

## 已知限制

- 目標環境是 Windows 11 + Python 3.12.x。
- Atlas v1 不使用 `uv` 部署到公司電腦。
- Atlas 必須使用系統 Chrome，不使用 `playwright install` 下載的瀏覽器。
- tGenie 需要你手動登入。
- tGenie URL、SSO 行為、UI selector 都只能在公司環境確認。

## 目前假設

- 公司電腦可以開 PowerShell。
- 公司電腦已安裝 Chrome。
- 公司電腦可用 `py -3.12` 啟動 Python 3.12。
- 你可以拿到 tGenie URL。
- 你能在公司環境完成 tGenie 登入。

## 不清楚、需要明天確認

- `py -3.12` 是否可用。
- `pip install -e .` 是否會被公司網路或權限擋住。
- Playwright 使用 `channel="chrome"` 是否能找到公司電腦的 Chrome。
- Chrome profile 放在 `%APPDATA%\Atlas\chrome-profile` 是否能重用登入狀態。
- tGenie UI 裡哪些 selector 穩定、哪些只是暫時可用。
- `gemini-3.0-pro` 是否存在、是否要點模型選單才可用。

## 明天要先準備的東西

- 若可以下載 ZIP：Atlas repo ZIP 已下載並解壓縮到公司 Windows 電腦。
- 若不能下載 ZIP：至少要能打開 GitHub issue 網頁留言。
- 你知道 repo 的資料夾位置。
- 一個可以測試的 tGenie URL。
- 不含機密資料的測試 workspace。
- 可選：一份不含機密內容的小 PDF，若你有時間觀察 attach UI。

不要用真實客戶文件做第一次 probe。

## 路線 A：可以下載 ZIP 時

這條路不需要 git，但需要你能從 GitHub 網頁下載 repo ZIP。

### A0：下載 repo ZIP

在公司電腦瀏覽器打開 repo：

```text
https://github.com/LesterCtw/Atlas
```

下載：

```text
Code -> Download ZIP
```

解壓縮後進入 Atlas 資料夾。你應該會看到：

```text
pyproject.toml
README.md
atlas\
scripts\
tests\
```

如果你看不到這些檔案，先不要跑後面的安裝，直接到 issue 留言：

```text
#2 HITL blocker

Company machine has no git.
Could not download or extract Atlas ZIP.
What I could access:
What I could not access:
Error message or screenshot summary:
```

### A1：打開 PowerShell

在 Atlas repo 根目錄打開 PowerShell。

確認目前位置：

```powershell
Get-Location
```

你應該在 Atlas repo，例如：

```text
C:\...\Atlas
```

如果 PowerShell 不允許執行本機 script，先跑：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

這只影響目前這個 PowerShell 視窗。

### A2：跑 HITL 收集腳本

先檢查腳本是否存在：

```powershell
Test-Path .\scripts\hitl_collect_windows.ps1
```

如果回傳 `True`，跑腳本。

把 URL 換成公司 tGenie URL：

```powershell
.\scripts\hitl_collect_windows.ps1 -TgenieUrl "https://your-company-tgenie-url"
```

如果你暫時不想把 URL 放進 command，可以先跑不含 probe 的版本：

```powershell
.\scripts\hitl_collect_windows.ps1 -SkipProbe
```

然後之後手動跑：

```powershell
.\.venv\Scripts\python scripts\probe_tgenie.py --url "https://your-company-tgenie-url" --output-dir probe-output
```

如果回傳 `False`，代表 ZIP 裡還沒有這個輔助腳本。改跑下面這組手動指令：

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\atlas --help
.\.venv\Scripts\python scripts\probe_tgenie.py --help
.\.venv\Scripts\python -m compileall atlas scripts
.\.venv\Scripts\python scripts\probe_tgenie.py --url "https://your-company-tgenie-url" --output-dir probe-output
```

請把每個 command 成功或失敗記在 issue comment。若某一步失敗，停下來記錄錯誤，不要硬往下跑。

### 這個腳本會做什麼

- 建立 `hitl-output/hitl-<timestamp>.log`
- 檢查 PowerShell、使用者、電腦名稱、Chrome 可能位置
- 檢查 `py -3.12 --version`
- 建立 `.venv`
- 執行 `pip install -e .`
- 執行 `atlas --help`
- 執行 `scripts\probe_tgenie.py --help`
- 執行 `compileall atlas scripts`
- 如果有提供 `-TgenieUrl`，啟動互動式 tGenie probe

### 必須記錄的輸出

請保留這些檔案：

- `hitl-output/hitl-*.log`
- `probe-output/tgenie_probe_*.json`
- `probe-output/tgenie_probe_*.md`
- `probe-output/tgenie_probe_*.png`

回來後至少要貼給 Codex：

```text
hitl-output 最新 log 的路徑：
probe-output 最新 md 的路徑：
probe-output 最新 json 的路徑：
probe-output 最新 screenshot 的路徑：
```

如果 screenshot 或 URL 有公司敏感資訊，不要貼到 GitHub；先只貼路徑和摘要。

### A3：tGenie probe 互動流程

腳本打開 Chrome 後，請先完成 tGenie 登入，並停在 tGenie 主對話頁。

Terminal 顯示：

```text
完成後回到 terminal 按 Enter 繼續 probe...
```

回到 PowerShell 按 Enter。

Probe 會列出像這樣的元素：

```text
[00] button role=- type=- box=... label=...
[01] textarea role=- type=- box=... label=...
```

每個人的 index 可能不同，不要照抄下面的數字。你要照畫面上的 index 選。

### 必須校準的 targets

先輸入：

```text
targets
list
```

依序完成：

```text
set sidebar_toggle <index>
click <index>
list

set new_conversation <index>
click <index>
list

set prompt_input <index>
set send_button <index>
set attach_button <index>
set model_selector <index>
set web_search_toggle <index>
shot
done
```

如果某個 target 找不到，不要亂猜。請記錄：

```text
找不到的 target：
畫面當下狀態：
我試過的 index：
是否需要先點其他按鈕：
```

### 每個 target 要觀察什麼

`sidebar_toggle`

- 按了之後 sidebar 是否展開或收合
- label 是否穩定，例如 sidebar、menu、navigation

`new_conversation`

- 是否必須先展開 sidebar 才看得到
- 按了之後是否真的開新對話

`prompt_input`

- 是 `textarea`、`contenteditable`，還是其他 editor
- placeholder 是什麼
- 能不能用 probe 的 `type <index> <text>` 輸入

`send_button`

- 輸入文字前是否 disabled
- 輸入文字後是否 enabled
- 送出後 label / icon 是否變成 stop generating
- 回覆完成後是否變回 send

`attach_button`

- 是否在主畫面可見
- 是否需要點加號或選單才會出現
- 點了之後是否打開檔案選擇器

`model_selector`

- `gemini-3.0-pro` 是否已經是預設
- 如果不是，能不能選到
- 模型選單打開後是否需要另外校準 option

`web_search_toggle`

- 是否存在
- 開關狀態是否可辨識
- 開關後畫面有沒有明確變化

## 路線 B：Issue-only 模式

如果公司端不能用 git，也不能下載 repo ZIP，那明天不能跑 Atlas 腳本。這不是你操作問題，而是 `#2` 的公司端 source/artifact access blocker。

這條路的目標改成：直接在 GitHub issue 留言，把 AFK agent 需要的人類觀察資料補齊。

### B1：先在 `#2` 留言

到 `#2` 留這段，照實填：

```text
#2 HITL result - issue-only company environment

Company machine has git:
Can download GitHub ZIP:
Can open PowerShell:
Can run py -3.12 --version:
Python version, if known:
Can install packages with pip:
Chrome installed:
Chrome version, if known:
Can access tGenie URL:
Can upload/download files from GitHub web:

Blocker:
I cannot run Atlas probe because:

Notes:
```

這段的用途：讓我們知道 `#2` 是真的完成、部分完成，還是被公司端「不能取得 repo artifact」卡住。

### B2：在 `#4` 留言

直接用一般 Chrome 手動打開 tGenie，不需要 Atlas。

在 `#4` 留：

```text
#4 HITL result - manual tGenie login

tGenie URL reachable:
Need company network or VPN:
Need SSO:
Manual login completed:
Login steps summary:
Does normal Chrome keep login after closing/reopening:
Any security warning:
Any timeout or redirect:

Expected Atlas first-run behavior:
- URL prompt text should say:
- Waiting-for-login text should say:
- Chrome-missing error should say:

Notes:
```

這段的用途：讓 agent 實作 `#4` 時知道真實登入流程，不用猜 UX 和錯誤訊息。

### B3：在 `#5` 留言

手動在 tGenie 介面操作，不需要 Atlas。

做這些事：

1. 打開 sidebar。
2. 開 new conversation。
3. 確認或選擇 `gemini-3.0-pro`。
4. 輸入：

```text
Atlas smoke test. Reply with exactly: atlas-ok
```

5. 送出。
6. 觀察送出按鈕在「生成中」和「完成後」的狀態。

在 `#5` 留：

```text
#5 HITL observation - manual single-turn tGenie flow

Can open sidebar:
Sidebar button visible text/icon:
Can create new conversation:
New conversation button visible text/icon:
Default model:
Can select gemini-3.0-pro:
Prompt input type, if visible:
Prompt input placeholder:
Send button before typing:
Send button after typing:
Button while generating:
Button after completion:
Final response visible:
Final response text:
Any obvious label around response area:

Notes:
```

這段的用途：讓 agent 實作 tGenie adapter 時知道要點哪裡、等什麼狀態、讀哪裡。

### B4：可選，在 `#9` 留言

如果 `#5` 手動流程很順，才觀察 attach。

不要用公司機密 PDF。只用空白或非機密 PDF。

在 `#9` 留：

```text
#9 HITL observation - manual PDF attach

Attach button visible:
Attach button visible text/icon:
Click attach opens file picker:
Can select a local PDF:
Upload starts:
Upload completed:
Upload completion clue:
Upload failed:
Failure message:
Can ask tGenie to summarize PDF:

Notes:
```

這段的用途：讓 agent 知道 attach UI 是否真的可自動化。

## 路線 A 後續紀錄

下面幾段是「可以下載 ZIP 並跑腳本」時要整理的結果。若你只能走 Issue-only 模式，直接用上面的 `B1` 到 `B4` 留言模板即可。

### A4：#2 驗收紀錄

`#2` 的目標是確認 Python 專案骨架與 probe 能在公司環境運作。

請回來後提供：

```text
#2 HITL result

Python version:
pip install -e .:
atlas --help:
probe --help:
compileall:
Chrome opened by probe:
tGenie manual login:
probe JSON generated:
probe Markdown generated:
probe screenshot generated:

Failed step, if any:
Notes:
```

成功標準：

- `py -3.12 --version` 是 Python 3.12.x
- `pip install -e .` 成功
- `atlas --help` 成功
- `probe_tgenie.py --help` 成功
- `compileall atlas scripts` 成功
- probe 能開系統 Chrome headed mode
- probe 能產出 JSON、Markdown、screenshot

### A5：#4 驗收紀錄

`#4` 的目標是首次設定、tGenie URL、Chrome profile、手動登入流程。

目前程式還不一定完整實作 `#4`，所以明天重點是把真實限制收集清楚。

請做這幾件事：

1. 完成一次 probe 登入。
2. 關掉 Chrome。
3. 再跑一次 probe，使用同一個 URL：

```powershell
.\.venv\Scripts\python scripts\probe_tgenie.py --url "https://your-company-tgenie-url" --output-dir probe-output
```

4. 看是否還需要重新登入。
5. 檢查 profile 目錄：

```powershell
$profileDir = Join-Path $env:APPDATA "Atlas\chrome-profile"
Test-Path $profileDir
Get-ChildItem $profileDir | Select-Object -First 20 Name
```

請回來後提供：

```text
#4 HITL result

tGenie URL format:
Need VPN or company network:
Need SSO:
Manual login completed:
Profile path:
Profile directory exists:
Second probe reused login:
Chrome path found:
Any company security warning:

What should Atlas show if Chrome is missing:
What should Atlas show while waiting for login:
README changes needed:
Notes:
```

成功標準：

- 我們知道 tGenie URL 如何取得或輸入
- 我們知道是否需要 VPN / SSO
- `%APPDATA%\Atlas\chrome-profile` 可以建立
- 第二次 probe 能重用登入狀態，或至少知道為什麼不能
- Chrome 找不到或登入未完成時，應該顯示的錯誤訊息已經明確

### A6：如果還有時間，收集 #5 資訊

`#5` 是真實 tGenie 單輪對話。它被 `#2` 和 `#4` 的實機資訊影響很大。

先不要期待明天完成 `#5`。目標是觀察 UI 行為。

在 probe 裡可以測：

```text
type <prompt_input_index> Atlas smoke test. Reply with exactly: atlas-ok
click <send_button_index>
shot
list
```

等 tGenie 回覆完成後，再：

```text
shot
list
done
```

請記錄：

```text
#5 observation

Can open new conversation:
Can select or confirm gemini-3.0-pro:
Prompt input accepts typed text:
Send button enabled after typing:
Button state while generating:
How completion is visible:
Can see final response:
Final response text:
Any obvious selector for response area:
Screenshot before send:
Screenshot while generating:
Screenshot after completion:
Notes:
```

成功標準：

- 能手動開新對話
- 能輸入 prompt
- 能送出
- 能看出生成中與生成完成的差異
- 能看到 tGenie 最終回答

## Optional：如果 #5 很順，才觀察 #9

`#9` 是 PDF attach。它正式被 `#5` 擋住，所以不要優先花太久。

如果時間夠，請只用不含機密資料的小 PDF。

請記錄：

```text
#9 observation

Attach button visible:
Click attach opens file picker:
Can choose workspace-local PDF:
Upload starts:
Upload completion visible:
Upload failure message, if any:
Can ask tGenie to summarize PDF:
Notes:
```

不要測 workspace 外的真實公司文件。

## 明天不要花時間做的事

- 不要實作 `#8` tool loop。
- 不要實作 `#12` LLM Wiki ingestion。
- 不要用真實敏感 PDF 測試。
- 不要把 screenshot 或內部 URL 直接貼到公開 GitHub issue。
- 不要修改公司電腦的 system PATH；如果要測 `atlas` 全域命令，先只記錄需求，不急著改。

## 回來後給 Codex 的最小回報

請照這個格式貼：

```text
HITL 2026-05-27 result

Files:
- hitl log:
- probe md:
- probe json:
- screenshot:

#2:
- pass/fail:
- failed step:
- notes:

#4:
- pass/fail:
- profile reused login:
- URL/SSO notes:
- README changes needed:

#5 observation:
- can create new conversation:
- can send prompt:
- can detect completion:
- response extraction clue:

#9 observation, optional:
- attach UI observed:
- upload status clue:

Sensitive info omitted:
```

## 回來後的下一步

如果 `#2` 成功：

- 可以關掉 `#2`，或貼驗收結果後關閉。

如果 `#4` 資訊完整：

- 可以把 `#4` 從 `needs-triage` 移到 `ready-for-agent` 或 `ready-for-human`。
- 若只剩一般程式實作，交給 AFK agent。
- 若還要你決定登入 UX 或錯誤文案，維持 `ready-for-human`。

如果 `#5` 有足夠 selector 與行為資訊：

- 可以把 `#5` 移到可執行狀態。
- 實作重點會是 tGenie adapter：new conversation、model selection、send、wait、read response。
