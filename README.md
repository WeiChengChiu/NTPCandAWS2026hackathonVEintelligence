# NTPC × AWS 2026 Hackathon — VE Intelligence

訴願案件智慧檢索。以 Amazon Bedrock Knowledge Base 為檢索後端，語料為訴願決定書、
相關函釋、法規與行政法院判決。

> ⚠️ **這是公開 repo。** 任何情況下都不要把 AWS 憑證、API Token、金鑰寫進檔案並 commit。
> 憑證只放在各自電腦的 `~/.aws/`（Windows 為 `%USERPROFILE%\.aws\`），該路徑已被 `.gitignore` 排除。

---

## 環境需求

| 項目 | 要求 | 備註 |
|---|---|---|
| Python | **3.10 以上** | 程式使用 `dataclass(slots=True)` |
| boto3 / botocore | **≥ 1.43.93** | 低於此版本沒有 `agentic_retrieve_stream`，會直接 `AttributeError` |
| AWS Region | `us-west-2` | 主辦方指定區域（另可用 `us-east-1`） |

---

## 1. 設定 AWS 憑證

憑證由 Workshop Studio 發給，屬**臨時憑證會過期**。**每人各自取得自己的一組**，不要共用，
共用會導致兩人的 session 同時失效、也無法區分操作來源。

寫入 `[default]` profile，這樣 boto3 與 Kiro 都不需要指定 profile 名稱。

### macOS / Linux

`~/.aws/credentials`

```ini
[default]
aws_access_key_id = <你的 ACCESS_KEY_ID>
aws_secret_access_key = <你的 SECRET_ACCESS_KEY>
aws_session_token = <你的 SESSION_TOKEN>
```

`~/.aws/config`

```ini
[default]
region = us-west-2
output = json
```

收斂檔案權限：

```bash
chmod 600 ~/.aws/credentials ~/.aws/config
```

### Windows 11

建立資料夾 `C:\Users\<你的帳號>\.aws\`，在裡面放兩個**沒有副檔名**的檔案。

> 用「記事本」另存新檔時，檔名要用雙引號包住（例如 `"credentials"`），
> 否則會被存成 `credentials.txt` 而讀不到。編碼選 UTF-8。

`%USERPROFILE%\.aws\credentials`

```ini
[default]
aws_access_key_id = <你的 ACCESS_KEY_ID>
aws_secret_access_key = <你的 SECRET_ACCESS_KEY>
aws_session_token = <你的 SESSION_TOKEN>
```

`%USERPROFILE%\.aws\config`

```ini
[default]
region = us-west-2
output = json
```

**Windows 特別注意：不要另外設環境變數。** 如果你執行過 `set AWS_ACCESS_KEY_ID=...`，
環境變數的優先序**高於** credentials 檔案。日後你更新了檔案但那個終端機還開著，
就會出現「檔案明明是新的卻還是 ExpiredToken」這種很難查的狀況。只用檔案最單純。

### 憑證過期了怎麼辦

臨時憑證到期後會出現 `ExpiredToken` / `ExpiredTokenException`。
boto3 讀的是檔案裡的靜態值，**不會自動續期**。
到 Workshop Studio 重新取得一組，覆蓋上面兩個檔案即可，程式不用改。

---

## 2. 安裝

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows 11 (PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

若 PowerShell 擋下啟動腳本，先執行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

`.venv/` 已被 `.gitignore` 排除，**兩台電腦各自建立自己的虛擬環境**，不要 commit。

---

## 3. 驗證設定

```bash
python scripts/verify_aws.py
```

成功會印出解析來源、region 與帳號資訊：

```
Resolved via   : shared-credentials-file
Region         : us-west-2
Session token  : present
----------------------------------------------
Account ID     : ****
ARN            : arn:aws:sts::****:assumed-role/WSParticipantRole/Participant
```

這支腳本只呼叫 STS `get_caller_identity`，不需要安裝 AWS CLI。

---

## 4. 查詢 Knowledge Base

```bash
# agentic 檢索（多步規劃 + 生成答案 + 引用來源）
python scripts/ask_kb.py "訴願逾越法定期間，依訴願法第77條第2款如何認定？"

# 顯示 agent 規劃過程
python scripts/ask_kb.py --trace "寄存送達的生效日如何計算？"

# 純向量檢索，不經 LLM，快且便宜
python scripts/ask_kb.py --mode retrieve --max-results 5 "當事人不適格"
```

程式內使用：

```python
from ve_intelligence import KnowledgeBaseClient

kb = KnowledgeBaseClient()          # 預設 KB 與 us-west-2

# 一次拿完整結果
answer = kb.ask("公寓大廈管理委員會解任的函釋依據？")
print(answer.answer)
print(answer.sources)               # 去重後的來源文件清單

# 串流，適合接 UI
for event in kb.ask_stream("停歇業場所是否仍須辦理公安申報？"):
    if event.kind == "token":
        print(event.text, end="")
    elif event.kind == "trace":
        print(f"[{event.step}/{event.status}]")
```

`ask_stream` 產出的是與 UI 無關的 `StreamEvent`，CLI、Streamlit、FastAPI SSE
都可以接同一條路徑。

---

## 專案結構

```
src/ve_intelligence/
  config.py        # KB ID、region、agentic 參數，皆可用環境變數覆蓋
  kb.py            # KnowledgeBaseClient：retrieve / ask / ask_stream
scripts/
  verify_aws.py    # 用 boto3 驗證憑證（不需 AWS CLI）
  ask_kb.py        # 命令列查詢工具
```

可用環境變數覆蓋預設值：`VE_KB_ID`、`VE_AWS_REGION`、`VE_KB_MAX_ITERATION`。

---

## 已知問題：Knowledge Base 索引品質

**目前 KB 檢索結果不可靠，UI 開發時請注意。**

來源 PDF 本身文字層完整（141 份全部可正常抽取文字），但 KB 匯入時採用
`SMART_PARSING` 且啟用 image extraction，把公文頁面當成圖片交給多模態模型處理，
導致索引內容中的中文幾乎全部流失。抽樣 68 個 chunk、涵蓋 38 份文件，
可用比例為 0%：

- 66 個為亂碼（漢字流失，只剩數字與雜訊字母）
- 2 個為英文影像描述（模型還把繁體中文誤判為日文）

`agentic_retrieve_stream` 有時會靠 `FullDocumentExpansion` 讀到原始文件而答對，
但並不穩定，同一問題可能時對時錯。

修正方向尚未定案，候選方案為：改 parsing 策略、或先把 PDF 抽成純文字再上傳（推薦）。

---

## 黑客松規範重點

- 不建立公開 S3 bucket；`ve-s3-bucket` 已確認四項 Block Public Access 全開、
  無 bucket policy、`BucketOwnerEnforced`、AES256 加密。
- 部署區域限 `us-west-2` 與 `us-east-1`。
- **Bedrock 請求需控制在 1 RPS 以下**，批次腳本請自行加上間隔（本專案診斷腳本使用 1.3 秒）。
- 不得匯入個人資料、財務、健康等受管制資料。現有語料為公開之去識別化訴願決定書
  （姓名與地址以 `○` 遮蔽）。
- 上傳程式碼前確認未包含任何憑證。
