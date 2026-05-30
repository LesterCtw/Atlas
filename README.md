# Atlas

Atlas 是一個 Python terminal 工具，用來把公司內部的網頁版 LLM（tGenie）接到本機 workspace。

使用者在 terminal 執行 `atlas`，Atlas 會開啟系統 Chrome、連到 tGenie，並把使用者輸入、workspace 檔案工具、附件上傳、LLM Wiki 產出串成一個可操作的流程。

HTML 版部署與使用手冊在 [`atlas-deployment-and-usage.html`](atlas-deployment-and-usage.html)。

FA STEM demo 驗證測試清單在 [`docs/fa-stem-demo-validation-checklist.html`](docs/fa-stem-demo-validation-checklist.html)。

## 目前範圍

Atlas v1 提供：

- `atlas` terminal TUI。
- 首次 tGenie URL 設定。
- 使用系統 Chrome 開啟 tGenie。
- 手動登入、登入狀態自動偵測與 Chrome profile 重用。
- 單一 workspace 邊界。
- tGenie 對話與 tool loop。
- workspace file tools：`file.list`、`file.read`、`file.search`、`file.write`。
- read-only tool batch：`atlas.tool_batch` 一次最多 5 個獨立的 `file.list`、`file.read`、`file.search`。
- workspace attachment：`file.attach` 支援 `.pdf`、`.jpg`、`.jpeg`、`.png`。
- Attachment evidence 結構化證據，用來保存附件回合中的 observation、inference、uncertainty、confidence 與 coordinates。
- 保守的 `shell.run` 安全政策。
- slash command：`/help`、`/exit`、`/login-done`、`/fa-stem brief <path>`、`/llm-wiki`、`/llm-wiki ingest <path>`、`/skill-creator`。
- FA STEM folder-level triage，使用 3x3 Photo Bundle 產生 candidate observations，做 second-pass original-image review、final ranking，並輸出 demo-ready HTML report package。
- LLM Wiki Markdown、HTML mirror、graph HTML 輸出。

## 重要限制

- Atlas v1 以 Windows 11 + Python 3.12 為主要部署環境。
- 公司電腦部署不需要 `uv`。
- Atlas 使用系統已安裝的 Google Chrome，不使用 Playwright 下載的瀏覽器。
- tGenie 登入必須由使用者在 Chrome 裡手動完成；如果 Atlas 偵測到 tGenie chat 輸入框與送出按鈕已出現，會自動進入可用狀態。
- Atlas 不會要求、儲存或處理密碼、SSO token 或公司憑證。
- v1 只支援單一 workspace、單一 tGenie conversation。
- v1 的附件工具只支援 workspace 內的 `.pdf`、`.jpg`、`.jpeg`、`.png`。
- v1 沒有 FastAPI、headless mode、packaged Windows exe、Office 附件、embedding/vector database。
- `shell.run` 目前非常保守。需要確認或高風險的 command 不會直接執行。

## 部署需求

公司 Windows 電腦需要：

- Windows 11。
- Python 3.12.x。
- Google Chrome。
- 可開啟 tGenie 的公司網路與 tGenie URL。
- PowerShell。

確認 Python：

```powershell
py -3.12 --version
```

確認 Chrome：從開始選單或桌面捷徑打開 Google Chrome。

## Windows 部署

進入 Atlas 專案資料夾後執行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\atlas --help
```

啟動 Atlas：

```powershell
.\.venv\Scripts\atlas
```

指定 workspace：

```powershell
.\.venv\Scripts\atlas C:\path\to\workspace
```

### 從任意 PowerShell 執行 atlas

如果希望之後在任意資料夾直接輸入 `atlas`，可以把 `.venv\Scripts` 加到目前使用者的 PATH。

在 Atlas 專案資料夾執行一次：

```powershell
$atlasScripts = "$PWD\.venv\Scripts"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
[Environment]::SetEnvironmentVariable("Path", "$atlasScripts;$userPath", "User")
```

關掉 PowerShell，重新開一個新的 PowerShell。之後可執行：

```powershell
atlas
atlas C:\path\to\workspace
```

這個方式的取捨是：日常使用最方便，但 Atlas 專案資料夾和 `.venv` 不能移走。若移動資料夾，需要重新設定 User PATH。

## 本機開發部署

如果是在自己的開發機，且已安裝 `uv`，可以用：

```bash
uv sync
uv run atlas --help
uv run atlas
```

執行測試：

```bash
uv run --with pytest pytest
```

## 第一次啟動

1. 在 workspace 目錄執行 `atlas`，或執行 `atlas <workspace-path>`。
2. Atlas TUI 啟動後，如果尚未設定 tGenie URL，會要求你貼上 tGenie URL。
3. Atlas 會把 tGenie URL 儲存在使用者全域設定，不放在 workspace。
4. Atlas 會開啟系統 Chrome，並使用固定 Chrome profile。
5. 你在 Chrome 裡手動完成 tGenie 登入。
6. 如果 Atlas 偵測到 tGenie chat UI 已可用，會顯示 `Atlas: tGenie is ready. You can continue in Atlas.`，不需要再輸入確認指令。
7. 如果 Atlas 還沒有偵測到 chat UI，回到 Atlas TUI，輸入：

```text
/login-done
```

完成後就可以在 Atlas 裡輸入一般 prompt 或 slash command。

使用者設定位置：

- Windows：`%APPDATA%\Atlas`
- macOS：`~/Library/Application Support/Atlas`
- Linux：`$XDG_CONFIG_HOME/Atlas`，沒有時使用 `~/.config/Atlas`

Chrome profile 也放在同一個使用者設定區域，因此登入狀態通常可以在下次啟動時重用。

## 基本使用

啟動：

```powershell
atlas
```

或：

```powershell
atlas C:\path\to\workspace
```

TUI 操作：

- 直接輸入問題或任務，按 `Enter` 送出。
- `Shift+Enter` 插入換行。
- 較長或多行的 prompt 會在輸入區內換行；縮放視窗時 Atlas 會保留底部輸入區可見。
- 輸入時可用左右方向鍵在文字中移動；多行或自動換行時可用上下方向鍵在文字行之間移動。
- 空白輸入框中可用上下方向鍵瀏覽送出歷史。
- 輸入 `/` 會顯示 slash command 選單。
- 使用上下方向鍵選擇 slash command。
- 如果 slash command 選單只剩一個候選，第一次按 `Enter` 或 `Tab` 會補齊 command 並加上尾端空白；再按一次 `Enter` 才會送出。

常用命令：

```text
/help
/exit
/login-done
/fa-stem brief <workspace-relative-folder>
/llm-wiki
/llm-wiki ingest <workspace-pdf-or-directory>
/skill-creator
```

## Input to Output Workflow

### 1. 一般對話

Input：

- 使用者在 Atlas TUI 輸入一段 prompt。

Process：

1. Atlas 把 prompt 送到目前的 tGenie conversation。
2. Bootstrap prompt 會要求 tGenie 把任務當成要完成的工作；在 final answer 前，先用安全且相關的 tool call 盡可能完成檔案檢查、搜尋、修改與測試。
3. tGenie 直接回答，或輸出 `atlas.tool_call` 要求單一工具；如果只是獨立的讀取、列檔或搜尋，也可以輸出 `atlas.tool_batch` 一次要求最多 5 個 read-only tool。
4. 如果有 tool call，Atlas 會解析 fenced JSON；如果 tGenie 網頁 UI 已經把 Markdown fence 渲染掉，Atlas 也會掃描完整 JSON object。
5. Atlas 只在目前 workspace 內執行允許的工具。
6. Atlas 把 `atlas.tool_result` 或 `atlas.tool_batch_result` 回貼給 tGenie。
7. tGenie 根據工具結果繼續下一個檢查，或在已完成、被工具錯誤阻擋、需要使用者決策時產生 final answer。
8. 如果同一回合要求太多次 tool call，Atlas 會停止該回合，避免無限循環。

Output：

- Atlas TUI transcript 顯示 `Working:` 狀態與最後 `Atlas:` 回覆。
- 如果 tGenie 使用 `file.write`，workspace 內會產生或更新檔案。

這個做法是什麼：Atlas 把 tGenie 當成主要推理模型，本機工具由 Atlas 代為執行；tool call 解析會依 JSON 結構判斷完整物件，不用 regex 去切 `{...}`。`atlas.tool_batch` 只用於 read-only 檔案檢查，一次最多 5 個 call。

為什麼這樣做：tGenie 是網頁版 LLM，不一定支援 native function calling；文字型 tool-call protocol 可以先讓它參與本機工作流程。網頁 UI 可能把 Markdown code fence 渲染掉，所以 Atlas 不能只依賴反引號。

影響與取捨：流程清楚、容易檢查，也比較能處理 nested `args`；bootstrap prompt 會鼓勵 tGenie 在回覆前多做合理檢查。read-only batch 可以減少讀多個檔案或搜尋多個線索時的來回時間；取捨是 batch 只能做無副作用工具，`file.write`、`shell.run`、`file.attach` 仍維持一次一個。5 個 call 是單批上限，不是總檢查上限；如果還有相關檔案或檢查，tGenie 應繼續請求下一批。Atlas 也會限制單回合 tool call 次數，避免模型卡在無限循環。

### 2. Workspace 檔案工作

Input：

- 例如：「讀取 `notes/report.md` 並整理重點」或「搜尋 workspace 裡包含 `error code` 的檔案」。

Process：

1. tGenie 需要檔案資訊時，輸出 `file.list`、`file.read` 或 `file.search` tool call。
2. 如果需要多個互不依賴的讀取、列檔或搜尋，tGenie 可以用 `atlas.tool_batch` 一次送出最多 5 個 call；如果還沒看完整個相關範圍，下一輪應繼續送下一批。
3. Atlas 檢查 path 必須留在 workspace 內。
4. Atlas 執行檔案工具並回傳結果。
5. tGenie 根據結果回答，或要求 `file.write` 產出檔案。

Output：

- TUI 顯示回答。
- `file.write` 會在 workspace 內寫入 Markdown、HTML 或文字檔。

這個做法是什麼：所有檔案讀寫都經過 workspace path 檢查；read-only batch 只是把多個安全檔案查詢包在同一回合。

為什麼這樣做：避免模型誤讀或誤寫 workspace 外的公司或個人檔案。

影響與取捨：安全邊界比較清楚，也能加速多檔案檢查；取捨是不能直接操作 workspace 外的檔案，而且 batch 不能寫檔、跑 shell 或上傳附件。

### 3. PDF 摘要或分析與圖片附件

Input：

- 例如：「請摘要 `docs/example.pdf`」。
- 例如：「請看 `photos/panel.png`，說明圖片裡的異常點」。

Process：

1. tGenie 請求 `file.attach`。
2. Atlas 確認 path 是 workspace 內的 `.pdf`、`.jpg`、`.jpeg` 或 `.png` 檔案。
3. Atlas 透過 tGenie 網頁上傳附件。
4. Atlas 把上傳結果回貼給 tGenie。
5. tGenie 讀取 PDF 或圖片後產生摘要或分析。

Output：

- TUI 顯示 PDF 或圖片分析結果。
- 如果任務要求產出檔案，結果會寫入 workspace。

這個做法是什麼：Atlas 只允許 workspace-local PDF、JPG、PNG 透過 tGenie 原生附件功能上傳。

為什麼這樣做：附件內容可能敏感，先限制路徑和副檔名可以降低誤上傳風險。

影響與取捨：支援 PDF 與常見圖片；Word、Excel、PowerPoint 目前不支援。

### 4. Attachment evidence 結構化證據

Input：

- 任何需要分析附件的 workflow，例如圖片初篩、PDF 摘要或後續多步驟分析。

Process：

1. Atlas 在附件回合中保留可重用的文字證據。
2. 每筆 evidence 會記錄來源影像或附件 identity、`observation`、`inference`、`uncertainty`、`confidence`。
3. 如果模型有回傳位置資訊，Atlas 也會保存 `coordinates`，例如百分比座標與半徑。
4. 後續 workflow 可以把這些 saved text evidence 放進 prompt，不需要假設模型仍然看得到前一次附件。

Output：

- workflow 內可重用的 structured evidence。
- 後續 prompt 可讀的 saved text evidence。

這個做法是什麼：Attachment evidence 是 Atlas harness 層的資料合約，把「模型看過附件後的有用觀察」保存成結構化文字。

為什麼這樣做：tGenie 是透過網頁附件看檔案；後續 workflow 需要穩定文字證據，不能只依賴前一輪視覺上下文。

影響與取捨：後續 workflow 比較容易追蹤來源、區分 observation 和 inference，也能保留 uncertainty。取捨是 evidence 是文字摘要，不等於原始附件本身；若後續步驟需要重新檢查細節，仍應由 Atlas workflow 重新提供附件或檔案內容。

### 5. FA STEM brief folder-level triage 與 final ranking

Input：

```text
/fa-stem brief <workspace-relative-folder>
```

接著在下一個 prompt 貼上 case background，例如電性異常、結構描述、想優先判斷的重點。

Process：

1. Atlas 驗證資料夾必須在 workspace 內。
2. Atlas 等待下一個非空 prompt，並把它當作 FA STEM case background。
3. Atlas recursive 收集資料夾底下的 `.jpg` 與 `.jpeg`，忽略其他檔案。
4. Atlas 用固定排序把影像每 9 張組成一個 3x3 Photo Bundle，最後不足 9 張也會形成 partial bundle。
5. 每個 tile 會有 A1 到 C3 的 label，並保留 tile-to-source mapping 回原始影像 path。
6. Atlas 將每個 Photo Bundle attach 給 tGenie。
7. tGenie 依照 FA STEM prompt 回傳 JSON `candidate_observations`，包含 `tile_label`、`observation`、`inference`、`uncertainty`、`confidence` 與 optional `coordinates`。如果網頁 UI 把 fenced JSON 渲染成 plain JSON，Atlas 仍會用 shared JSON parser 解析。
8. Atlas 從 saved first-pass evidence 選出最多 10 張 candidate 原始影像。
9. Atlas 重新 attach 每張候選原圖，執行 second-pass original-image review。
10. second-pass review 會要求 tGenie 回傳百分比圈選座標、reason、confidence、uncertainty，並標示 `primary-suspect-relevant` 或 `profile-only`。
11. Atlas 用 first-pass 與 second-pass saved text evidence 做 final ranking，不假設 tGenie 還看得到前面回合的附件。
12. final ranking 支援 0 或 1 個 primary electrical suspect，也支援多個 profile anomalies。
13. 如果證據不足，final ranking 可以輸出 `primary suspect unclear`，同時保留 profile anomalies。
14. Atlas 在 case folder 內寫出 HTML report，並在 Atlas-managed artifact folder 保存 bundles、metadata、model outputs 與 report assets。
15. HTML report 會在原圖上畫 overlay：primary electrical suspect 使用紅色圈，profile anomalies 使用黃色或橘黃色圈。

Output：

- `<case-folder>/atlas-fa-stem-brief.html`
- `<case-folder>/atlas-fa-stem-report/bundles/photo-bundle-XXX.png`
- `<case-folder>/atlas-fa-stem-report/metadata.json`
- `<case-folder>/atlas-fa-stem-report/model-outputs.json`
- `<case-folder>/atlas-fa-stem-report/assets/report.css`
- demo 驗證時可搭配 `docs/fa-stem-demo-validation-checklist.html` 檢查要測什麼、怎麼判斷 pass/fail、何時要開 follow-up issue。

這個做法是什麼：這是一條 folder-level triage 流程，先把整個 STEM JPG 資料夾壓成可追蹤來源的 3x3 Photo Bundle，取得 first-pass candidate observations，再重新上傳候選原圖做 second-pass original-image review，最後用 saved text evidence 做 final ranking。

為什麼這樣做：tGenie 一次只能穩定看有限附件，而且附件不應假設會跨回合保留；bundle 讓 Atlas 用較少回合掃過多張影像，second-pass 則用原圖補回細節，final ranking 只讀保存下來的文字證據。Artifact folder 讓 demo 後可以檢查 bundles、metadata.json、model-outputs.json 與 report assets，同時不移動、不覆寫原始 STEM 圖。

影響與取捨：first-pass candidate observations 不是 final conclusions；final ranking 也只是 full-case triage ranking，不是 final FA root cause 結論。報告中的紅色與黃色圈選是 AI 建議的初篩標記，不是量測級標註。這個流程會多花最多 10 個候選原圖 review 回合；取捨是速度較慢，但可避免用低解析 bundle 直接下結論，也能在證據不足時保留 `primary suspect unclear`。

### 6. LLM Wiki 匯入

Input：

```text
/llm-wiki ingest docs/example.pdf
```

或：

```text
/llm-wiki ingest docs/pdf-folder
```

Process：

1. Atlas 驗證指定 path 必須在 workspace 內。
2. Atlas 收集單一 PDF 或資料夾中的 PDF。
3. Atlas 初始化 `wiki/` 結構。
4. Atlas 以每批 1 個 PDF 的保守方式送給 tGenie。
5. tGenie 使用 `file.attach` 讀取 PDF。
6. tGenie 使用 file tools 更新 wiki Markdown。
7. Atlas 重新產生 HTML mirror 與 graph HTML。

Output：

- `wiki/index.md`
- `wiki/log.md`
- `wiki/pages/`
- `wiki/output/html/index.html`
- `wiki/output/graph/index.html`

這個做法是什麼：raw source 保持原樣，wiki 是 LLM 維護的知識層，HTML 與 graph 是閱讀輸出。

為什麼這樣做：FA 工程師可以保留原始 PDF，又能用瀏覽器閱讀整理後的知識庫。

影響與取捨：每批 1 個 PDF 比較慢，但比較穩，較不容易讓 tGenie context 或附件流程失控。

### 7. Skill 使用

Input：

```text
/llm-wiki
/skill-creator
/skill-creator <prompt>
```

Process：

1. Atlas 找到內建 skill 或 workspace-local skill。
2. Atlas 把 skill instructions 注入目前工作流程。
3. 如果 skill command 後面有 `<prompt>`，Atlas 會用該 skill instructions 直接執行這段 prompt。
4. `/llm-wiki` 會同時初始化 `wiki/`。

Output：

- TUI 顯示 skill 已載入。
- 後續 prompt 會依照該 skill 的規則工作。

Workspace-local skill 位置：

```text
.atlas/skills/<skill-name>/SKILL.md
```

## 主要輸出位置

| 輸出 | 位置 |
| --- | --- |
| 一般回答 | Atlas TUI transcript |
| 模型要求寫入的檔案 | workspace 內指定 path |
| FA STEM brief report | `<case-folder>/atlas-fa-stem-brief.html` |
| LLM Wiki Markdown | `wiki/index.md`、`wiki/log.md`、`wiki/pages/` |
| LLM Wiki HTML | `wiki/output/html/index.html` |
| LLM Wiki graph | `wiki/output/graph/index.html` |
| tGenie URL 與 Chrome profile | 使用者全域設定區域 |

## Workspace 安全規則

- Atlas 啟動時只綁定一個 workspace。
- `file.list`、`file.read`、`file.search`、`file.write` 都只能操作 workspace 內 path。
- `file.read` 和 `file.search` 有預設大小與結果數量上限，避免模型一次讀取或搜尋過多資料。
- `atlas.tool_batch` 只允許 `file.list`、`file.read`、`file.search`，一次最多 5 個 call。
- `file.attach` 只接受 workspace 內 `.pdf`、`.jpg`、`.jpeg`、`.png`。
- absolute path、`..` escape、指向 workspace 外的 path 會被拒絕。
- `shell.run` 預設保守。大部分 command 會回傳 `confirmation-required`，高風險 command 會回傳 `rejected`，允許執行的 command 也有 timeout。

## 常見問題

### `atlas` 找不到

如果尚未設定 PATH，請使用：

```powershell
.\.venv\Scripts\atlas
```

或重新設定 User PATH 後開新的 PowerShell。

### Chrome 沒有開啟

確認公司電腦已安裝 Google Chrome，且公司政策允許本機 Python 程式開啟 Chrome。

### Atlas 一直要求 `/login-done`

先在 Chrome 裡完成 tGenie 登入。若 tGenie chat 輸入框與送出按鈕已出現，Atlas 通常會自動偵測並顯示可以繼續使用。

如果公司網路或 tGenie UI 載入較慢，Atlas 可能還沒偵測到；這時再回到 Atlas TUI 輸入 `/login-done`。

### 附件上傳失敗

檢查：

- 檔案在 workspace 裡。
- 副檔名是 `.pdf`、`.jpg`、`.jpeg` 或 `.png`。
- path 沒有使用 absolute path 或 `..` 跳出 workspace。
- 附件不含不該上傳的敏感資料。

### `/llm-wiki ingest` 找不到檔案

請確認指令中的 path 是相對於 workspace 的 path。例如 workspace 是 `C:\Work\AtlasData`，PDF 是 `C:\Work\AtlasData\docs\a.pdf`，指令應該是：

```text
/llm-wiki ingest docs/a.pdf
```

## 維護者驗證

在開發機確認自動化測試：

```bash
uv run --with pytest pytest
```

確認 Python 檔案可編譯：

```bash
python -m compileall atlas
```
