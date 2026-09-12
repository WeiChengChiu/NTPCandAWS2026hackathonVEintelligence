# Implementation Plan

**實作計畫：訴願決定書 AI 輔助撰擬系統**

## Overview

**概觀**

本計畫依 design.md 之階段規劃（P0–P10）展開為可執行之編碼任務。實作語言為 Python 3.12（設計文件已明確以 Python 表述全部演算法與資料模型），測試框架為 pytest 搭配 Hypothesis 進行 property-based 測試。

三項貫穿全計畫之硬性約束：

第一，**去識別化為架構閘門**。P1（文件載入與 PIIRedactor）之 Property 1–4、19–21 測試必須全數通過，方可執行 P3 及其後任何會將案件內容寫入 S3 或送往 Bedrock／Knowledge Base 之任務。此為競賽規範第 2 條之合規要求，非實作偏好。

第二，**每一階段完成即建立一次 git commit**。每個 P 階段之最後一個子任務即為「執行該階段測試 → 確認完成條件 → 建立 commit」，並使用 design.md 指定之 commit 訊息。

第三，**Bedrock 呼叫一律經 BedrockGateway**。P2 完成後，任何新增之 Bedrock 或 Knowledge Base 呼叫皆不得直接建立 boto3 client。

## Tasks

- [ ] 1. P0 專案骨架與設定管理
  - [ ] 1.1 建立專案目錄結構與套件骨架
    - 建立 `src/petition_ai/` 及其子套件 `core/`、`models/`、`ingest/`、`extraction/`、`retrieval/`、`similarity/`、`drafting/`、`feedback/`、`ui/`，各含 `__init__.py`
    - 建立 `src/petition_ai/app.py` 之 `build_container()` 空骨架與依賴組裝介面簽章
    - 建立 `tests/unit/`、`tests/property/`、`tests/compliance/`、`tests/fixtures/`、`infra/`、`scripts/` 目錄與 `conftest.py`
    - 建立 `pyproject.toml`（ruff、mypy、pytest 設定，`--cov` 門檻 80%）
    - _Requirements: 14.1_

  - [ ] 1.2 建立 `.gitignore` 與 `.env.example`
    - `.gitignore` 必須包含 `.env`、`.env.*`、`.local/`、`inbox/`、`exports/`、`*.pem`、`__pycache__/`
    - `.gitignore` 必須不匹配 `.kiro/` 或其任何子目錄（競賽規範第 9 條要求展示 specs／hooks／steering）
    - `.env.example` 列出所有設定鍵名但不含任何真實憑證或 model_id
    - _Requirements: 13.9, 13.10_

  - [ ] 1.3 建立相依套件鎖定檔
    - `requirements.txt`：boto3、gradio、pydantic、pydantic-settings、pypdf、python-docx、tenacity、orjson、cryptography、charset-normalizer，全部鎖定版本
    - `requirements-dev.txt`：pytest、pytest-cov、hypothesis、ruff、mypy、detect-secrets、moto，全部鎖定版本
    - _Requirements: 14.8, 14.9_

  - [ ] 1.4 實作設定管理 `src/petition_ai/core/config.py`
    - 以 pydantic-settings 定義 `AppConfig`：region（僅允許 `us-east-1` 或 `us-west-2`）、embedding_model_id、generation_model_id、law_kb_id、precedent_kb_id、s3_bucket、ddb 表名
    - 定義 `FusionWeights`（alpha／beta／gamma 和為 1.0、delta ∈ [0,1]）與 `SimilarityWeights` 之驗證器
    - 定義 learning_rate 預設 0.2、exemplar_threshold、rate_limit refill_interval 預設 1.05
    - 記錄使用中之 EC2／SageMaker 執行個體清單欄位
    - _Requirements: 12.12, 13.3, 13.7, 13.14_

  - [ ] 1.5 實作例外型別與日誌遮蔽
    - `src/petition_ai/core/errors.py`：`ResidualPIIError`、`RateLimitTimeout`、`ThrottlingError`、`PreflightError`、`SchemaValidationError`、`ScannedPdfError`
    - `src/petition_ai/core/logging.py`：logging filter，於輸出前對訊息執行殘留掃描並遮蔽命中內容（掃描函式以可注入 callable 表示，避免與 ingest 套件循環相依）
    - _Requirements: 2.6, 2.14, 10.5, 12.4, 12.5_

  - [ ] 1.6 實作前置檢查腳本 `scripts/preflight.py`
    - 逐一驗證設定檔中每個 model_id 之可用性，並查詢兩個 Knowledge Base 狀態
    - 無可用生成模型時回報「僅檢索模式」旗標，供 `build_container()` 停用草稿生成
    - 輸出人類可讀之檢查結果與後續指引
    - _Requirements: 12.7, 12.8_

  - [ ]* 1.7 撰寫 P0 單元測試
    - `tests/unit/test_config.py`：region 白名單、融合權重和為 1.0 之驗證失敗案例
    - `tests/unit/test_logging.py`：含個資之日誌訊息輸出後不含原文
    - `tests/unit/test_preflight.py`：以測試替身模擬模型不可用，斷言回傳僅檢索模式
    - _Requirements: 2.14, 12.7, 12.8, 13.3_

  - [ ] 1.8 撰寫合規測試 `tests/compliance/test_gitignore_protects_secrets.py`
    - 斷言 `.env`、`.env.*`、`.local/`、`inbox/`、`exports/`、`*.pem` 皆被忽略
    - 斷言 `.kiro/` 及其子路徑未被忽略
    - _Requirements: 13.9, 13.10, 13.11_

  - [ ] 1.9 P0 收尾與 commit
    - 確認完成條件：`.kiro/` 未被忽略、`.env` 已被忽略、`scripts/preflight.py` 可執行
    - 確認所有測試通過，若有疑問請詢問使用者
    - 於同一 commit 內納入本階段實作與測試程式碼，建立 commit：`chore: 建立專案骨架與設定管理`
    - _Requirements: 14.2, 14.3, 14.4, 14.7_

- [ ] 2. P1 文件載入與個資去識別化強制閘門
  - 本階段為所有後續階段之合規前提，其 property 測試未通過前不得執行 P3 及其後任務
  - [ ] 2.1 建立資料模型與列舉 `src/petition_ai/models/`
    - `enums.py`：`CaseType`、`DocKind`、`EffectiveStatus`、`FeedbackAction`、`CitationStatus`
    - `documents.py`：`TextSpan`、`SourceDocument`、`PIIFinding`、`RedactionMap`、`RedactedDocument`
    - `case.py`：`Petitioner`、`OriginalDisposition`、`PetitionGround`、`Issue`、`CaseFacts`、`Classification`、`ExtractedCase`
    - `retrieval.py`：`FreshnessFlag`、`LawCitation`、`ReasoningOutline`、`SimilarityBreakdown`、`PrecedentMatch`
    - `draft.py`：`DecisionTemplate`、`DraftSection`、`DecisionDraft`、`CitationIssue`、`VerificationReport`
    - `feedback.py`：`FeedbackEvent`、`PreferenceWeight`、`Exemplar`、`OptimizationMetrics`
    - 全部採 frozen dataclass（`PreferenceWeight` 除外），並實作設計文件所列驗證規則
    - _Requirements: 2.8, 3.1, 5.3, 6.4, 7.1, 9.1_

  - [ ] 2.2 實作 `src/petition_ai/ingest/loader.py`
    - 支援 `.pdf`（pypdf）、`.docx`（python-docx）、`.txt`（UTF-8／Big5 自動偵測）
    - 保留 `page_no` 與 `paragraph_index`，使 `paragraphs` 與 `page_of_paragraph` 元素數相等
    - 無文字層時拋出 `ScannedPdfError`；副檔名非白名單時拒絕
    - 多檔上傳依順序合併為單一 `SourceDocument`；長文件以段落批次串流處理
    - 純本機處理，不發出任何網路請求
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [ ]* 2.3 撰寫 DocumentLoader 單元測試
    - Big5 與 UTF-8 解碼、空文字層錯誤、副檔名白名單拒絕、多檔合併後頁碼連續性
    - 以 spy 斷言載入過程網路請求數為 0
    - _Requirements: 1.2, 1.3, 1.4, 1.6, 1.7_

  - [ ] 2.4 實作 `src/petition_ai/ingest/detectors.py`
    - 11 類偵測器：身分證統一編號、營利事業統一編號、居留證號、市內電話、行動電話、地址、電子郵件、車牌號碼、金融帳號、案號、人名
    - 人名以「訴願人／代理人／代表人」上下文樣式搭配中文姓名字典輔助
    - `make_alias` 產生符合 `^【[\u4e00-\u9fa5]+[A-Z]\d*】$` 之代號
    - 本機規則庫：承辦人員手動補標之樣式可登錄並於後續案件自動命中
    - _Requirements: 2.2, 2.3, 2.15_

  - [ ] 2.5 實作 `src/petition_ai/ingest/redactor.py`
    - `redact`：逐段偵測、命中依 `char_start` 由後往前替換、同一實體映射同一代號、維持 mapping 單射
    - `scan_residual`：對替換後全文掃描，回傳命中清單；`redact` 完成後掃描非空即拋 `ResidualPIIError` 並中止，不外送任何位元組
    - 段落數與 `page_of_paragraph` 與輸入一致
    - `RedactionMap` 以 AES-GCM 加密後僅寫入 `./.local/redaction/`
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.8, 2.10, 2.11_

  - [ ] 2.6 實作 `src/petition_ai/ingest/rehydrator.py`
    - 於呈現階段以本機 `RedactionMap` 將代號還原為原文，支援 `RedactedDocument` 與 `DecisionDraft`
    - 還原結果不寫入任何伺服端日誌
    - _Requirements: 2.9, 2.12_

  - [ ]* 2.7 撰寫去識別化模組單元測試（要求 100% 分支覆蓋）
    - 各類個資樣式命中、重疊命中、由後往前替換之位移正確性、代號穩定性
    - 殘留掃描未通過時之中止行為與命中位置回報
    - AES-GCM 加密寫入路徑與金鑰口令解密
    - _Requirements: 2.2, 2.5, 2.6, 2.10, 14.8_

  - [ ]* 2.8 撰寫 Property 1 測試
    - **Property 1：去識別化完備性**
    - 以 Hypothesis 自訂策略 `chinese_paragraph_strategy()` 產生混入個資樣式之中文段落（測試資料為程式生成之假資料）
    - **Validates: Requirements 2.5, 2.6**
    - _Requirements: 2.5, 2.6_
    - _Property: 1_

  - [ ]* 2.9 撰寫 Property 2 測試
    - **Property 2：去識別化可逆性**
    - 斷言 `restore(r, m) == d`，並以 `RuleBasedStateMachine` 驗證多文件累積下代號穩定性
    - **Validates: Requirements 2.9, 2.12**
    - _Requirements: 2.9, 2.12_
    - _Property: 2_

  - [ ]* 2.10 撰寫 Property 3 測試
    - **Property 3：代號單射性**
    - 斷言 `len(set(m.mapping.values())) == len(m.mapping)` 且代號格式符合正規表示式
    - **Validates: Requirements 2.3, 2.4**
    - _Requirements: 2.3, 2.4_
    - _Property: 3_

  - [ ]* 2.11 撰寫 Property 4 測試
    - **Property 4：段落結構保持**
    - 斷言段落數不變且 `page_of_paragraph` 逐元素相等
    - **Validates: Requirements 1.5, 2.8**
    - _Requirements: 1.5, 2.8_
    - _Property: 4_

  - [ ] 2.12 撰寫合規測試 `tests/compliance/test_no_pii_leaves_local.py`
    - **Property 19：AWS 側無個資**
    - 以 spy 攔截全部 boto3 呼叫，對每個 payload 斷言 `scan_residual(payload) == []`
    - **Validates: Requirements 2.1, 2.11**
    - _Requirements: 2.1, 2.11_
    - _Property: 19_

  - [ ] 2.13 撰寫合規測試 `tests/compliance/test_redaction_map_never_serialized.py`
    - **Property 20：對照表不外送**
    - 以測試替身斷言 `RedactionMap` 型別不出現於任何 AWS SDK 呼叫參數，違反時回報呼叫位置
    - **Validates: Requirements 2.10, 2.13**
    - _Requirements: 2.10, 2.13_
    - _Property: 20_

  - [ ]* 2.14 撰寫 Property 21 測試
    - **Property 21：回饋事件無個資**
    - 以隨機 `FeedbackEvent` 序列化後斷言 `scan_residual(serialize(e)) == []`
    - **Validates: Requirements 9.16**
    - _Requirements: 9.16_
    - _Property: 21_

  - [ ] 2.15 P1 收尾與 commit
    - 確認完成條件：Property 1、2、3、4、19、20、21 測試全數通過；去識別化模組達 100% 分支覆蓋
    - 確認所有測試通過，若有疑問請詢問使用者
    - 於同一 commit 內納入本階段實作與測試程式碼，建立 commit：`feat: 實作個資去識別化強制閘門`
    - _Requirements: 14.2, 14.3, 14.4, 14.8_

- [ ] 3. P2 Bedrock 速率閘門與統一出口
  - [ ] 3.1 實作 `src/petition_ai/core/rate_limit.py`
    - `TokenBucketRateLimiter`：`capacity=1`、`refill_interval=1.05`，以 `threading.Lock` 保護
    - 等待迴圈於未持有鎖之狀態下分段睡眠，單次不超過 0.25 秒
    - 逾時拋出 `RateLimitTimeout` 且不消耗 token
    - _Requirements: 12.1, 12.3, 12.4_

  - [ ]* 3.2 撰寫 RateLimiter 單元測試（要求 100% 分支覆蓋）
    - 逾時行為、token 不變式 `0 <= tokens <= capacity`、睡眠發生於鎖外
    - _Requirements: 12.3, 12.4, 14.8_

  - [ ]* 3.3 撰寫 Property 5 測試
    - **Property 5：速率上界**
    - 多執行緒並發取用，斷言授權時間戳集合中任意 1 秒滑動窗內元素數 ≤ 1
    - **Validates: Requirements 12.1**
    - _Requirements: 12.1_
    - _Property: 5_

  - [ ] 3.4 實作 `src/petition_ai/core/bedrock_gateway.py`
    - 唯一持有 `bedrock-runtime` 與 `bedrock-agent-runtime` boto3 client 之處
    - `retrieve`：以 `(kb_id, query, metadata_filter, top_k)` 雜湊為鍵之工作階段內快取，快取命中不消耗速率預算
    - `converse_json`：以 `toolConfig` 與 `toolChoice` 強制結構化輸出，`temperature=0.2`、`maxTokens=4096`
    - 以 tenacity 對 `ThrottlingException`、`ServiceUnavailableException` 指數退避加 jitter，重試上限 5 次；達上限則回報可標記 PENDING 之錯誤
    - 型別約束：接受案件內容之參數型別僅允許 `RedactedDocument` 衍生之文字，不接受 `SourceDocument`
    - 記錄每案件累計 Bedrock 呼叫次數供效能預算檢視
    - _Requirements: 5.11, 7.12, 10.7, 12.2, 12.5, 12.6, 12.9_

  - [ ]* 3.5 撰寫 BedrockGateway 單元測試
    - 以 `botocore.stub.Stubber` 驗證重複 `retrieve` 命中快取且新增請求數為 0
    - 節流重試次數上限與退避行為；達上限後之錯誤型別
    - 呼叫次數計數器正確累加
    - _Requirements: 5.11, 10.7, 12.5, 12.6_

  - [ ] 3.6 撰寫無旁路檢查測試 `tests/compliance/test_no_bedrock_bypass.py`
    - **Property 6：無旁路**
    - 以 AST 靜態掃描 `src/` 全部模組，斷言 `boto3.client("bedrock-runtime")` 與 `boto3.client("bedrock-agent-runtime")` 僅出現於 `BedrockGateway.__init__`
    - **Validates: Requirements 12.2**
    - _Requirements: 12.2_
    - _Property: 6_

  - [ ] 3.7 P2 收尾與 commit
    - 確認完成條件：Property 5、6 測試通過；速率限制模組達 100% 分支覆蓋
    - 確認所有測試通過，若有疑問請詢問使用者
    - 於同一 commit 內納入本階段實作與測試程式碼，建立 commit：`feat: 實作 Bedrock 速率閘門與統一出口`
    - _Requirements: 14.2, 14.3, 14.4, 14.8_

- [ ] 4. P3 S3 上傳與 Knowledge Base 建置
  - 前置條件：P1 之 Property 1–4、19–21 與 P2 之 Property 5–6 皆已通過。此為合規閘門，不得提前執行
  - [ ] 4.1 實作 `src/petition_ai/ingest/kb_sync.py` 之 metadata 驗證與 S3 上傳
    - 本機 metadata 驗證器：檢查 `.metadata.json` 之格式與必要欄位（`doc_kind`、`effective_status`、`last_amended_date`、`applicable_case_types`／`case_type`、`issue_tags`、`cited_laws`）
    - 上傳函式簽章僅接受 `RedactedDocument`，上傳前再次執行殘留掃描
    - 依 `law/` 與 `precedent/` 前綴寫入，套用 SSE-KMS
    - _Requirements: 2.1, 2.11, 12.11, 13.2_

  - [ ] 4.2 實作 KB ingestion 作業與輪詢
    - `StartIngestionJob` 觸發與 `GetIngestionJob` 以 5 秒間隔輪詢
    - 逾時回報失敗檔案清單與錯誤原因（metadata 格式、編碼問題）
    - _Requirements: 12.10_

  - [ ] 4.3 建立基礎設施定義 `infra/`
    - S3：帳戶層級與 bucket 層級 Block Public Access 四項全開、SSE-KMS 客戶管理金鑰、版本控制、存取日誌、bucket policy 明示 Deny 非預期 principal
    - 兩個獨立 Knowledge Base（法規庫指向 `law/`、先例庫指向 `precedent/`），向量後端為 OpenSearch Serverless 且採私有網路存取
    - DynamoDB 表：回饋事件、偏好權重、範例池
    - IAM 最小權限政策：限定 model ARN、KB ARN、S3 前綴與 DynamoDB 表
    - 部署區域由設定檔指定，限定 `us-east-1` 或 `us-west-2`
    - _Requirements: 12.12, 13.1, 13.2, 13.3, 13.4, 13.6, 13.8_

  - [ ] 4.4 實作 `scripts/build_law_corpus.py`
    - 產製法規庫與先例庫之 `.metadata.json`，填入 `effective_status`、`last_amended_date`、`issue_tags`、`cited_laws`、`case_number_alias`、`decision_date`
    - 產製前對先例決定書執行去識別化閘門，案號一律代號化
    - 產製後呼叫 4.1 之 metadata 驗證器
    - _Requirements: 2.1, 5.3, 6.9, 12.11_

  - [ ] 4.5 撰寫合規測試 `tests/compliance/test_no_public_s3.py`
    - 斷言 `infra/` 設定中 `BlockPublicAcls`、`IgnorePublicAcls`、`BlockPublicPolicy`、`RestrictPublicBuckets` 四項皆為 `true`
    - 斷言未使用啟用公開存取之 RDS 或 EMR 資源、OpenSearch Serverless 為私有存取
    - _Requirements: 13.1, 13.4, 13.11_

  - [ ]* 4.6 撰寫 KBSync 單元測試
    - 以 moto／Stubber 驗證 metadata 缺欄位時拒絕上傳、輪詢逾時回報失敗清單
    - 斷言傳入 `SourceDocument` 時型別檢查失敗
    - _Requirements: 12.10, 12.11_

  - [ ] 4.7 P3 收尾與 commit
    - 確認完成條件：兩個 Knowledge Base 可檢索、無任何公開存取設定、合規測試通過
    - 確認所有測試通過，若有疑問請詢問使用者
    - 於同一 commit 內納入本階段實作與測試程式碼，建立 commit：`feat: 建置法規庫與先例庫 Knowledge Base`
    - _Requirements: 14.2, 14.3, 14.4_

- [ ] 5. P4 案件資訊擷取與類型分類
  - [ ] 5.1 實作 `src/petition_ai/extraction/extractor.py`
    - `extract_facts`：以 `BedrockGateway.converse_json` 之 tool use 強制輸出符合 JSON schema 之 `CaseFacts`
    - 每一擷取欄位附 `source_span`，並驗證其 `paragraph_index` 指向存在之段落
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ] 5.2 實作 `src/petition_ai/extraction/classifier.py`
    - 規則式分類：洗錢防制法、廢棄物清理法、空氣污染防制法之法規名稱與處分機關關鍵字表，命中時 `method="rule"`
    - 規則無法判定時呼叫生成模型 zero-shot 分類，`method="model"`
    - 產生 `confidence` 與 `rationale`；低於 0.7 時輸出需人工確認旗標
    - 關鍵字表可由回饋事件擴充（讀取介面預留，寫入於 P9 接線）
    - _Requirements: 3.4, 3.5, 3.6, 3.10_

  - [ ] 5.3 實作 `src/petition_ai/extraction/issues.py`
    - `Issue_Tag_Vocabulary` 受控詞彙表定義與標籤正規化
    - `extract_issues`：指派 `tag`、`statement`、`priority`（1 為最主要）、`related_ground_indices` 並驗證其對應存在之 `ground_index`
    - 模型未萃取出爭點時，退回以每一 `PetitionGround` 逐項作為爭點，保證清單至少 1 項
    - 提供承辦人員修改後之爭點清單作為後續檢索與生成輸入之介面
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.7_

  - [ ]* 5.4 撰寫擷取與分類單元測試
    - 規則命中三大類型、`confidence < 0.7` 之人工確認旗標、爭點空結果退回機制
    - `source_span` 指向不存在段落時之驗證失敗
    - 爭點標籤不在受控詞彙時之正規化或拒絕
    - _Requirements: 3.3, 3.4, 3.6, 4.2, 4.3, 4.5_

  - [ ] 5.5 P4 收尾與 commit
    - 確認完成條件：樣本案件擷取欄位完整且皆具有效 `source_span`、分類信賴度門檻生效、爭點清單非空
    - 確認所有測試通過，若有疑問請詢問使用者
    - 於同一 commit 內納入本階段實作與測試程式碼，建立 commit：`feat: 實作案件資訊擷取與類型分類`
    - _Requirements: 14.2, 14.3, 14.4_

- [ ] 6. P5 智能法規推薦與時效標示
  - [ ] 6.1 實作 `src/petition_ai/retrieval/law_id.py`
    - `normalize_law_id`：處理全形與半形數字、「第27條」與「第 27 條」等寫法、款項次層級，輸出如 `廢棄物清理法#27#11`
    - 保證冪等：`f(f(x)) == f(x)`
    - _Requirements: 8.10_

  - [ ]* 6.2 撰寫 `normalize_law_id` 單元測試
    - 全形半形、空白差異、款項次層級、冪等性 `f(f(x)) == f(x)`
    - _Requirements: 8.10_

  - [ ] 6.3 實作 `src/petition_ai/retrieval/freshness.py`
    - 依 KB metadata 之 `effective_status` 與 `last_amended_date` 產生 `FreshnessFlag`，含適用時點提示 note
    - 非「現行」者輸出 staleness 旗標供融合排序與 UI 標記使用
    - _Requirements: 5.3, 5.4_

  - [ ] 6.4 實作 `src/petition_ai/retrieval/legal_retriever.py`
    - `recommend`：呼叫 `BedrockGateway.retrieve`，metadata filter 於檢索階段以 `notEquals` 排除 `已廢止`，並限定 `applicable_case_types`
    - 同一 `law_id` 多片段時保留 `kb_score` 最高者並合併 `matched_issue_ids`
    - 依 `final_score` 遞減排序且回傳元素數不超過 `top_k`；附 `source_uri` 與原文片段
    - 爭點數超過 3 時合併為單一加權查詢並以較大 `top_k` 取回，使法規檢索呼叫次數不超過 3 次
    - 檢索空結果時回傳空清單，不拋出例外
    - _Requirements: 5.1, 5.2, 5.7, 5.8, 5.9, 5.10, 5.12_

  - [ ] 6.5 實作融合排序 `src/petition_ai/retrieval/fusion.py`
    - `fuse_scores`：`α·kb_score + β·feedback_weight + γ·type_match_bonus − δ·staleness_penalty`，結果 clamp 至 [0.0, 1.0]
    - 純函式、對 `feedback_weight` 單調遞增；冷啟動中性值 0.5 時排序與純 `kb_score` 一致
    - _Requirements: 5.4, 5.5, 5.6_

  - [ ]* 6.6 撰寫 Property 7 測試
    - **Property 7：融合分數有界**
    - 以 `law_citation_strategy()` 產生隨機分數與時效狀態組合，斷言回傳值 ∈ [0.0, 1.0]
    - **Validates: Requirements 5.5**
    - _Requirements: 5.5_
    - _Property: 7_

  - [ ]* 6.7 撰寫 Property 11 測試
    - **Property 11：冷啟動中性**
    - 全部項目 `feedback_weight == 0.5` 時，融合排序與純 `kb_score` 排序一致
    - **Validates: Requirements 5.6, 9.14**
    - _Requirements: 5.6, 9.14_
    - _Property: 11_

  - [ ]* 6.8 撰寫 Property 22 測試（法規推薦分支）
    - **Property 22：檢索空結果安全**
    - KB 回傳空結果時 `recommend` 回傳空清單而不拋出例外
    - **Validates: Requirements 5.9**
    - _Requirements: 5.9_
    - _Property: 22_

  - [ ] 6.9 P5 收尾與 commit
    - 確認完成條件：Property 7、11、22（法規推薦分支）測試通過；已廢止條文於檢索階段被排除
    - 確認所有測試通過，若有疑問請詢問使用者
    - 於同一 commit 內納入本階段實作與測試程式碼，建立 commit：`feat: 實作智能法規推薦與時效標示`
    - _Requirements: 14.2, 14.3, 14.4_

- [ ] 7. P6 相似案例比對與論理架構萃取
  - [ ] 7.1 實作 `src/petition_ai/similarity/outline.py`
    - 以段落標題正規表示式辨識「主文」、「事實」、「理由」，輸出 `ReasoningOutline`
    - 純字串處理，Bedrock 呼叫次數為 0
    - _Requirements: 6.5_

  - [ ] 7.2 實作 `src/petition_ai/similarity/matcher.py`
    - `match`：以 `top_k=15` 取回候選，metadata filter 限定 `case_type`
    - 依 `document_id` 聚合片段，使回傳結果 `document_id` 互不重複
    - 計算 `SimilarityBreakdown`：`issue_overlap`、`law_overlap` 以 Jaccard、`semantic_score` 取群組最高分、`feedback_weight`（P9 前為中性 0.5），各分項落於 [0,1]
    - 依 `final_score` 遞減排序，回傳不超過 `limit` 件且 `3 <= limit <= 5`
    - 附 `case_number_alias`、`decision_date`、`cited_laws`、`source_uri`；空結果回傳空清單
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6, 6.9_

  - [ ]* 7.3 撰寫 Property 12 測試
    - **Property 12：相似案例數量與唯一性**
    - 斷言 `len(match(...)) <= limit` 且結果 `document_id` 互不重複
    - **Validates: Requirements 6.1, 6.2**
    - _Requirements: 6.1, 6.2_
    - _Property: 12_

  - [ ]* 7.4 撰寫 Property 13 測試
    - **Property 13：相似案例類型一致**
    - 對 `case_type != OTHER` 之查詢，斷言每個回傳項之 `case_type` 等於查詢類型
    - **Validates: Requirements 6.3**
    - _Requirements: 6.3_
    - _Property: 13_

  - [ ]* 7.5 撰寫 Property 14 測試
    - **Property 14：相似度分項有界**
    - 斷言 `breakdown` 之四個分項皆 ∈ [0.0, 1.0]
    - **Validates: Requirements 6.4**
    - _Requirements: 6.4_
    - _Property: 14_

  - [ ]* 7.6 撰寫 Property 22 測試（相似案例分支）
    - **Property 22：檢索空結果安全**
    - KB 回傳空結果時 `match` 回傳空清單而不拋出例外
    - **Validates: Requirements 6.7**
    - _Requirements: 6.7_
    - _Property: 22_

  - [ ]* 7.7 撰寫論理架構與聚合單元測試
    - 以 spy 斷言 `extract_outline` 之 Bedrock 呼叫次數為 0
    - 多片段聚合後 `semantic_score` 取最高值、排序遞減
    - _Requirements: 6.5, 6.6_

  - [ ] 7.8 P6 收尾與 commit
    - 確認完成條件：Property 12、13、14、22（相似案例分支）測試通過；論理架構萃取不消耗 Bedrock 呼叫
    - 確認所有測試通過，若有疑問請詢問使用者
    - 於同一 commit 內納入本階段實作與測試程式碼，建立 commit：`feat: 實作相似案例比對`
    - _Requirements: 14.2, 14.3, 14.4_

- [ ] 8. P7 決定書草稿生成與引用驗證
  - [ ] 8.1 建立 `src/petition_ai/drafting/templates/`
    - 三大類型（洗錢防制法、廢棄物清理法、空氣污染防制法）與「其他」之 `DecisionTemplate`
    - 含 `main_text_pattern`、`fact_section_guide`、`reasoning_section_guide`、`instruction_clause`
    - 提供 `for_case_type()` 查表函式
    - _Requirements: 7.2, 7.3_

  - [ ] 8.2 實作 `src/petition_ai/drafting/prompts.py`
    - `SYSTEM_FACTS_ONLY`（禁止引入外部資訊）、`SYSTEM_CITE_ONLY_PROVIDED`（僅可引用提供之法條）
    - `FACTS_SCHEMA`、`REASONING_SCHEMA` 之 tool schema 定義
    - few-shot 範例注入函式，依 `case_type` 與 `issue_tag` 取最多 3 筆（ExemplarPool 於 P9 接線，此階段以空清單運作）
    - _Requirements: 7.6, 7.7_

  - [ ] 8.3 實作 `src/petition_ai/drafting/generator.py`
    - 依主文、事實欄、逐爭點理由欄、教示規定之順序分段生成
    - 主文與教示規定由模板逐字填入且 `generated=False`；教示規定段落 `section_id="instruction"` 且內容非空
    - 理由欄每一爭點產生 `section_id="reasoning:<issue_id>"`，僅提供該爭點對應之 `LawCitation` 作為可引用來源
    - `temperature=0.2`；schema 驗證失敗時以補齊缺漏欄位之修正提示重試 1 次，二次失敗標記「待人工填寫」並保留原始輸出
    - 重試達上限之段落標記 PENDING 並提供重新生成，其餘段落照常回傳
    - `DecisionDraft.disclaimer` 填入 AI 草稿聲明
    - _Requirements: 7.1, 7.4, 7.5, 7.8, 7.9, 7.11, 7.12_

  - [ ] 8.4 實作 `src/petition_ai/drafting/citation_guard.py`
    - 以正規表示式擷取草稿全部段落之法規引用字串，經 `normalize_law_id` 後比對許可清單
    - 未命中者標記 `UNVERIFIED`；命中但 `freshness.status != 現行` 者標記 `STALE`
    - `passed` 等於「全部引用皆為 VERIFIED」；每一引用在 `issues` 中恰出現 1 次
    - 純函式，不修改輸入草稿內容
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 8.5 撰寫 Property 15 測試
    - **Property 15：引用不幻覺**
    - `verify(d, A).passed` 為真時，斷言草稿中每個引用皆可正規化後對應至 `A` 中某個 `law_id`
    - **Validates: Requirements 8.3, 8.5, 8.10**
    - _Requirements: 8.3, 8.5, 8.10_
    - _Property: 15_

  - [ ]* 8.6 撰寫 Property 16 測試
    - **Property 16：引用驗證覆蓋**
    - 斷言草稿中每個被擷取之引用字串在 `issues` 中恰出現一次
    - **Validates: Requirements 8.1, 8.2**
    - _Requirements: 8.1, 8.2_
    - _Property: 16_

  - [ ]* 8.7 撰寫 Property 17 測試
    - **Property 17：模板段落不變**
    - 斷言 `generated == False` 之段落內容與 `DecisionTemplate` 對應欄位逐字相同
    - **Validates: Requirements 7.2, 7.3, 7.4**
    - _Requirements: 7.2, 7.3, 7.4_
    - _Property: 17_

  - [ ]* 8.8 撰寫 Property 18 測試
    - **Property 18：教示規定必存在**
    - 斷言每份草稿存在 `section_id == "instruction"` 之段落且非空白字元數大於 0
    - **Validates: Requirements 7.5**
    - _Requirements: 7.5_
    - _Property: 18_

  - [ ]* 8.9 撰寫草稿黃金檔案測試
    - 以 `tests/fixtures/` 之固定輸入案件與錄製之 KB 回應，比對草稿之段落存在性、段落順序與教示規定逐字內容，不比對模型自由文字
    - 涵蓋段落生成失敗標記 PENDING 之情境
    - _Requirements: 7.9, 14.10_

  - [ ] 8.10 P7 收尾與 commit
    - 確認完成條件：Property 15、16、17、18 測試通過；黃金檔案測試通過
    - 確認所有測試通過，若有疑問請詢問使用者
    - 於同一 commit 內納入本階段實作與測試程式碼，建立 commit：`feat: 實作決定書草稿生成與引用驗證`
    - _Requirements: 14.2, 14.3, 14.4_

- [ ] 9. P8 Gradio 操作介面
  - [ ] 9.1 實作 `src/petition_ai/ui/main.py`
    - 以 `gr.Blocks` 建立「案件匯入」、「案件資訊」、「法規與案例」、「草稿」、「成效」共 5 個分頁骨架與 `gr.State`
    - 以 `server_name="127.0.0.1"`、`share=False` 啟動
    - 上傳限制：副檔名白名單 `.pdf`／`.docx`／`.txt`、單檔大小上限、單次上傳總量上限
    - _Requirements: 11.1, 11.2, 11.3_

  - [ ] 9.2 實作 `src/petition_ai/ui/tabs/import_tab.py`
    - 檔案上傳、去識別化結果預覽、殘留掃描報告（個資類型、頁碼、段落索引、前後文）
    - 手動遮蔽介面：補標後重新執行去識別化，並將補標樣式登錄至本機規則庫
    - 掃描影像與非白名單副檔名之錯誤呈現
    - _Requirements: 1.3, 1.4, 2.7, 2.15_

  - [ ] 9.3 實作 `src/petition_ai/ui/tabs/case_tab.py`
    - 擷取欄位表單支援就地修正；點選溯源標記定位至 `source_span` 所指段落
    - `confidence < 0.7` 時以警示樣式呈現並要求確認或改選類型後方開放後續流程
    - 爭點清單依 `priority` 遞增顯示，支援新增、刪除、修改標籤
    - _Requirements: 3.6, 3.8, 3.9, 4.6, 4.7_

  - [ ] 9.4 實作 `src/petition_ai/ui/tabs/law_tab.py`
    - 左欄法規推薦：時效徽章（非現行以警示色）、採納／排除／標記不相關按鈕
    - 右欄相似案例：`SimilarityBreakdown` 各分項數值與 `ReasoningOutline`、選用／排除按鈕
    - _Requirements: 5.4, 6.8_

  - [ ] 9.5 實作 `src/petition_ai/ui/tabs/draft_tab.py`
    - 分段可編輯草稿、每段 `citation_refs` 與 `precedent_refs` 溯源標記
    - `UNVERIFIED` 紅框、`STALE` 黃框與側欄問題清單；PENDING 段落之重新生成按鈕
    - 匯出 DOCX 並保留 AI 草稿聲明；匯出路徑正規化限定於設定之 exports 目錄內
    - 呈現前經 `Rehydrator` 還原代號，且還原內容不寫入伺服端日誌
    - _Requirements: 2.12, 7.8, 7.10, 8.7, 8.8, 11.9_

  - [ ] 9.6 實作 `src/petition_ai/ui/components.py`
    - 以 `gr.Progress()` 逐階段更新處理狀態
    - 法規推薦與相似案例結果先行顯示，草稿生成於背景排隊執行
    - _Requirements: 11.4, 11.5_

  - [ ] 9.7 實作工作階段持久化
    - 以 `case_id` 為鍵將去識別化文件、擷取結果與草稿持久化於 `./.local/sessions/`
    - 啟動時列出未完成案件供續作；載入加密案件時要求輸入本機金鑰口令後方載入 `RedactionMap`
    - _Requirements: 11.6, 11.7, 11.8_

  - [ ]* 9.8 撰寫 UI 事件處理單元測試
    - 直接呼叫 handler 函式（不啟動伺服器）：上傳白名單拒絕、殘留掃描失敗之報告內容、匯出路徑穿越被阻擋
    - 斷言啟動參數為 `127.0.0.1` 且 `share=False`
    - 工作階段持久化與續作載入之往返一致
    - _Requirements: 11.2, 11.3, 11.7, 11.9_

  - [ ] 9.9 P8 收尾與 commit
    - 確認完成條件：端到端流程可於介面操作完成、服務僅綁定本機、五個分頁皆可運作
    - 確認所有測試通過，若有疑問請詢問使用者
    - 於同一 commit 內納入本階段實作與測試程式碼，建立 commit：`feat: 建立 Gradio 操作介面`
    - _Requirements: 14.2, 14.3, 14.4_

- [ ] 10. P9 使用者回饋驅動之優化迴路
  - [ ] 10.1 實作 `src/petition_ai/feedback/store.py`
    - DynamoDB 後端（開發階段可切換本機 SQLite）：回饋事件、偏好權重、範例池
    - `has_event`／`mark_event` 支援 `event_id` 去重；`get_weight`／`put_weight`
    - _Requirements: 9.13, 13.6_

  - [ ] 10.2 實作 `src/petition_ai/feedback/preference.py`
    - `PreferenceModel.update`：EMA `w ← (1−η)·w + η·reward`，η = 0.2，結果 clamp 至 [0,1]
    - `_reward_of`：ACCEPT／KEEP → 1.0；REJECT／IRRELEVANT／DELETE → 0.0；EDIT → `1 − edit_distance_ratio`
    - `weight()` 對未見過之 `(case_type, issue_tag, item_id)` 回傳中性值 0.5
    - `sample_count` 每次更新恰增加 1；對相同 `event_id` 冪等
    - _Requirements: 9.8, 9.9, 9.10, 9.11, 9.12, 9.13, 9.14, 9.18_

  - [ ] 10.3 實作 `src/petition_ai/feedback/collector.py` 之明示訊號
    - `on_citation_action`、`on_precedent_action`：產生 `FeedbackEvent` 並寫入 `FeedbackStore`
    - 承辦人員手動改選案件類型時產生事件，供擴充規則式分類器關鍵字表
    - `UNVERIFIED` 引用被確認為正確引用時產生事件
    - 事件僅含代號與識別碼
    - _Requirements: 3.7, 8.9, 9.1, 9.2, 9.16_

  - [ ] 10.4 實作 `on_draft_finalize` 草稿差異轉回饋訊號
    - 逐段比對生成草稿與定稿並計算 `edit_distance_ratio`
    - `ratio == 0.0` → 整段保留；定稿去空白後長度為 0 → 整段刪除；其餘 → 編輯
    - 生成段落之 `citation_refs` 法條若仍出現於定稿內容，產生該法條之正向事件
    - 僅就 `generated == True` 之段落產生學習訊號；事件寫入後逐筆套用 `PreferenceModel.update`
    - _Requirements: 9.3, 9.4, 9.5, 9.6, 9.7, 9.17_

  - [ ] 10.5 實作 `src/petition_ai/feedback/exemplars.py`
    - `ExemplarPool.register`：`edit_distance_ratio` 不高於門檻之定稿段落登錄為候選範例
    - 依 `case_type` 與 `issue_tag` 分群，保留最近 N 筆；`get(n=3)` 供提示詞注入
    - 範例摘要為去識別化內容
    - _Requirements: 7.7, 9.15_

  - [ ] 10.6 接線偏好權重至檢索與比對
    - `LegalRetriever` 與 `PrecedentMatcher` 自 `FeedbackStore` 讀取權重並納入 `feedback_weight`
    - `DraftGenerator` 自 `ExemplarPool` 取得 few-shot 範例，取代 P7 之空清單
    - 於 `build_container()` 完成依賴注入
    - _Requirements: 9.19, 7.7_

  - [ ] 10.7 實作 `src/petition_ai/feedback/metrics.py`
    - 計算 `citation_accept_rate`、`precedent_accept_rate`、`mean_edit_distance_ratio`、`mean_time_to_finalize_s`、`case_count`
    - 稽核軌跡：被採納之建議識別碼、草稿修改差異、定稿操作者代號
    - 記錄單一案件實際 Bedrock 呼叫次數（讀取 BedrockGateway 計數器）
    - _Requirements: 10.1, 10.6, 10.7_

  - [ ] 10.8 實作 `src/petition_ai/ui/tabs/metrics_tab.py`
    - 以趨勢圖呈現指定時間窗內之 `OptimizationMetrics`
    - _Requirements: 10.2_

  - [ ] 10.9 實作 `scripts/replay_feedback.py`
    - **Property 23：優化有效性（統計性質，以離線回放評估）**
    - 重放歷史回饋事件序列，比較啟用與停用回饋權重兩種設定下之 Recall@5 與 MRR
    - 輸出同一 `case_type` 之 `mean_edit_distance_ratio` 移動平均趨勢
    - **Validates: Requirements 10.3, 10.4**
    - _Requirements: 10.3, 10.4_
    - _Property: 23_

  - [ ]* 10.10 撰寫 Property 8 測試
    - **Property 8：回饋單調性**
    - 以 `feedback_event_sequence_strategy()` 產生動作序列，斷言連續 ACCEPT 使權重單調不減、連續 REJECT 單調不增
    - **Validates: Requirements 9.10, 9.11**
    - _Requirements: 9.10, 9.11_
    - _Property: 8_

  - [ ]* 10.11 撰寫 Property 9 測試
    - **Property 9：權重有界**
    - 對任意事件序列，斷言套用後全部 `PreferenceWeight.weight ∈ [0.0, 1.0]`
    - **Validates: Requirements 9.8, 9.9**
    - _Requirements: 9.8, 9.9_
    - _Property: 9_

  - [ ]* 10.12 撰寫 Property 10 測試
    - **Property 10：回饋冪等**
    - 斷言 `update(e); update(e)` 之結果等同於 `update(e)`，且 `sample_count` 僅增加 1
    - **Validates: Requirements 9.13**
    - _Requirements: 9.13, 9.18_
    - _Property: 10_

  - [ ]* 10.13 撰寫回饋擷取單元測試
    - `edit_distance_ratio` 邊界：0.0 判為整段保留、空白定稿判為整段刪除、其餘判為編輯
    - 模板段落（`generated == False`）不產生學習訊號
    - 定稿保留法條產生正向事件；事件序列化通過殘留掃描
    - _Requirements: 9.4, 9.5, 9.6, 9.7, 9.16, 9.17_

  - [ ] 10.14 P9 收尾與 commit
    - 確認完成條件：Property 8、9、10 測試通過；Property 23 離線回放腳本可產出比較結果
    - 確認所有測試通過，若有疑問請詢問使用者
    - 於同一 commit 內納入本階段實作與測試程式碼，建立 commit：`feat: 實作使用者回饋驅動之優化迴路`
    - _Requirements: 14.2, 14.3, 14.4_

- [ ] 11. P10 部署設定、觀測與合規收尾
  - [ ] 11.1 補齊多人使用之部署設定
    - `infra/`：ALB 與身分提供者驗證置於 Gradio 服務之前
    - EC2 Security Group 入向來源限定為 ALB 安全群組或 SSM Session Manager 端點，不得有 `0.0.0.0/0`
    - _Requirements: 11.10, 13.5_

  - [ ] 11.2 接線 CloudWatch 日誌與指標
    - 掛載個資遮蔽 filter，於寫入前執行殘留掃描
    - 輸出案件流程階段耗時與 Bedrock 呼叫次數指標
    - _Requirements: 10.5, 10.7_

  - [ ] 11.3 收斂 IAM 政策與資源盤點
    - IAM 政策限定所需 model ARN、Knowledge Base ARN、S3 前綴與 DynamoDB 表；改用 IAM Role 或 SSO 短期憑證
    - 設定檔記錄僅申請 1 個嵌入模型與 1 個生成模型之存取權，及使用中之 EC2／SageMaker 執行個體清單
    - _Requirements: 13.7, 13.8, 13.14_

  - [ ] 11.4 實作收尾檢核測試套件 `tests/compliance/test_final_checklist.py`
    - 五類檢查：公開存取設定、部署區域、Bedrock 速率、模型存取權範圍、個資外送
    - 加入單案件 Bedrock 呼叫次數落於 7 至 10 次之預算檢視
    - 斷言優化流程不含任何模型訓練作業
    - _Requirements: 12.9, 13.12, 13.13_

  - [ ] 11.5 建立提交前檢核 hook
    - `.pre-commit-config.yaml`：detect-secrets 機密掃描、`.kiro/` 未被忽略檢查、ruff 與 mypy
    - 檢核未通過時阻擋該階段 commit
    - _Requirements: 13.11, 14.6, 14.7_

  - [ ] 11.6 建立測試執行流程設定
    - 整體覆蓋率門檻 80%，去識別化與速率限制模組 100% 分支覆蓋
    - AWS 相依一律以 Stubber／moto／測試替身隔離，斷言對真實 Bedrock 端點請求數為 0
    - 區分離線整合測試（CI 執行）與線上冒煙測試（手動觸發、單案件序列執行）
    - _Requirements: 14.8, 14.9_

  - [ ] 11.7 補齊 `README.md` 與 `.env.example` 之設定與執行說明
    - 環境變數清單、preflight 執行方式、KB 建置步驟、測試指令
    - 說明 `.kiro/` 已納入版本控制之用途（競賽規範第 9 條）
    - 確認不含任何真實憑證
    - _Requirements: 13.9, 14.7_

  - [ ] 11.8 P10 收尾與 commit
    - 確認完成條件：design.md 之收尾檢核清單 10 項全數通過
    - 確認所有測試通過，若有疑問請詢問使用者
    - 於同一 commit 內納入本階段實作與測試程式碼，建立 commit：`chore: 完成部署設定與合規檢核`
    - _Requirements: 14.2, 14.3, 14.4, 14.7_

## Notes

**備註**

- 標記 `*` 之子任務為選用，可為加速 MVP 而略過。但合規性任務刻意**未**標記 `*`：2.12、2.13（個資外送與對照表序列化）、3.6（Bedrock 無旁路）、1.8、4.5、11.4（競賽規範檢核）。這些是硬性閘門，略過即違反競賽規範。
- 去識別化模組（`ingest/redactor.py`、`ingest/detectors.py`）與速率限制模組（`core/rate_limit.py`）要求 100% 分支覆蓋，其單元測試雖標記 `*`，實務上為完成條件之一。
- Property 1 至 Property 22 以 Hypothesis 撰寫；Property 23 為統計性質，以 `scripts/replay_feedback.py` 離線回放評估，不作為單元測試。
- Property 22 拆為兩個子任務（6.8 與 7.6），分別對應 `LegalRetriever.recommend` 與 `PrecedentMatcher.match` 兩條分支及其對應之需求條款。
- 階段依賴：P0 → P1、P0 → P2、P1 → P3、P2 → P3、P3 → P4、P4 → P5、P4 → P6、P5 → P7、P6 → P7、P7 → P8、P8 → P9、P9 → P10。P1 與 P2 可並行，P5 與 P6 可並行。
- 每一 P 階段之最後一個子任務即為該階段之 commit 任務，commit 訊息採 design.md 指定之文字，且同一 commit 內須含實作與測試程式碼。
- 測試資料一律為程式生成之假資料，不得使用任何真實個人資料或真實案件內容。

## Task Dependency Graph

**任務依賴關係圖**

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "1.5", "1.8"] },
    { "id": 2, "tasks": ["1.6", "1.7"] },
    { "id": 3, "tasks": ["1.9"] },
    { "id": 4, "tasks": ["2.1"] },
    { "id": 5, "tasks": ["2.2", "2.4", "3.1"] },
    { "id": 6, "tasks": ["2.3", "2.5", "3.2"] },
    { "id": 7, "tasks": ["2.6", "2.7", "3.3", "3.4"] },
    { "id": 8, "tasks": ["2.8", "2.9", "2.10", "2.11", "3.5", "3.6"] },
    { "id": 9, "tasks": ["2.12", "2.13", "2.14"] },
    { "id": 10, "tasks": ["2.15", "3.7"] },
    { "id": 11, "tasks": ["4.1", "4.3", "4.4"] },
    { "id": 12, "tasks": ["4.2", "4.5"] },
    { "id": 13, "tasks": ["4.6"] },
    { "id": 14, "tasks": ["4.7"] },
    { "id": 15, "tasks": ["5.1", "5.2", "5.3"] },
    { "id": 16, "tasks": ["5.4"] },
    { "id": 17, "tasks": ["5.5"] },
    { "id": 18, "tasks": ["6.1", "6.3", "7.1"] },
    { "id": 19, "tasks": ["6.2", "6.4", "6.5", "7.2"] },
    { "id": 20, "tasks": ["6.6", "6.7", "6.8", "7.3", "7.4", "7.5", "7.6", "7.7"] },
    { "id": 21, "tasks": ["6.9", "7.8"] },
    { "id": 22, "tasks": ["8.1", "8.2"] },
    { "id": 23, "tasks": ["8.3", "8.4"] },
    { "id": 24, "tasks": ["8.5", "8.6", "8.7", "8.8", "8.9"] },
    { "id": 25, "tasks": ["8.10"] },
    { "id": 26, "tasks": ["9.1", "9.6", "9.7"] },
    { "id": 27, "tasks": ["9.2", "9.3", "9.4", "9.5"] },
    { "id": 28, "tasks": ["9.8"] },
    { "id": 29, "tasks": ["9.9"] },
    { "id": 30, "tasks": ["10.1", "10.5"] },
    { "id": 31, "tasks": ["10.2", "10.3"] },
    { "id": 32, "tasks": ["10.4", "10.6", "10.7"] },
    { "id": 33, "tasks": ["10.8", "10.9", "10.10", "10.11", "10.12", "10.13"] },
    { "id": 34, "tasks": ["10.14"] },
    { "id": 35, "tasks": ["11.1", "11.2", "11.3", "11.6", "11.7"] },
    { "id": 36, "tasks": ["11.4", "11.5"] },
    { "id": 37, "tasks": ["11.8"] }
  ]
}
```
