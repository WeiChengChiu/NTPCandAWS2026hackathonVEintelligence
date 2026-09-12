"""Central configuration. Everything is overridable by environment variable."""

import os

DEFAULT_REGION = os.getenv("VE_AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-west-2"))

# Bedrock knowledge base holding the 建築管理 / 公共安全檢查申報 corpus.
#
# 用 txt 版語料建的 KB（bucket: ntpc-suyuan-txt-446423139874），不是 PDF 版。
# 原本指向的 CMKZVQHAYB 是 console quick-start 建的 managed KB，直接餵 PDF，
# 實測檢索結果漢字比 0%——只撈到網頁列印的頁碼與時間戳（如 "2/2"、
# "1/2 2026/3/20 E'+8:32"），中文正文全被丟棄。
#
# 成因：managed KB 只能用 SMART_PARSING（AWS 文件明載 BEDROCK_FOUNDATION_MODEL
# 與 BEDROCK_DATA_AUTOMATION 皆不支援，且省略 parsingConfiguration 等於仍用
# SMART_PARSING），而該解析器處理這批 PDF 會丟掉中文。這批 PDF 是從
# web.law.ntpc.gov.tw 列印產生、內嵌 Type3 字型。
#
# 對策是繞過雲端解析：先在本機用 pypdf 抽文字（141/141 皆正常）產出
# build/corpus/*.txt，再以純文字建 KB。同一查詢下漢字比回到 65–84%。
DEFAULT_KB_ID = os.getenv("VE_KB_ID", "D4FH6JJ2YD")

# Agentic retrieval defaults.
DEFAULT_FOUNDATION_MODEL_TYPE = os.getenv("VE_KB_FM_TYPE", "MANAGED")
DEFAULT_MAX_AGENT_ITERATION = int(os.getenv("VE_KB_MAX_ITERATION", "5"))
