# Implementation Plan

**實作計畫：訴願決定書 AI 輔助撰擬系統（黑客松精簡版）**

## Overview

**概觀**

本計畫依 design.md 之階段規劃（P0–P10）展開為可執行之編碼任務，並依黑客松時程精簡。實作語言為 Python 3.12。

**測試範圍之說明**：design.md 之 Testing Strategy（pytest、Hypothesis、23 條正確性性質、覆蓋率門檻）刻意排除於本次黑客松實作範圍之外。design.md 仍完整保留，作為日後強化（production hardening）之參考基準。本次之合規保證改由兩項機制承擔：

1. **執行時去識別化閘門**：`PIIRedactor.scan_residual` 為產品程式碼而非測試，於流程中實際執行，掃到殘留個資即拋 `ResidualPIIError` 中止流程；每個往 S3、Bedrock、Knowledge Base 之出口在送出前再掃一次 payload。拿掉自動化測試不會拿掉這層保護。
2. **`scripts/compliance_check.py`**：一支可直接執行之檢查腳本，不使用 pytest，交件前人工跑一次。

三項貫穿全計畫之硬性約束：

第一，**去識別化閘門優先於任何 AWS 出口**。P1 未完成並人工驗證前，不得執行 P3 及其後任何會將案件內容上傳 S3 或送往 Bedrock／Knowledge Base 之任務。競賽規範第 2 條禁止將個人資料匯入 AWS 帳戶，而訴願文件本質上充滿個資。此為合規要求，非實作偏好。以型別系統輔助強制：AWS 出口函式之參數型別僅接受 `RedactedDocument`，不接受 `SourceDocument`。

第二，**Bedrock 一律經 `BedrockGateway`**。P2 完成後不得再直接建立 boto3 bedrock client，且速率須低於每秒 1 請求。此亦為競賽規範要求。

第三，**每一階段完成即建立一次 git commit**。每個 P 階段之最後一個子任務即為「以樣本案件執行端到端驗證 → 確認完成條件 → 建立 commit」，commit 訊息沿用 design.md 指定之文字。

## Tasks

- [ ] 1. P0 專案骨架與設定管理
  - [ ] 1.1 建立專案目錄結構與套件骨架
    - 建立 `src/petition_ai/` 及其子套件 `core/`、`models/`、`ingest/`、`extraction/`、`retrieval/`、`similarity/`、`drafting/`、`feedback/`、`ui/`，各含 `__init__.py`
    - 建立 `src/petition_ai/app.py`：`AppContainer` 依賴組裝容器與 `build_container()` 骨架，欄位涵蓋 loader、redactor、rehydrator、extractor、retriever、matcher、generator、guard、feedback、metrics、templates、gateway、limiter，先以型別註記加 `None` 佔位
    - 建立 `infra/`、`scripts/` 目錄
    - 建立 `pyproject.toml`：專案 metadata、`src` layout 設定、ruff 與 mypy 設定（不含 pytest 與覆蓋率設定）
    - _Requirements: 14.1_

  - [ ] 1.2 建立 `.gitignore`、`.env.example` 與相依套件鎖定檔
    - `.gitignore` 必須包含 `.env`、`.env.*`、`.local/`、`inbox/`、`exports/`、`*.pem`、`__pycache__/`
    - `.gitignore` 必須不匹配 `.kiro/` 或其任何子目錄（競賽規範第 9 條要求展示 specs／hooks／steering）
    - `.env.example` 列出所有設定鍵名但不含任何真實憑證或 model_id
    - `requirements.txt`：boto3、gradio、pydantic、pydantic-settings、pypdf、python-docx、tenacity、orjson、cryptography、charset-normalizer，全部鎖定版本
    - `requirements-dev.txt`：僅 ruff、mypy、detect-secrets（不含 pytest、pytest-cov、hypothesis、moto）
    - _Requirements: 13.9, 13.10_

  - [ ] 1.3 實作設定管理 `src/petition_ai/core/config.py`
    - 以 pydantic-settings 定義 `AppConfig`：region（僅允許 `us-east-1` 或 `us-west-2`）、embedding_model_id、generation_model_id、law_kb_id、precedent_kb_id、s3_bucket、feedback_db_path
    - `FusionWeights`：alpha／beta／gamma 和為 1.0、delta ∈ [0, 1] 之驗證器
    - `SimilarityWeights`：四項權重和為 1.0 之驗證器
    - learning_rate 預設 0.2、exemplar_threshold、rate_limit refill_interval 預設 1.05、top_k 預設 8、precedent_limit 預設 5
    - 上傳限制：副檔名白名單、單檔與總量大小上限
    - _Requirements: 12.1, 12.12, 13.3, 13.7_

  - [ ] 1.4 實作例外型別與日誌遮蔽
    - `src/petition_ai/core/errors.py`：`ResidualPIIError`、`RateLimitTimeout`、`ThrottlingError`、`PreflightError`、`SchemaValidationError`、`ScannedPdfError`、`DocumentLoadError`
    - `src/petition_ai/core/logging.py`：logging filter，於輸出前對訊息執行殘留掃描並遮蔽命中內容。掃描函式以可注入 callable 表示，避免與 `ingest` 套件循環相依
    - _Requirements: 2.6, 2.14, 10.5, 12.4_

  - [ ] 1.5 實作前置檢查腳本 `scripts/preflight.py`
    - 逐一驗證設定檔中每個 model_id 之可用性，並查詢兩個 Knowledge Base 狀態
    - 無可用生成模型時回報「僅檢索模式」旗標，供 `build_container()` 停用草稿生成
    - 嵌入模型不可用時回報僅本機模式
    - 輸出人類可讀之檢查結果與取得存取權之後續指引
    - _Requirements: 12.7, 12.8_

  - [ ] 1.6 P0 驗證與 commit
    - 驗證：`python -c "import petition_ai.app"` 可匯入；`git check-ignore` 確認 `.env` 被忽略而 `.kiro/specs` 未被忽略；`scripts/preflight.py` 可執行並輸出檢查結果
    - 僅 stage 本階段相關檔案，確認無任何憑證進入版控
    - 建立 commit：`chore: 建立專案骨架與設定管理`
    - _Requirements: 14.2, 14.3, 14.4, 14.7_

- [ ] 2. P1 文件載入與個資去識別化強制閘門
  - 本階段為所有 AWS 出口之合規前提。未完成並人工驗證前不得執行 P3 及其後任務
  - [ ] 2.1 建立資料模型與列舉 `src/petition_ai/models/`
    - `enums.py`：`CaseType`、`DocKind`、`EffectiveStatus`、`FeedbackAction`、`CitationStatus`
    - `documents.py`：`TextSpan`、`SourceDocument`、`PIIFinding`、`RedactionMap`、`RedactedDocument`
    - `case.py`：`Petitioner`、`OriginalDisposition`、`PetitionGround`、`Issue`、`CaseFacts`、`Classification`、`ExtractedCase`
    - `retrieval.py`：`FreshnessFlag`、`LawCitation`、`ReasoningOutline`、`SimilarityBreakdown`、`PrecedentMatch`
    - `draft.py`：`DecisionTemplate`、`DraftSection`、`DecisionDraft`、`CitationIssue`、`VerificationReport`
    - `feedback.py`：`FeedbackEvent`、`PreferenceWeight`、`Exemplar`、`OptimizationMetrics`
    - 全部採 frozen dataclass（`PreferenceWeight` 除外），並實作 design.md 所列驗證規則
    - _Requirements: 2.8, 3.1, 5.3, 6.4, 7.1, 9.1_

  - [ ] 2.2 實作 `src/petition_ai/ingest/loader.py`
    - 支援 `.pdf`（pypdf）、`.docx`（python-docx）、`.txt`（UTF-8 優先、Big5 次之自動偵測）
    - 保留 `page_no` 與 `paragraph_index`，使 `paragraphs` 與 `page_of_paragraph` 元素數相等且頁碼為非遞減序列
    - 無文字層時拋出 `ScannedPdfError` 並指明檔名；副檔名非白名單時拒絕
    - 多檔上傳依清單順序合併為單一 `SourceDocument`，頁碼與段落索引維持連續對應
    - 受密碼保護、檔案損毀、編碼無法辨識時分類回報錯誤，其餘檔案照常回傳
    - 純本機處理，不發出任何網路請求
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [ ] 2.3 實作 `src/petition_ai/ingest/detectors.py`
    - 11 類偵測器：身分證統一編號、營利事業統一編號、居留證號、市內電話、行動電話、地址、電子郵件、車牌號碼、金融帳號、案號、人名
    - 人名以「訴願人／代理人／代表人」上下文樣式搭配中文姓名字典輔助
    - 每一命中輸出個資類型、段落索引、字元起訖位置與信賴度
    - `make_alias` 產生符合 `^【[\u4e00-\u9fa5]+[A-Z]\d*】$` 之代號，同案件內序號自 1 起遞增且不重用
    - 本機補標規則庫：承辦人員手動補標之樣式可登錄並於後續案件自動命中，另備誤遮蔽排除清單
    - _Requirements: 2.2, 2.3, 2.15_

  - [ ] 2.4 實作 `src/petition_ai/ingest/redactor.py`
    - `redact`：逐段偵測，命中依 `char_start` **由後往前**替換以避免位移失效；同一實體映射同一代號；維持 mapping 單射
    - 重疊命中時保留覆蓋字元數最多者，相同時依固定類型優先序取一
    - `scan_residual`：對替換後全文掃描並回傳命中清單；`redact` 完成後掃描非空即拋 `ResidualPIIError` 中止，不外送任何位元組，且錯誤內容不含命中原文
    - 段落數與 `page_of_paragraph` 與輸入一致
    - `RedactionMap` 以 AES-GCM 加密後僅寫入 `./.local/redaction/`，金鑰由本機口令衍生
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.8, 2.10, 2.11_

  - [ ] 2.5 實作 `src/petition_ai/ingest/rehydrator.py`
    - 於呈現階段以本機 `RedactionMap` 將代號還原為原文，支援 `RedactedDocument` 與 `DecisionDraft`
    - 還原結果不寫入任何伺服端日誌，亦不送往任何 AWS 呼叫
    - 口令錯誤時中止還原並保留代號顯示狀態
    - _Requirements: 2.9, 2.12_

  - [ ] 2.6 P1 端到端驗證與 commit
    - 以程式生成之假樣本訴願書（含 11 類個資樣式）執行完整流程
    - 確認：代號化結果正確且同一實體共用代號、殘留掃描回報為空、對照表可完整還原為原文、加密檔案寫入 `./.local/redaction/`
    - 另以刻意留下殘留個資之樣本確認 `ResidualPIIError` 中止行為與命中位置報告
    - 僅 stage 本階段相關檔案，建立 commit：`feat: 實作個資去識別化強制閘門`
    - _Requirements: 2.5, 2.6, 2.7, 14.2, 14.3, 14.4_

- [ ] 3. P2 Bedrock 速率閘門與統一出口
  - [ ] 3.1 實作 `src/petition_ai/core/rate_limit.py`
    - `TokenBucketRateLimiter`：`capacity=1`、`refill_interval=1.05`（5% 安全邊際），以 `threading.Lock` 保護
    - 等待迴圈於**未持有鎖**之狀態下分段睡眠，單次不超過 0.25 秒，避免封鎖 Gradio 其他事件執行緒
    - 逾時拋出 `RateLimitTimeout` 且不消耗 token；`timeout_s` 預設 120 秒
    - _Requirements: 12.1, 12.3, 12.4_

  - [ ] 3.2 實作 `src/petition_ai/core/bedrock_gateway.py`
    - 唯一持有 `bedrock-runtime` 與 `bedrock-agent-runtime` boto3 client 之處
    - `retrieve`：以 `(kb_id, query, metadata_filter, top_k)` 雜湊為鍵之工作階段內快取，**快取層置於速率閘門之前**，命中不消耗速率預算
    - `converse_json`：以 `toolConfig` 與 `toolChoice` 強制結構化輸出，`temperature=0.2`、`maxTokens=4096`
    - 以 tenacity 對 `ThrottlingException`、`ServiceUnavailableException` 指數退避加 jitter，初始 1.0 秒、上限 30.0 秒、總嘗試次數上限 5 次；每次重試前重新取得 token
    - 型別約束：接受案件內容之參數僅允許來自 `RedactedDocument` 之文字
    - 記錄每案件累計 Bedrock 呼叫次數供效能預算檢視
    - _Requirements: 5.11, 7.12, 10.7, 12.2, 12.5, 12.6, 12.9_

  - [ ] 3.3 建立 `scripts/compliance_check.py`
    - 不使用 pytest，為可直接執行之檢查腳本，逐項輸出通過或失敗並以退出碼表示整體結果
    - 檢查 1：`.gitignore` 忽略 `.env`、`.env.*`、`.local/`、`inbox/`、`exports/`、`*.pem`、`__pycache__/`，且**不**忽略 `.kiro/`
    - 檢查 2：`infra/` 之 S3 Block Public Access 四項（`BlockPublicAcls`、`IgnorePublicAcls`、`BlockPublicPolicy`、`RestrictPublicBuckets`）皆為 true；無公開存取之 RDS／EMR；OpenSearch Serverless 為私有存取（此項於 P3 建立 `infra/` 後方會有實質內容）
    - 檢查 3：以 AST 掃描 `src/`，斷言 `boto3.client("bedrock-runtime")` 與 `boto3.client("bedrock-agent-runtime")` 僅出現於 `BedrockGateway`
    - 檢查 4：設定之部署區域為 `us-east-1` 或 `us-west-2`
    - 檢查 5：僅設定兩個必要之 Bedrock model id（一個嵌入、一個生成）
    - _Requirements: 12.2, 13.1, 13.3, 13.4, 13.7, 13.9, 13.10, 13.11_

  - [ ] 3.4 P2 驗證與 commit
    - 驗證：以多執行緒連續取用 `RateLimiter` 並列印授權時間戳，確認任意 1 秒窗內不超過 1 次
    - 驗證：重複相同 `retrieve` 參數，確認第二次命中快取且未新增請求
    - 執行 `scripts/compliance_check.py` 之檢查 3（AST 無旁路），確認通過
    - 僅 stage 本階段相關檔案，建立 commit：`feat: 實作 Bedrock 速率閘門與統一出口`
    - _Requirements: 12.1, 12.2, 14.2, 14.3, 14.4_

- [ ] 4. P3 S3 上傳與 Knowledge Base 建置
  - 前置條件：P1 之去識別化閘門已完成並通過端到端驗證。此為競賽規範第 2 條之合規閘門，不得提前執行
  - [ ] 4.1 決定向量儲存後端並記錄決策
    - 比較 OpenSearch Serverless 與 S3 Vectors：OpenSearch Serverless 有最低 OCU 費用且佈建較慢，S3 Vectors 成本與佈建時間較低
    - 依黑客松時程與成本選定其一，將決策與理由記錄於 `infra/README.md`
    - 將選定結果反映至 `AppConfig` 與後續 `infra/` 定義
    - _Requirements: 13.4_

  - [ ] 4.2 實作 `src/petition_ai/ingest/kb_sync.py`
    - 本機 metadata 驗證器：檢查 `.metadata.json` 可解析且必要欄位齊備（`doc_kind`、`effective_status`、`last_amended_date`、`applicable_case_types`／`case_type`、`issue_tags`、`cited_laws`），任一檔案未通過即中止上傳且送往 S3 之位元組數為 0
    - 上傳函式簽章僅接受 `RedactedDocument`，上傳前再次執行殘留掃描
    - 依 `law/` 與 `precedent/` 前綴寫入，套用 SSE-KMS
    - `StartIngestionJob` 觸發與 `GetIngestionJob` 以 5 秒間隔輪詢，不消耗 RateLimiter token；逾時回報失敗檔案清單與錯誤原因
    - _Requirements: 2.1, 2.11, 12.10, 12.11, 13.2_

  - [ ] 4.3 建立基礎設施定義 `infra/`
    - S3：帳戶層級與 bucket 層級 Block Public Access 四項全開、SSE-KMS 客戶管理金鑰、版本控制、存取日誌寫入**獨立**日誌 bucket、bucket policy 明示 Deny 非預期 principal
    - 兩個獨立 Knowledge Base（法規庫指向 `law/`、先例庫指向 `precedent/`），向量後端依 4.1 之決策且採私有存取
    - IAM 最小權限政策：限定所需 model ARN、Knowledge Base ARN、S3 前綴
    - 部署區域由設定檔指定，限定 `us-east-1` 或 `us-west-2`
    - 不建立 RDS／EMR；不建立入向來源為 `0.0.0.0/0` 之 Security Group
    - _Requirements: 12.12, 13.1, 13.2, 13.3, 13.4, 13.8_

  - [ ] 4.4 實作 `scripts/build_law_corpus.py`
    - 產製法規庫與先例庫之 `.metadata.json`，填入 `effective_status`、`last_amended_date`、`issue_tags`、`cited_laws`、`case_number_alias`、`decision_date`
    - **先例決定書必須先過去識別化閘門**，案號一律代號化後方可產製
    - 產製後呼叫 4.2 之 metadata 驗證器確認格式
    - _Requirements: 2.1, 5.3, 6.9, 12.11_

  - [ ] 4.5 P3 驗證與 commit
    - 驗證：以去識別化後之樣本語料執行上傳與 ingestion，確認兩個 Knowledge Base 皆可回傳檢索結果
    - 執行 `scripts/compliance_check.py` 之檢查 2，確認 S3 無公開存取
    - 僅 stage 本階段相關檔案，建立 commit：`feat: 建置法規庫與先例庫 Knowledge Base`
    - _Requirements: 13.1, 14.2, 14.3, 14.4_

- [ ] 5. P4 案件資訊擷取與類型分類
  - [ ] 5.1 實作 `src/petition_ai/extraction/extractor.py`
    - `extract_facts`：以 `BedrockGateway.converse_json` 之 tool use 強制輸出符合 JSON schema 之 `CaseFacts`
    - 每一擷取欄位附 `source_span`，並驗證其 `paragraph_index` 指向存在之段落
    - 必要欄位缺漏時以修正提示重試 1 次，二次仍缺則標記「待人工填寫」並使其餘欄位照常回傳
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ] 5.2 實作 `src/petition_ai/extraction/classifier.py`
    - 規則式分類：洗錢防制法、廢棄物清理法、空氣污染防制法之法規名稱與處分機關關鍵字表，命中時 `method="rule"` 且不呼叫模型（1 RPS 限制下極為重要）
    - 規則無法判定時才呼叫生成模型 zero-shot 分類，`method="model"`
    - 產生 `confidence` 與 `rationale`；低於 0.7 時輸出需人工確認旗標
    - 多重類型命中時優先採用 `legal_basis` 所命中者
    - 關鍵字表提供可由回饋事件擴充之讀取介面（寫入於 P9 接線）
    - _Requirements: 3.4, 3.5, 3.6, 3.10_

  - [ ] 5.3 實作 `src/petition_ai/extraction/issues.py`
    - `Issue_Tag_Vocabulary` 受控詞彙表定義（涵蓋三大類案件並含保留詞彙「其他」）與標籤正規化
    - `extract_issues`：指派 `tag`、`statement`、`priority`（1 為最主要）、`related_ground_indices` 並驗證其對應存在之 `ground_index`
    - 模型未萃取出爭點時，退回以每一 `PetitionGround` 逐項作為爭點，保證清單至少 1 項
    - 標籤不在詞彙表內時指派為「其他」並標記待人工指派
    - 提供承辦人員修改後之爭點清單作為後續檢索與生成輸入之介面
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.7_

  - [ ] 5.4 P4 驗證與 commit
    - 驗證：以樣本案件執行，確認擷取欄位完整且 `source_span` 皆有效、三大類型規則分類命中且未呼叫模型、`confidence < 0.7` 時輸出人工確認旗標、爭點清單非空且標籤屬受控詞彙
    - 僅 stage 本階段相關檔案，建立 commit：`feat: 實作案件資訊擷取與類型分類`
    - _Requirements: 3.4, 3.6, 4.2, 14.2, 14.3, 14.4_

- [ ] 6. P5 智能法規推薦與時效標示
  - [ ] 6.1 實作 `src/petition_ai/retrieval/law_id.py` 與 `freshness.py`
    - `normalize_law_id`：處理全形與半形數字、「第27條」與「第 27 條」空白差異、「第 N 條之 M」、款項目次層級，輸出如 `廢棄物清理法#27#11`，並保證冪等 `f(f(x)) == f(x)`
    - `freshness.py`：依 KB metadata 之 `effective_status` 與 `last_amended_date` 產生 `FreshnessFlag`，比對 `disposition_date` 產生新舊法適用之 note；metadata 缺漏或值非預期時設為「未確認」並套用與非現行相同之懲罰
    - _Requirements: 5.3, 5.4, 8.10_

  - [ ] 6.2 實作融合排序 `src/petition_ai/retrieval/fusion.py`
    - `fuse_scores`：`α·kb_score + β·feedback_weight + γ·type_match_bonus − δ·staleness_penalty`，結果 clamp 至 [0.0, 1.0]
    - 純函式、對 `feedback_weight` 單調遞增；冷啟動中性值 0.5 時排序與純 `kb_score` 一致
    - `kb_score` 以保序方式正規化至 [0.0, 1.0]
    - 排序決定性：`final_score` 相同時依 `kb_score`、再依 `law_id` 字典序
    - _Requirements: 5.5, 5.6, 5.7_

  - [ ] 6.3 實作 `src/petition_ai/retrieval/legal_retriever.py`
    - `recommend`：呼叫 `BedrockGateway.retrieve`，metadata filter **於檢索階段**以 `notEquals` 排除 `已廢止`（而非事後過濾，避免 top_k 名額被無效條文佔用），並限定 `applicable_case_types`
    - 同一 `law_id` 多片段時保留 `kb_score` 最高者並合併 `matched_issue_ids`
    - 依 `final_score` 遞減排序且回傳元素數不超過 `top_k`；附 `source_uri` 與原文片段
    - 爭點數超過 3 時合併為單一加權查詢並以較大 `top_k` 取回，使法規檢索呼叫次數不超過 3 次
    - 檢索空結果時回傳空清單，不拋出例外
    - 偏好權重讀取介面先以中性 0.5 運作，P9 再接線
    - _Requirements: 5.1, 5.2, 5.8, 5.9, 5.10, 5.12_

  - [ ] 6.4 P5 驗證與 commit
    - 驗證：以樣本爭點執行，確認已廢止條文未出現於結果、非現行條文帶有時效標示與扣分、融合分數落於 [0, 1]、冷啟動時排序等同純 `kb_score`、空結果不拋例外
    - 僅 stage 本階段相關檔案，建立 commit：`feat: 實作智能法規推薦與時效標示`
    - _Requirements: 5.2, 5.5, 5.6, 5.9, 14.2, 14.3, 14.4_

- [ ] 7. P6 相似案例比對與論理架構萃取
  - [ ] 7.1 實作 `src/petition_ai/similarity/outline.py`
    - 以段落標題正規表示式辨識「主文」、「事實」、「理由」，輸出 `ReasoningOutline`
    - 容許全形與半形冒號、標題前後空白、數字或中文序號前綴等變體
    - 純字串處理，**Bedrock 呼叫次數為 0**（1 RPS 限制下能用字串處理解決的就不花一次呼叫）
    - 標題無法辨識時對應欄位輸出空值，仍保留該筆結果
    - _Requirements: 6.5_

  - [ ] 7.2 實作 `src/petition_ai/similarity/matcher.py`
    - `match`：以 `top_k=15` 取回候選，metadata filter 限定 `case_type`（`其他` 時不過濾）
    - 依 `document_id` 聚合片段，避免同一決定書佔滿名次，使回傳結果 `document_id` 互不重複
    - 計算 `SimilarityBreakdown`：`issue_overlap` 與 `law_overlap` 以 Jaccard、`semantic_score` 取群組最高分、`feedback_weight`（P9 前為中性 0.5），各分項落於 [0, 1]
    - 依 `final_score` 遞減排序，回傳不超過 `limit` 件且 `3 <= limit <= 5`；聚合後不足 3 件時回傳實際件數且不補足
    - 附 `case_number_alias`、`decision_date`、`cited_laws`、`source_uri`；空結果回傳空清單不拋例外
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6, 6.7, 6.9_

  - [ ] 7.3 P6 驗證與 commit
    - 驗證：以樣本案件執行，確認回傳 3 至 5 件且 `document_id` 不重複、相似度分項皆落於 [0, 1]、`outline` 萃取未產生 Bedrock 呼叫、空結果不拋例外
    - 僅 stage 本階段相關檔案，建立 commit：`feat: 實作相似案例比對`
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 14.2, 14.3, 14.4_

- [ ] 8. P7 決定書草稿生成與引用驗證
  - [ ] 8.1 建立 `src/petition_ai/drafting/templates/`
    - 洗錢防制法、廢棄物清理法、空氣污染防制法與「其他」四類之 `DecisionTemplate`
    - 含 `main_text_pattern`、`fact_section_guide`、`reasoning_section_guide`、`instruction_clause`
    - 教示規定依決定結果（駁回／撤銷原處分／不受理）分別備有定型文字
    - 提供 `for_case_type()` 查表函式，`其他` 或查無對應時退回通用模板
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ] 8.2 實作 `src/petition_ai/drafting/prompts.py`
    - `SYSTEM_FACTS_ONLY`（禁止引入外部資訊）、`SYSTEM_CITE_ONLY_PROVIDED`（僅可引用提供之法條）
    - `FACTS_SCHEMA`、`REASONING_SCHEMA` 之 tool schema 定義
    - few-shot 範例注入函式，依 `case_type` 與 `issue_tag` 取最多 3 筆（ExemplarPool 於 P9 接線，本階段以空清單運作並改用 `reasoning_section_guide`）
    - _Requirements: 7.6, 7.7_

  - [ ] 8.3 實作 `src/petition_ai/drafting/generator.py`
    - 依主文、事實欄、逐爭點理由欄、教示規定之順序**分段生成**（降低單次上下文長度、提高可控性、部分失敗可重試）
    - **主文與教示規定由模板逐字填入，不經模型生成**且 `generated=False`。此二者為高度定型之法定文字，任何幻覺皆為嚴重瑕疵
    - 主文結論以佔位標記表示，由承辦人員自駁回／撤銷原處分／不受理中選定；結論變更時教示規定隨之重填
    - 理由欄每一爭點產生 `section_id="reasoning:<issue_id>"`，僅提供該爭點對應之 `LawCitation` 作為可引用來源
    - `temperature=0.2`；schema 驗證失敗時以補齊缺漏欄位之修正提示重試 1 次，二次失敗標記「待人工填寫」並保留原始輸出
    - 重試達上限之段落標記 PENDING 並提供重新生成，其餘段落照常回傳
    - `DecisionDraft.disclaimer` 填入 AI 草稿聲明
    - _Requirements: 7.1, 7.4, 7.5, 7.8, 7.9, 7.11, 7.12_

  - [ ] 8.4 實作 `src/petition_ai/drafting/citation_guard.py`
    - 以正規表示式擷取草稿中 `generated=True` 段落之法規引用字串（含條、項、款、目、之 N、準用、函釋字號、判決字號）
    - 經 `normalize_law_id` 正規化後比對許可清單；未命中標記 `UNVERIFIED`，命中但非現行標記 `STALE`
    - `passed` 等於「全部引用皆為 VERIFIED」；每一引用以 `(section_id, 正規化字串)` 為單位恰出現 1 次
    - **不自動刪除可疑引用**，純函式不修改輸入草稿。法律文書之最終責任在人，系統靜默修改內容比明確標示風險更危險
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ] 8.5 P7 驗證與 commit
    - 驗證：以樣本案件生成草稿，確認段落順序正確、主文與教示規定與模板逐字相同且 `generated=False`、`instruction` 段落存在且非空、每一爭點各有理由欄段落
    - 驗證：刻意在草稿中植入不在許可清單之引用，確認被標記 `UNVERIFIED` 且草稿內容未被修改
    - 僅 stage 本階段相關檔案，建立 commit：`feat: 實作決定書草稿生成與引用驗證`
    - _Requirements: 7.4, 7.5, 8.3, 8.6, 14.2, 14.3, 14.4_

- [ ] 9. P8 Gradio 操作介面
  - [ ] 9.1 實作 `src/petition_ai/ui/main.py` 與 `components.py`
    - 以 `gr.Blocks` 建立「案件匯入」、「案件資訊」、「法規與案例」、「草稿」、「成效」共 5 個分頁骨架與 `gr.State`
    - 以 `server_name="127.0.0.1"`、`share=False` 啟動。**Gradio 本身無身分驗證機制，任何情況下不得將其埠開放至公網**
    - 上傳限制：副檔名白名單 `.pdf`／`.docx`／`.txt`、單檔大小上限、單次上傳檔案數與總量上限
    - `components.py`：`gr.Progress()` 逐階段更新處理狀態；法規推薦與相似案例結果先行顯示，草稿生成於背景排隊執行（1 RPS 下等待不可避免，讓承辦人員在等待期間有事可做）
    - 前置階段未完成之分頁元件為停用狀態並顯示待完成之前置階段
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ] 9.2 實作 `src/petition_ai/ui/tabs/import_tab.py`
    - 檔案上傳、去識別化結果預覽、殘留掃描報告（個資類型、頁碼、段落索引、信賴度、前後文）
    - 手動遮蔽介面：補標後重新執行去識別化與殘留掃描，並將補標樣式登錄至本機規則庫
    - 掃描影像、非白名單副檔名、超出大小上限之錯誤呈現
    - _Requirements: 1.3, 1.4, 2.7, 2.15, 11.11_

  - [ ] 9.3 實作 `src/petition_ai/ui/tabs/case_tab.py`
    - 擷取欄位表單支援就地修正；點選溯源標記定位並高亮 `source_span` 所指段落
    - `confidence < 0.7` 時以警示樣式呈現並要求確認或改選類型後方開放後續流程
    - 爭點清單依 `priority` 遞增顯示，標籤僅可自受控詞彙選擇，支援新增、刪除、修改
    - 欄位修正後將下游結果標記為失效
    - _Requirements: 3.6, 3.8, 3.9, 4.6, 4.7_

  - [ ] 9.4 實作 `src/petition_ai/ui/tabs/law_tab.py`
    - 左欄法規推薦：時效徽章（非現行以警示色並顯示 `effective_status` 與 `last_amended_date`）、採納／排除／標記不相關按鈕
    - 右欄相似案例：`SimilarityBreakdown` 四項分項數值與 `final_score`、`ReasoningOutline`、選用／排除按鈕
    - _Requirements: 5.4, 6.8_

  - [ ] 9.5 實作 `src/petition_ai/ui/tabs/draft_tab.py`
    - 分段可編輯草稿、每段 `generated` 標記與 `citation_refs`、`precedent_refs` 溯源標記
    - `UNVERIFIED` 紅框、`STALE` 黃框與側欄問題清單；三項處置操作（刪除引用／加入許可清單重新驗證／確認為正確引用）
    - PENDING 段落之重新生成按鈕，僅覆寫該段落
    - 主文結論選擇；仍含佔位標記時拒絕匯出
    - 匯出 DOCX 保留 AI 草稿聲明；匯出路徑正規化限定於 `./exports/` 內
    - 呈現與匯出前經 `Rehydrator` 還原代號，且還原內容不寫入伺服端日誌
    - _Requirements: 2.12, 7.8, 7.10, 8.7, 8.8, 11.9_

  - [ ] 9.6 實作工作階段持久化與 P8 驗證、commit
    - `src/petition_ai/ui/session.py`：以 `case_id` 為鍵將去識別化文件、擷取結果與草稿加密持久化於 `./.local/sessions/`，內容不含原文、對照表明文或已還原個資
    - 啟動時列出未完成案件之 `case_id`、最後更新時間與已完成階段供續作；載入加密案件時要求輸入本機金鑰口令
    - 驗證：啟動介面並以樣本案件走完匯入至匯出全流程；確認服務僅綁定 `127.0.0.1`、匯出路徑穿越被阻擋、重啟後可續作
    - 僅 stage 本階段相關檔案，建立 commit：`feat: 建立 Gradio 操作介面`
    - _Requirements: 11.6, 11.7, 11.8, 14.2, 14.3, 14.4_

- [ ] 10. P9 使用者回饋驅動之優化迴路
  - [ ] 10.1 實作 `src/petition_ai/feedback/store.py`
    - **以本機 SQLite 為主實作**（避免 AWS 佈建擋在關鍵路徑），DynamoDB 後端降為選用且以相同介面實作
    - 資料表：回饋事件、偏好權重、範例池、稽核軌跡
    - `has_event`／`mark_event` 支援 `event_id` 去重；`get_weight`／`put_weight`
    - _Requirements: 9.13, 13.6_

  - [ ] 10.2 實作 `src/petition_ai/feedback/preference.py`
    - `PreferenceModel.update`：EMA `w ← (1−η)·w + η·reward`，η = 0.2，結果 clamp 至 [0, 1]。選擇 EMA 而非訓練模型，符合競賽避免大規模訓練之限制且即時生效
    - `_reward_of`：採納／整段保留 → 1.0；排除／標記不相關／整段刪除 → 0.0；編輯 → `1 − edit_distance_ratio`
    - `weight()` 對未見過之 `(case_type, issue_tag, item_id)` 回傳中性值 0.5，不干擾原始 KB 排序
    - `sample_count` 每次更新恰增加 1；對相同 `event_id` 冪等
    - _Requirements: 9.8, 9.9, 9.10, 9.11, 9.12, 9.13, 9.14, 9.18_

  - [ ] 10.3 實作 `src/petition_ai/feedback/collector.py`
    - 明示訊號：`on_citation_action`、`on_precedent_action` 產生 `FeedbackEvent` 並寫入 `FeedbackStore`；承辦人員手動改選案件類型、將 `UNVERIFIED` 引用確認為正確引用時亦產生事件
    - `on_draft_finalize`：逐段比對生成草稿與定稿，以字元級編輯距離除以兩者字元數最大值計算 `edit_distance_ratio`
    - `ratio == 0.0` → 整段保留；定稿去空白後長度為 0 → 整段刪除；其餘 → 編輯
    - **生成段落之 `citation_refs` 法條若仍出現於定稿內容，產生該法條之正向訊號**。承辦人員不會逐一按採納鈕，但定稿本身誠實表達了哪些法條有用
    - 僅就 `generated == True` 之段落產生學習訊號；事件僅含代號與識別碼，寫入後逐筆套用 `PreferenceModel.update`
    - _Requirements: 3.7, 8.9, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.16, 9.17_

  - [ ] 10.4 實作 `src/petition_ai/feedback/exemplars.py`
    - `ExemplarPool.register`：`edit_distance_ratio` 不高於門檻之定稿段落登錄為候選範例，避免把壞範例餵回系統
    - 依 `case_type` 與 `issue_tag` 分群，保留最近 N 筆；`get(n=3)` 供提示詞注入
    - 範例摘要為去識別化內容
    - _Requirements: 7.7, 9.15_

  - [ ] 10.5 接線偏好權重與範例池
    - `LegalRetriever` 與 `PrecedentMatcher` 自 `FeedbackStore` 讀取權重並納入 `feedback_weight`；讀取失敗或逾時時退回中性 0.5 並維持流程
    - `DraftGenerator` 自 `ExemplarPool` 取得 few-shot 範例，取代 P7 之空清單
    - 於 `build_container()` 完成依賴注入
    - _Requirements: 7.7, 9.19_

  - [ ] 10.6 實作 `src/petition_ai/feedback/metrics.py` 與 `ui/tabs/metrics_tab.py`
    - 計算 `citation_accept_rate`、`precedent_accept_rate`、`mean_edit_distance_ratio`、`mean_time_to_finalize_s`、`case_count`
    - 稽核軌跡：被採納之建議識別碼、草稿修改差異、定稿操作者代號
    - 記錄單一案件實際 Bedrock 呼叫次數（讀取 `BedrockGateway` 計數器）與是否落於 7 至 10 次預算
    - `metrics_tab.py`：以趨勢圖呈現指定時間窗內之 `OptimizationMetrics`；樣本數不足時顯示提示而不呈現趨勢結論
    - _Requirements: 10.1, 10.2, 10.6, 10.7_

  - [ ] 10.7 實作 `scripts/replay_feedback.py` 與 P9 驗證、commit
    - 重放歷史回饋事件序列，比較啟用與停用回饋權重兩種設定下之 Recall@5 與 MRR 及其差值
    - 輸出同一 `case_type` 之 `mean_edit_distance_ratio` 移動平均趨勢
    - 驗證：對同一法條連續採納數次，確認權重上升且下次推薦排序提前；連續排除確認權重下降；重複套用同一 `event_id` 確認權重不變
    - 僅 stage 本階段相關檔案，建立 commit：`feat: 實作使用者回饋驅動之優化迴路`
    - _Requirements: 9.10, 9.11, 9.13, 10.3, 10.4, 14.2, 14.3, 14.4_

- [ ] 11. P10 合規檢核與交件收尾
  - [ ] 11.1 執行 `scripts/compliance_check.py` 並修正所有不符項
    - 五項檢查全數通過：`.gitignore` 保護與 `.kiro/` 未被忽略、S3 無公開存取、Bedrock 無旁路、部署區域、僅兩個模型存取權
    - 以 detect-secrets 掃描確認無憑證進入版控
    - 確認優化流程不含任何模型訓練或微調作業
    - _Requirements: 13.9, 13.10, 13.11, 13.12, 13.13_

  - [ ] 11.2 補齊 `README.md` 與部署說明
    - 環境變數清單、`scripts/preflight.py` 執行方式、Knowledge Base 建置步驟（`scripts/build_law_corpus.py` 與 `kb_sync`）、介面啟動指令、`scripts/compliance_check.py` 執行方式
    - 說明 `.kiro/` 納入版本控制之用途（競賽規範第 9 條展示 specs／hooks／steering）
    - 記載本次為本機執行版本；多人使用需置於 ALB 與身分提供者驗證之後並將 EC2 Security Group 入向來源限定為該 ALB，此部分為已記載未實作（需求 11.10 與 13.5）
    - 記載 CloudWatch 日誌與指標接線為選用後續事項
    - 確認不含任何真實憑證
    - _Requirements: 11.10, 13.5, 13.9_

  - [ ] 11.3 P10 收尾與 commit
    - 確認 `.kiro/` 及其 `specs`、`hooks`、`steering` 子目錄皆已納入版控且未被任何 git 排除規則匹配
    - 確認全部階段 commit 皆已建立
    - 僅 stage 本階段相關檔案，建立 commit：`chore: 完成部署設定與合規檢核`
    - _Requirements: 14.2, 14.3, 14.7_

## Notes

**備註**

- **測試與執行時功能之區別**：本計畫移除 pytest、Hypothesis 與覆蓋率門檻，但去識別化殘留掃描（`scan_residual`）與速率閘門（`TokenBucketRateLimiter`）皆為產品程式碼而非測試，必須完整實作。前者掃到殘留個資即中止流程，後者將 Bedrock 壓在每秒 1 請求以下，二者皆為競賽規範之直接要求。
- **合規檢查**：原四個 pytest 合規測試檔收斂為 `scripts/compliance_check.py` 一支腳本，交件前人工執行。此腳本於任務 3.3 建立，其中 S3 相關檢查於 P3 建立 `infra/` 後方有實質內容。
- **合規閘門排序**：P1 未完成並通過端到端驗證前，不得執行 P3 及其後任何會將案件內容上傳 S3 或送往 Bedrock／Knowledge Base 之任務。以型別系統輔助強制：AWS 出口函式僅接受 `RedactedDocument`。
- **驗證方式**：各階段以樣本案件執行真實流程之端到端手動驗證取代自動化斷言。樣本資料一律為程式生成之假資料，不得使用任何真實個人資料或真實案件內容。
- **commit 規則**：每一 P 階段之最後一個子任務即為該階段之 commit 任務，commit 訊息採 design.md 指定之文字。中間任務不建立 commit。每次僅 stage 該階段相關檔案，不使用 `git add .`。
- **階段依賴**：P0 → P1、P0 → P2、P1 → P3、P2 → P3、P3 → P4、P4 → P5、P4 → P6、P5 → P7、P6 → P7、P7 → P8、P8 → P9、P9 → P10。P1 與 P2 可並行，P5 與 P6 可並行。
- **黑客松取捨**：回饋儲存以本機 SQLite 為主實作（DynamoDB 選用）；向量後端於 P3 開頭明確決策（OpenSearch Serverless 有最低 OCU 費用且佈建較慢，S3 Vectors 為較省較快之替代）；部署維持本機執行，ALB + Cognito 多人部署與 CloudWatch 接線移出關鍵路徑。
- **design.md 之 Testing Strategy 與 23 條正確性性質原樣保留**，作為日後強化之參考基準，本次不實作。

## Task Dependency Graph

**任務依賴關係圖**

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4"] },
    { "id": 2, "tasks": ["1.5"] },
    { "id": 3, "tasks": ["1.6"] },
    { "id": 4, "tasks": ["2.1"] },
    { "id": 5, "tasks": ["2.2", "2.3", "3.1"] },
    { "id": 6, "tasks": ["2.4", "3.2"] },
    { "id": 7, "tasks": ["2.5", "3.3"] },
    { "id": 8, "tasks": ["2.6", "3.4"] },
    { "id": 9, "tasks": ["4.1"] },
    { "id": 10, "tasks": ["4.2", "4.3"] },
    { "id": 11, "tasks": ["4.4"] },
    { "id": 12, "tasks": ["4.5"] },
    { "id": 13, "tasks": ["5.1", "5.2", "5.3"] },
    { "id": 14, "tasks": ["5.4"] },
    { "id": 15, "tasks": ["6.1", "7.1"] },
    { "id": 16, "tasks": ["6.2", "7.2"] },
    { "id": 17, "tasks": ["6.3"] },
    { "id": 18, "tasks": ["6.4", "7.3"] },
    { "id": 19, "tasks": ["8.1", "8.2"] },
    { "id": 20, "tasks": ["8.3", "8.4"] },
    { "id": 21, "tasks": ["8.5"] },
    { "id": 22, "tasks": ["9.1"] },
    { "id": 23, "tasks": ["9.2", "9.3", "9.4", "9.5"] },
    { "id": 24, "tasks": ["9.6"] },
    { "id": 25, "tasks": ["10.1"] },
    { "id": 26, "tasks": ["10.2", "10.3"] },
    { "id": 27, "tasks": ["10.4"] },
    { "id": 28, "tasks": ["10.5", "10.6"] },
    { "id": 29, "tasks": ["10.7"] },
    { "id": 30, "tasks": ["11.1", "11.2"] },
    { "id": 31, "tasks": ["11.3"] }
  ]
}
```
