# Requirements Document

## Introduction

**簡介**

本文件為「訴願決定書 AI 輔助撰擬系統」（petition-decision-ai-assistant）之需求規格，依已核可之設計文件（design.md）反向推導而成，用以確保設計意圖被完整、可驗證地記錄。

新北市訴願案量自 110 年之 1,238 件攀升至 114 年之 1,566 件，其中以洗錢防制法、廢棄物清理法及空氣污染防制法案件為最大宗。此類案件之處分依據與論理架構具高度規律性，惟每一份決定書仍需承辦人員逐一撰擬與校對。本系統以 Python 與 Gradio 建構本機工作台，並以 Amazon Bedrock Knowledge Bases 作為檢索骨幹，提供案件資訊擷取與分類、智能法規推薦、相似案例比對、決定書草稿生成四項核心能力，另納入依使用者操作持續優化之回饋迴路。

本規格有三項貫穿全文之基本立場：

第一，**個資去識別化為強制閘門**。訴願文件本質上含有訴願人姓名、地址、身分證統一編號等個人資料，而競賽規範明文禁止將個人資料匯入 AWS 帳戶。因此去識別化為架構上不可繞過之前置條件，而非事後補強。

第二，**AI 產出為草稿，最終責任在人**。系統標示風險而不靜默修改法律文書內容；引用驗證僅標記可疑項目，處置決定一律交由承辦人員。

第三，**Bedrock 每秒 1 請求為主要設計約束**。所有效能設計之重點在於減少呼叫次數，而非加快單次呼叫。

## Glossary

**詞彙表**

- **Petition_AI_System**：訴願決定書 AI 輔助撰擬系統整體，涵蓋本機應用、AWS 資源與相關設定。
- **Workbench_UI**：以 Gradio Blocks 建構之承辦人員操作介面，共五個分頁。
- **DocumentLoader**：文件載入元件，將 PDF、DOCX、TXT 轉為保留頁碼與段落索引之 SourceDocument。
- **SourceDocument**：原始文件之結構化表述，含個人資料，僅存於本機記憶體與本機暫存區。
- **PIIRedactor**：個資去識別化元件，將個人資料替換為穩定代號並產生 RedactionMap。
- **RedactionAuditor**：殘留個資掃描元件，對去識別化後全文執行 scan_residual。
- **RedactedDocument**：去識別化後之文件，為唯一允許寫入 S3 或匯入 Knowledge Base 之文件型別。
- **RedactionMap**：代號至原文之還原對照表，以 AES-GCM 加密後僅存於本機。
- **Rehydrator**：呈現層還原元件，於顯示前以 RedactionMap 將代號還原為原文。
- **CaseExtractor**：案件資訊擷取元件，負責事實擷取、案件類型分類與爭點萃取。
- **CaseFacts**：訴願人、原處分內容與訴願理由之結構化集合。
- **Classification**：案件類型判定結果，含 case_type、confidence 與 method。
- **Issue**：爭點，含受控詞彙標籤 tag、爭點敘述與優先序 priority。
- **Issue_Tag_Vocabulary**：爭點標籤之受控詞彙表，使回饋權重可跨案件累積。
- **LegalRetriever**：法規推薦元件，自法規庫檢索法條、行政函釋與法院判決並產生融合排序。
- **LawCitation**：單一法規推薦項目，含 law_id、原文片段、kb_score、feedback_weight、final_score 與 FreshnessFlag。
- **FreshnessFlag**：法規時效標示，含 EffectiveStatus 與 last_amended_date。
- **EffectiveStatus**：法規效力狀態，取值為「現行」、「已修正」、「已廢止」或「未確認」。
- **PrecedentMatcher**：相似案例比對元件，自先例庫取回候選並重排為 3 至 5 件 PrecedentMatch。
- **PrecedentMatch**：單一相似歷史決定書，含 SimilarityBreakdown 與 ReasoningOutline。
- **SimilarityBreakdown**：相似度分解，含 issue_overlap、law_overlap、semantic_score 與 feedback_weight。
- **ReasoningOutline**：歷史決定書之論理架構摘要，含事實欄摘要、論理步驟與結論。
- **DraftGenerator**：決定書草稿生成元件，分段產生主文、事實欄、逐爭點理由欄與教示規定。
- **DecisionTemplate**：類型化決定書骨架，含主文定型句、撰寫指引與教示規定定型文字。
- **DecisionDraft**：決定書草稿，由多個 DraftSection 組成並含 AI 草稿聲明。
- **DraftSection**：草稿段落，含 section_id、內容、引用參照與 generated 標記。
- **CitationGuard**：引用驗證元件，比對草稿引用與許可清單並輸出 VerificationReport。
- **VerificationReport**：引用驗證報告，含 passed 與逐筆 CitationIssue。
- **CitationStatus**：引用狀態，取值為 VERIFIED、UNVERIFIED 或 STALE。
- **FeedbackCollector**：回饋擷取元件，將明示操作與草稿差異轉為 FeedbackEvent。
- **FeedbackEvent**：單一回饋事件，僅含代號與識別碼。
- **FeedbackStore**：回饋事件與偏好權重之儲存後端。
- **PreferenceModel**：偏好權重模型，以指數移動平均線上更新排序權重。
- **PreferenceWeight**：偏好權重，值域為 [0.0, 1.0]，中性值為 0.5。
- **ExemplarPool**：few-shot 範例池，收錄低編輯距離之定稿段落。
- **OptimizationMetrics**：優化成效指標集合，含採納率、平均編輯距離與平均定稿時間。
- **BedrockGateway**：所有 Bedrock 與 Knowledge Base 呼叫之唯一出口，內含結果快取。
- **RateLimiter**：全域 token bucket 速率閘門，確保 Bedrock 請求低於每秒 1 次。
- **PreflightChecker**：啟動前置檢查元件，驗證模型存取權與 Knowledge Base 狀態。
- **KBSync**：Knowledge Base 同步元件，負責 S3 上傳、metadata 驗證與 ingestion 作業。
- **ComplianceTestSuite**：合規專項測試套件，位於 tests/compliance/。
- **DeliveryProcess**：實作交付流程，涵蓋階段切分、完成條件與 git commit 規範。

## Requirements

### Requirement 1: 案件文件匯入與格式支援

**User Story:** 作為訴願案件承辦人員，我想要將訴願書與原處分書等卷證檔案匯入系統，以便後續分析能取得完整案件文字並可回溯至原文位置。

#### Acceptance Criteria

1. WHEN 承辦人員上傳副檔名為 `.pdf`、`.docx` 或 `.txt` 之檔案，THE DocumentLoader SHALL 將檔案內容轉換為 SourceDocument，並為每一段落保留 page_no 與 paragraph_index。
2. WHEN DocumentLoader 載入 `.txt` 檔案，THE DocumentLoader SHALL 自動偵測 UTF-8 與 Big5 編碼並依偵測結果解碼。
3. IF 上傳檔案抽取所得文字之總字元數為 0，THEN THE DocumentLoader SHALL 回報「疑為掃描影像，無可抽取文字層」錯誤並提示改用可搜尋 PDF。
4. IF 上傳檔案之副檔名不屬於 `.pdf`、`.docx`、`.txt` 白名單，THEN THE Workbench_UI SHALL 拒絕該檔案並顯示允許之副檔名清單。
5. THE DocumentLoader SHALL 使 SourceDocument.paragraphs 之元素數等於 SourceDocument.page_of_paragraph 之元素數。
6. WHILE DocumentLoader 處理上傳檔案，THE DocumentLoader SHALL 僅以本機運算完成文字抽取，且發出之網路請求數為 0。
7. WHEN 承辦人員於單次操作上傳多個檔案，THE DocumentLoader SHALL 依上傳順序合併為單一 SourceDocument，並維持頁碼與段落索引之連續對應。
8. WHILE DocumentLoader 處理頁數超過 20 頁之文件，THE DocumentLoader SHALL 以段落為單位串流處理，使單次載入之記憶體內容不超過一個段落集合批次。

### Requirement 2: 個資去識別化強制閘門

**User Story:** 作為資料保護負責人，我想要所有文件在離開本機之前完成去識別化，以便系統符合競賽規範第 2 條禁止將個人資料匯入 AWS 帳戶之要求。

#### Acceptance Criteria

1. WHEN SourceDocument 完成載入，THE PIIRedactor SHALL 於任何內容寫入 S3、Bedrock 或 Knowledge Base 之前，將偵測到之個人資料替換為代號。
2. THE PIIRedactor SHALL 偵測身分證統一編號、營利事業統一編號、居留證號、市內電話、行動電話、地址、電子郵件、車牌號碼、金融帳號、案號與人名共 11 類個人資料樣式。
3. WHEN 同一實體在同一案件內出現於多個位置，THE PIIRedactor SHALL 將全部出現位置映射至同一代號，且代號格式符合 `^【[\u4e00-\u9fa5]+[A-Z]\d*】$`。
4. THE PIIRedactor SHALL 使 RedactionMap.mapping 為單射，即相異代號對應相異原文。
5. WHEN 代號替換作業完成，THE RedactionAuditor SHALL 對替換後全文執行殘留掃描，並於掃描結果為空清單時方允許文件外送。
6. IF 殘留掃描回報至少一項命中，THEN THE PIIRedactor SHALL 拋出 ResidualPIIError 並中止流程，且 Petition_AI_System 送往 AWS 之內容量為 0 位元組。
7. WHEN 殘留掃描回報命中項目，THE Workbench_UI SHALL 顯示每一命中項目之個資類型、頁碼、段落索引與前後文，並提供手動遮蔽介面供承辦人員補標後重新執行去識別化。
8. THE PIIRedactor SHALL 使 RedactedDocument.paragraphs 之元素數與 RedactedDocument.page_of_paragraph 之內容，與輸入 SourceDocument 之對應欄位相同。
9. THE PIIRedactor SHALL 使 RedactedDocument 與 RedactionMap 之組合可還原為原始 SourceDocument 之逐字內容。
10. THE PIIRedactor SHALL 將 RedactionMap 以 AES-GCM 加密後僅寫入本機路徑 `./.local/redaction/`。
11. THE Petition_AI_System SHALL 使所有送往 Bedrock、S3 與 Knowledge Base 之 payload 通過殘留掃描且掃描結果為空清單。
12. WHEN Workbench_UI 需向承辦人員顯示含代號之內容，THE Rehydrator SHALL 於呈現階段以本機 RedactionMap 還原代號，且還原後內容寫入伺服端日誌之筆數為 0。
13. IF RedactionMap 型別出現於任何 AWS SDK 呼叫參數，THEN THE ComplianceTestSuite SHALL 判定測試失敗並回報呼叫位置。
14. WHERE Petition_AI_System 輸出日誌訊息，THE Petition_AI_System SHALL 於輸出前對該訊息執行殘留掃描並遮蔽命中內容。
15. WHEN 承辦人員完成手動補標，THE PIIRedactor SHALL 將該補標樣式登錄至本機規則庫，供後續案件自動命中。

### Requirement 3: 案件資訊擷取與分類

**User Story:** 作為承辦人員，我想要系統自動擷取訴願人資訊、原處分內容與訴願理由並判定案件類型，以便省去人工逐項摘錄與歸類之時間。

#### Acceptance Criteria

1. WHEN RedactedDocument 通過殘留掃描，THE CaseExtractor SHALL 擷取 Petitioner、OriginalDisposition 與 PetitionGround，並輸出 CaseFacts。
2. THE CaseExtractor SHALL 以 Bedrock Converse API 之 tool use 機制強制模型輸出符合指定 JSON schema 之結構化結果。
3. THE CaseExtractor SHALL 為每一擷取欄位附上 source_span，且該 source_span 之 paragraph_index 指向 RedactedDocument 中存在之段落。
4. WHEN 案件文件命中洗錢防制法、廢棄物清理法或空氣污染防制法之法規名稱或對應處分機關關鍵字，THE CaseExtractor SHALL 以規則式分類判定 case_type，並將 Classification.method 設為 `rule`。
5. IF 規則式分類無法判定 case_type，THEN THE CaseExtractor SHALL 呼叫生成模型執行 zero-shot 分類，並將 Classification.method 設為 `model`。
6. IF Classification.confidence 小於 0.7，THEN THE Workbench_UI SHALL 以警示樣式呈現分類結果，並要求承辦人員確認或改選案件類型後方開放後續流程。
7. WHEN 承辦人員手動改選案件類型，THE FeedbackCollector SHALL 產生一筆 FeedbackEvent，供改進規則式分類器之關鍵字表。
8. WHEN Workbench_UI 顯示擷取結果，THE Workbench_UI SHALL 允許承辦人員就地修正任一擷取欄位之值。
9. WHEN 承辦人員點選任一擷取欄位之溯源標記，THE Workbench_UI SHALL 定位至該欄位 source_span 所指之原文段落。
10. THE CaseExtractor SHALL 於 Classification.rationale 記錄判定依據，使分類結果可供人工複核。

### Requirement 4: 爭點萃取

**User Story:** 作為承辦人員，我想要系統自動萃取案件主要爭點並套用統一標籤，以便法規推薦與相似案例比對能以爭點為單位精準運作。

#### Acceptance Criteria

1. WHEN CaseFacts 與 case_type 皆已確定，THE CaseExtractor SHALL 萃取 Issue 清單，並為每一 Issue 指派 tag。
2. THE CaseExtractor SHALL 使每一 Issue.tag 屬於 Issue_Tag_Vocabulary 之受控詞彙。
3. IF 生成模型未萃取出任何爭點，THEN THE CaseExtractor SHALL 以每一 PetitionGround 逐項作為爭點，使 Issue 清單之元素數至少為 1。
4. THE CaseExtractor SHALL 為每一 Issue 指派 priority，且數值 1 表示最主要爭點。
5. THE CaseExtractor SHALL 使每一 Issue.related_ground_indices 之元素皆對應至存在之 PetitionGround.ground_index。
6. WHEN 爭點萃取完成，THE Workbench_UI SHALL 依 priority 遞增順序顯示爭點清單。
7. WHEN 承辦人員新增、刪除或修改爭點標籤，THE CaseExtractor SHALL 以修改後之爭點清單作為後續檢索與生成之輸入。

### Requirement 5: 智能法規推薦與時效標示

**User Story:** 作為承辦人員，我想要系統依案件類型與爭點自動推薦相關法條、行政函釋與法院判決並標示時效狀態，以便降低人工檢索之耗時與遺漏風險。

#### Acceptance Criteria

1. WHEN case_type 與爭點清單皆已確定，THE LegalRetriever SHALL 自法規庫檢索法條、行政函釋與法院判決，並回傳 LawCitation 清單。
2. THE LegalRetriever SHALL 於檢索請求之 metadata filter 中排除 effective_status 等於「已廢止」之文件。
3. THE LegalRetriever SHALL 依 Knowledge Base metadata 之 effective_status 與 last_amended_date，為每一 LawCitation 產生 FreshnessFlag。
4. WHERE LawCitation.freshness.status 不等於「現行」，THE LegalRetriever SHALL 於融合分數中套用 staleness 懲罰項，並由 Workbench_UI 以警示色標記該項目。
5. THE LegalRetriever SHALL 以 `final_score = α·kb_score + β·feedback_weight + γ·type_match_bonus − δ·staleness_penalty` 計算融合分數，且回傳值落於 [0.0, 1.0] 區間。
6. WHEN 全部候選項目之 feedback_weight 皆等於冷啟動中性值 0.5，THE LegalRetriever SHALL 產生與純 kb_score 排序一致之推薦順序。
7. THE LegalRetriever SHALL 依 final_score 遞減排序回傳結果，且回傳元素數不超過 top_k。
8. WHEN 同一 law_id 出現於多個檢索片段，THE LegalRetriever SHALL 保留 kb_score 最高之片段，並合併全部片段之 matched_issue_ids。
9. IF 法規庫檢索回傳空結果，THEN THE LegalRetriever SHALL 回傳空清單並維持流程繼續執行。
10. THE LegalRetriever SHALL 為每一 LawCitation 附上 source_uri 與 Knowledge Base 回傳之原文片段。
11. WHEN 同一 `(kb_id, query, metadata_filter, top_k)` 組合於同一工作階段內重複出現，THE BedrockGateway SHALL 回傳快取結果，且新增之 Bedrock 請求數為 0。
12. WHEN 爭點數超過 3，THE LegalRetriever SHALL 將爭點查詢合併為單一加權查詢並以較大 top_k 取回結果，使法規檢索之 Bedrock 呼叫次數不超過 3 次。

### Requirement 6: 相似案例比對

**User Story:** 作為承辦人員，我想要系統從歷史訴願決定書中找出最相似之 3 至 5 件案例並說明相似依據，以便參考過往論理架構並維持法律見解一致。

#### Acceptance Criteria

1. WHEN case_type 與爭點清單皆已確定，THE PrecedentMatcher SHALL 自先例庫以 top_k 等於 15 取回候選片段，並於重排後回傳不超過 limit 件 PrecedentMatch，且 limit 落於 3 至 5 之範圍。
2. THE PrecedentMatcher SHALL 依 document_id 聚合同一決定書之多個片段，使回傳結果中 document_id 互不重複。
3. WHERE case_type 不等於「其他」，THE PrecedentMatcher SHALL 使每一回傳之 PrecedentMatch.case_type 等於查詢之 case_type。
4. THE PrecedentMatcher SHALL 為每一 PrecedentMatch 提供 SimilarityBreakdown，包含 issue_overlap、law_overlap、semantic_score 與 feedback_weight，且各分項落於 [0.0, 1.0] 區間。
5. THE PrecedentMatcher SHALL 以段落標題正規表示式辨識「主文」、「事實」與「理由」段落並輸出 ReasoningOutline，且該作業之 Bedrock 呼叫次數為 0。
6. THE PrecedentMatcher SHALL 依 final_score 遞減排序回傳結果。
7. IF 先例庫檢索回傳空結果，THEN THE PrecedentMatcher SHALL 回傳空清單並維持流程繼續執行。
8. WHEN Workbench_UI 顯示相似案例，THE Workbench_UI SHALL 併同顯示 SimilarityBreakdown 各分項數值與 ReasoningOutline，使承辦人員可判讀排序依據。
9. THE PrecedentMatcher SHALL 為每一 PrecedentMatch 附上 case_number_alias、decision_date、cited_laws 與 source_uri。

### Requirement 7: 決定書草稿生成

**User Story:** 作為承辦人員，我想要系統依案件資訊、採用之法條與選用之相似案例生成決定書草稿，以便在既有基礎上審核修正而非從零撰擬。

#### Acceptance Criteria

1. WHEN 承辦人員確認採用之法條與相似案例，THE DraftGenerator SHALL 依主文、事實欄、逐爭點理由欄、教示規定之順序生成段落並輸出 DecisionDraft。
2. THE DraftGenerator SHALL 以 DecisionTemplate.main_text_pattern 填入主文段落，並將該段落之 generated 設為 False。
3. THE DraftGenerator SHALL 以 DecisionTemplate.instruction_clause 逐字填入教示規定段落，並將該段落之 generated 設為 False。
4. THE DraftGenerator SHALL 使每一 generated 等於 False 之段落內容與 DecisionTemplate 對應欄位逐字相同。
5. THE DraftGenerator SHALL 使每一 DecisionDraft 包含 section_id 等於 `instruction` 之段落，且該段落內容之非空白字元數大於 0。
6. WHEN 生成理由欄，THE DraftGenerator SHALL 為每一 Issue 產生 section_id 等於 `reasoning:<issue_id>` 之段落，並僅提供該爭點對應之 LawCitation 作為可引用來源。
7. WHEN 生成理由欄，THE DraftGenerator SHALL 自 ExemplarPool 取得對應 case_type 與 issue_tag 之最多 3 筆範例注入提示詞。
8. THE DraftGenerator SHALL 於 DecisionDraft.disclaimer 標示「本文為 AI 生成草稿，須經承辦人員審核確認後方得使用。」，並於匯出之 DOCX 檔案中保留該標示。
9. IF 任一理由欄段落生成失敗且重試次數達上限，THEN THE DraftGenerator SHALL 將該段落標記為 PENDING、提供重新生成操作，並使其餘段落照常回傳。
10. WHEN Workbench_UI 顯示草稿，THE Workbench_UI SHALL 提供逐段編輯功能，並顯示每一段落之 citation_refs 與 precedent_refs 溯源標記。
11. IF 模型輸出未通過 schema 驗證，THEN THE DraftGenerator SHALL 以補齊缺漏欄位之修正提示重試 1 次；IF 重試後仍未通過驗證，THEN THE DraftGenerator SHALL 將缺漏欄位標記為「待人工填寫」並保留模型原始輸出供參考。
12. THE DraftGenerator SHALL 以 temperature 等於 0.2 之推論設定呼叫生成模型，使同一輸入之輸出具一致性。

### Requirement 8: 引用驗證與防幻覺

**User Story:** 作為承辦人員，我想要系統驗證草稿中每一法規引用是否確實來自檢索結果，以便避免採用幻覺引用而使決定書事後遭法院撤銷。

#### Acceptance Criteria

1. WHEN DecisionDraft 生成完成，THE CitationGuard SHALL 擷取全部段落中之法規引用字串並與許可清單比對，輸出 VerificationReport。
2. THE CitationGuard SHALL 使草稿中每一被擷取之引用字串在 VerificationReport.issues 中恰出現 1 次。
3. IF 引用字串正規化後未對應至許可清單中任一 law_id，THEN THE CitationGuard SHALL 將該引用之狀態設為 UNVERIFIED。
4. IF 引用字串對應之 LawCitation.freshness.status 不等於「現行」，THEN THE CitationGuard SHALL 將該引用之狀態設為 STALE。
5. THE CitationGuard SHALL 使 VerificationReport.passed 等於「全部引用狀態皆為 VERIFIED」之判斷結果。
6. THE CitationGuard SHALL 保留輸入 DecisionDraft 之內容不變，並將引用之處置決定交由承辦人員執行。
7. WHEN VerificationReport 包含 UNVERIFIED 引用，THE Workbench_UI SHALL 以紅框標記該引用並列入側欄問題清單。
8. WHEN VerificationReport 包含 STALE 引用，THE Workbench_UI SHALL 以黃框標記該引用並列入側欄問題清單。
9. WHEN 承辦人員將某一 UNVERIFIED 引用確認為正確引用，THE FeedbackCollector SHALL 產生一筆 FeedbackEvent 供改善後續檢索。
10. THE CitationGuard SHALL 使 normalize_law_id 對全形數字、半形數字、「第27條」與「第 27 條」等寫法產生相同正規化結果，且該函式滿足 `f(f(x)) == f(x)`。

### Requirement 9: 使用者操作驅動之優化迴路

**User Story:** 作為承辦人員，我想要系統從我的採納、排除與草稿修改行為中學習，以便後續案件之推薦與草稿品質隨使用逐步提升。

#### Acceptance Criteria

1. WHEN 承辦人員對某一 LawCitation 執行採納、排除或標記不相關，THE FeedbackCollector SHALL 產生一筆 FeedbackEvent 並寫入 FeedbackStore。
2. WHEN 承辦人員選用或排除某一 PrecedentMatch，THE FeedbackCollector SHALL 產生一筆 FeedbackEvent 並寫入 FeedbackStore。
3. WHEN 承辦人員完成草稿定稿，THE FeedbackCollector SHALL 逐段比對生成草稿與定稿內容、計算 edit_distance_ratio，並產生段落級 FeedbackEvent。
4. IF 段落之 edit_distance_ratio 等於 0.0，THEN THE FeedbackCollector SHALL 將該段落事件之 action 設為「整段保留」。
5. IF 定稿段落內容去除空白字元後之長度為 0，THEN THE FeedbackCollector SHALL 將該段落事件之 action 設為「整段刪除」。
6. WHEN 段落內容經修改且去除空白字元後之長度大於 0，THE FeedbackCollector SHALL 將該段落事件之 action 設為「編輯」並記錄 edit_distance_ratio。
7. WHEN 生成段落之某一 citation_refs 法條於定稿內容中仍然出現，THE FeedbackCollector SHALL 為該法條產生正向 FeedbackEvent。
8. THE PreferenceModel SHALL 以指數移動平均 `w ← (1−η)·w + η·reward` 更新權重，且 η 等於 0.2。
9. THE PreferenceModel SHALL 使全部 PreferenceWeight.weight 落於 [0.0, 1.0] 區間。
10. WHEN FeedbackEvent 之 action 為「採納」或「整段保留」，THE PreferenceModel SHALL 使對應權重不低於更新前之值。
11. WHEN FeedbackEvent 之 action 為「排除」、「標記不相關」或「整段刪除」，THE PreferenceModel SHALL 使對應權重不高於更新前之值。
12. WHEN FeedbackEvent 之 action 為「編輯」，THE PreferenceModel SHALL 以 `1 − edit_distance_ratio` 作為 reward 值。
13. WHEN 同一 event_id 之 FeedbackEvent 被重複套用，THE PreferenceModel SHALL 產生與單次套用相同之權重結果。
14. IF 查詢之 `(case_type, issue_tag, item_id)` 組合尚無累積樣本，THEN THE PreferenceModel SHALL 回傳中性權重 0.5。
15. WHEN 定稿段落之 edit_distance_ratio 不高於範例池門檻，THE ExemplarPool SHALL 將該段落登錄為 few-shot 候選範例，並依 case_type 與 issue_tag 分群保留最近 N 筆。
16. THE FeedbackCollector SHALL 使每一 FeedbackEvent 僅含代號與識別碼，且序列化結果通過殘留掃描。
17. THE FeedbackCollector SHALL 僅就 generated 等於 True 之段落產生段落級學習訊號。
18. WHEN PreferenceModel 完成權重更新，THE PreferenceModel SHALL 使 PreferenceWeight.sample_count 恰增加 1。
19. WHEN 後續案件執行法規推薦或相似案例比對，THE LegalRetriever 與 THE PrecedentMatcher SHALL 自 FeedbackStore 讀取偏好權重並納入重排分數。

### Requirement 10: 成效指標與可觀測性

**User Story:** 作為訴願審議業務主管，我想要看到採納率、平均編輯距離與平均定稿時間之趨勢，以便驗證 AI 輔助確實提升行政效能。

#### Acceptance Criteria

1. THE Petition_AI_System SHALL 計算並提供 citation_accept_rate、precedent_accept_rate、mean_edit_distance_ratio、mean_time_to_finalize_s 與 case_count 五項 OptimizationMetrics。
2. WHEN 承辦人員開啟成效分頁，THE Workbench_UI SHALL 以趨勢圖呈現指定時間窗內之 OptimizationMetrics。
3. WHILE 同一 case_type 之回饋事件持續累積，THE Petition_AI_System SHALL 使 mean_edit_distance_ratio 之移動平均呈非上升趨勢，並以離線回放腳本評估該趨勢。
4. THE Petition_AI_System SHALL 提供離線回放腳本，比較啟用與停用回饋權重兩種設定下之 Recall@5 與 MRR 數值。
5. WHERE Petition_AI_System 寫入 CloudWatch 日誌，THE Petition_AI_System SHALL 於寫入前執行個資遮蔽。
6. THE Petition_AI_System SHALL 保留稽核軌跡，記錄被採納之建議識別碼、草稿修改內容差異與定稿操作者代號。
7. WHEN 單一案件流程結束，THE Petition_AI_System SHALL 記錄該案件實際使用之 Bedrock 呼叫次數，供效能預算檢視。

### Requirement 11: 操作介面與工作階段持續性

**User Story:** 作為承辦人員，我想要在單一介面完成從匯入到匯出之全部作業，並在頁面中斷後能續作，以便不因技術問題重做已完成之工作。

#### Acceptance Criteria

1. THE Workbench_UI SHALL 提供「案件匯入」、「案件資訊」、「法規與案例」、「草稿」與「成效」共 5 個分頁。
2. THE Workbench_UI SHALL 以 server_name 等於 `127.0.0.1` 且 share 等於 False 啟動 Gradio 服務。
3. THE Workbench_UI SHALL 限制上傳副檔名為 `.pdf`、`.docx` 與 `.txt`，並套用單檔大小上限與單次上傳總量上限。
4. WHILE Petition_AI_System 執行需等待 Bedrock 回應之階段，THE Workbench_UI SHALL 以進度元件逐階段更新目前處理狀態。
5. WHEN 法規推薦與相似案例結果產出，THE Workbench_UI SHALL 先行顯示該兩項結果，並使草稿生成於背景排隊執行。
6. THE Workbench_UI SHALL 以 case_id 為鍵，將去識別化文件、擷取結果與草稿持久化於本機 `./.local/sessions/`。
7. IF Gradio 工作階段狀態遺失，THEN THE Workbench_UI SHALL 於重新啟動時列出未完成案件供承辦人員續作。
8. WHEN 承辦人員續作已加密之案件，THE Workbench_UI SHALL 要求輸入本機金鑰口令後方載入 RedactionMap。
9. WHEN 承辦人員匯出草稿，THE Workbench_UI SHALL 正規化匯出檔案路徑，使匯出目標限定於設定之 exports 目錄內。
10. WHERE Petition_AI_System 需供多人使用，THE Petition_AI_System SHALL 將 Gradio 服務置於 ALB 與身分提供者驗證之後，並使 EC2 Security Group 之入向來源限定為該 ALB 之安全群組。

### Requirement 12: Bedrock 速率限制與韌性

**User Story:** 作為參賽團隊技術負責人，我想要系統嚴格遵守 Bedrock 每秒 1 請求之限制並在受限時仍可用，以便符合競賽規範且不因節流造成流程整體失敗。

#### Acceptance Criteria

1. THE RateLimiter SHALL 使任意 1 秒滑動窗內對 Bedrock 端點之請求數不超過 1，且 refill_interval 不小於 1.05 秒。
2. THE Petition_AI_System SHALL 使全部 Bedrock 與 Knowledge Base 呼叫皆經由 BedrockGateway，且 `bedrock-runtime` 與 `bedrock-agent-runtime` 之 boto3 client 建立僅出現於 BedrockGateway 之初始化程式碼。
3. WHILE RateLimiter 等待可用 token，THE RateLimiter SHALL 於未持有鎖之狀態下分段睡眠，且單次睡眠不超過 0.25 秒。
4. IF RateLimiter 之等待時間將超過指定 timeout_s，THEN THE RateLimiter SHALL 拋出 RateLimitTimeout 且消耗之 token 數為 0。
5. IF Bedrock 回傳 ThrottlingException 或 ServiceUnavailableException，THEN THE BedrockGateway SHALL 以指數退避加 jitter 重試，且重試次數上限為 5 次。
6. IF 重試次數達 5 次上限，THEN THE Petition_AI_System SHALL 將該子任務標記為 PENDING、提供重試操作，並使其餘已完成結果照常呈現。
7. WHEN Petition_AI_System 啟動，THE PreflightChecker SHALL 驗證設定檔中每一 model_id 之可用性，並於介面顯示檢查結果與後續指引。
8. IF PreflightChecker 判定無可用之生成模型，THEN THE Petition_AI_System SHALL 以僅檢索模式啟動，保留法規推薦與相似案例功能並停用草稿生成功能。
9. THE Petition_AI_System SHALL 使單一案件自擷取至草稿生成之 Bedrock 呼叫次數落於 7 至 10 次之範圍。
10. WHILE Knowledge Base ingestion 作業進行中，THE KBSync SHALL 以 5 秒間隔輪詢作業狀態，並於逾時回報失敗檔案清單與錯誤原因。
11. THE KBSync SHALL 提供本機 metadata 驗證器，於上傳前檢查 metadata JSON 之格式與必要欄位。
12. THE Petition_AI_System SHALL 為法規庫與先例庫建立 2 個獨立 Knowledge Base，並使各自之 data source 指向 S3 之 `law/` 與 `precedent/` 前綴。

### Requirement 13: AWS 安全與競賽合規

**User Story:** 作為參賽團隊技術負責人，我想要系統之 AWS 資源設定與版控實務全數符合競賽規範，以便交付成果不因合規瑕疵被扣分或取消資格。

#### Acceptance Criteria

1. THE Petition_AI_System SHALL 於帳戶層級與 bucket 層級同時啟用 S3 Block Public Access 之 4 項設定。
2. THE Petition_AI_System SHALL 以客戶管理之 KMS 金鑰對 S3 內容啟用 SSE-KMS 加密，並啟用版本控制與存取日誌。
3. THE Petition_AI_System SHALL 將部署區域限定為 `us-east-1` 或 `us-west-2`，且該區域由設定檔指定。
4. THE Petition_AI_System SHALL 使 OpenSearch Serverless 集合採私有網路存取設定。
5. THE Petition_AI_System SHALL 使 EC2 Security Group 之入向規則來源限定為 ALB 安全群組或 SSM Session Manager 端點。
6. THE Petition_AI_System SHALL 以 DynamoDB 作為回饋事件、偏好權重與範例池之雲端儲存後端。
7. THE Petition_AI_System SHALL 僅申請 1 個文字嵌入模型與 1 個生成模型之 Bedrock 存取權，並將 model_id 置於環境變數。
8. THE Petition_AI_System SHALL 以 IAM Role 或 SSO 短期憑證存取 AWS 服務，並使 IAM 政策限定於所需之 model ARN、Knowledge Base ARN、S3 前綴與 DynamoDB 表。
9. THE Petition_AI_System SHALL 使 `.gitignore` 包含 `.env`、`.env.*`、`.local/`、`inbox/`、`exports/`、`*.pem` 與 `__pycache__/`。
10. THE Petition_AI_System SHALL 使 `.kiro/` 及其子目錄納入版本控制，並使 `.gitignore` 之內容不匹配 `.kiro/` 路徑。
11. IF 機密掃描於待提交內容中發現憑證，THEN THE ComplianceTestSuite SHALL 判定測試失敗並回報命中檔案。
12. THE Petition_AI_System SHALL 僅以指數移動平均權重更新與提示詞範例池達成優化，使優化過程所需之模型訓練作業數為 0。
13. THE ComplianceTestSuite SHALL 驗證收尾檢核清單全部項目，涵蓋公開存取設定、部署區域、Bedrock 速率、模型存取權範圍與個資外送共 5 類檢查。
14. THE Petition_AI_System SHALL 使 EC2 與 SageMaker AI 執行個體數量限於必要工作所需，並於設定檔記錄使用中之執行個體清單。

### Requirement 14: 開發流程與階段交付

**User Story:** 作為專案負責人，我想要每個實作階段完成即建立 git commit，以便交付歷程可追溯且完整展示 Kiro specs、hooks 與 steering 之使用情況。

#### Acceptance Criteria

1. THE DeliveryProcess SHALL 將實作切分為 P0 至 P10 共 11 個階段，且每一階段具備明確之完成條件。
2. WHEN 任一階段之完成條件全部達成，THE DeliveryProcess SHALL 建立 1 次 git commit。
3. THE DeliveryProcess SHALL 使每一階段 commit 訊息包含類型前綴 `feat`、`chore`、`fix`、`test` 或 `docs`，並附階段目的之中文描述。
4. WHEN 建立階段 commit，THE DeliveryProcess SHALL 於同一 commit 內包含該階段之實作程式碼與對應測試程式碼。
5. THE DeliveryProcess SHALL 依 P0 → P1 與 P2 → P3 → P4 → P5 與 P6 → P7 → P8 → P9 → P10 之依賴順序執行階段。
6. IF 階段完成條件未全部達成，THEN THE DeliveryProcess SHALL 保留該階段為進行中狀態並延後該階段 commit。
7. WHEN 專案推送至公開儲存庫，THE DeliveryProcess SHALL 確認 `.kiro/` 資料夾存在於專案根目錄且已納入版本控制。
8. THE DeliveryProcess SHALL 使單元測試整體覆蓋率達 80%，且使去識別化模組與速率限制模組達 100% 分支覆蓋。
9. WHILE 持續整合流程執行測試，THE DeliveryProcess SHALL 以測試替身隔離 AWS 相依，使測試對真實 Bedrock 端點之請求數為 0。
10. THE DeliveryProcess SHALL 以黃金檔案測試比對草稿之段落存在性、段落順序與教示規定內容，使模型輸出變動不造成測試脆弱。
