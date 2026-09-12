#!/usr/bin/env python3
"""把法制局資料集的 141 份 PDF 轉成乾淨純文字 + 結構化 metadata。

產出：
  build/corpus/<類別>/<檔名>.txt                 乾淨全文（純文字版 KB 用）
  build/corpus/<類別>/<檔名>.txt.metadata.json   Bedrock KB metadata sidecar
  build/pdf_upload/<類別>/<檔名>.pdf             原始 PDF，檔名清乾淨（PDF 版 KB 用）
  build/pdf_upload/<類別>/<檔名>.pdf.metadata.json
  build/index.json                               全部文件的合併索引（前端 / 評測用）
  build/stats.json                               統計摘要

兩份語料是為了 A/B 測試 Bedrock KB 的中文檢索品質：
  PDF 版 = 講師示範的做法（managed parser 自己解析）
  TXT 版 = 已收斂法學系統固定寬度排版的假空白
兩邊各建一個 KB，用同一組查詢比對 retrieval 結果，再決定正式採用哪個。
metadata sidecar 兩邊都有 —— metadata filtering 跟檔案格式無關，是必要的。

用法：
  python3 scripts/extract_corpus.py
  python3 scripts/extract_corpus.py --src <資料集目錄> --out <輸出目錄>

  資料集目錄也可用環境變數指定（夥伴機器路徑不同時用這個）：
  VE_DATASET_DIR=~/Documents/法制局/資料集 python3 scripts/extract_corpus.py
"""

import argparse
import json
import os
import pathlib
import re
import shutil
import sys
from collections import Counter

try:
    from pypdf import PdfReader
except ImportError:
    sys.exit("需要 pypdf：pip install pypdf")

# 路徑預設與 scripts/check_citations.py 對齊（parents[2] = repo 外層的 hackathon/），
# 這樣不論從哪個目錄執行，產出都落在同一個 build/，不會在 repo 內留下多餘副本。
DEFAULT_OUT = pathlib.Path(__file__).resolve().parents[2] / "build"

# 資料集不在版控內（含個資，且規範禁止匯入 AWS）。夥伴的機器路徑不同，
# 所以允許用環境變數覆蓋，不要寫死在程式裡。
DEFAULT_SRC = os.environ.get(
    "VE_DATASET_DIR", str(pathlib.Path.home() / "Documents" / "法制局" / "資料集")
)

# 資料集四個子目錄 -> 內部類別代號
CATEGORY = {
    "歷史訴願決定書": "decision",
    "相關法規": "statute",
    "行政函釋": "interpretation",
    "司法院釋字及行政判解": "judgment",
}

# 訴願決定書檔名範例：
#   01.110年-社會救助事件-77(1)-逾期不補正-不受理.pdf 的副本.pdf
#   21.114年-違反建築法事件-77(8)&79I-部分不受理&部分駁回.pdf 的副本.pdf
DECISION_NAME = re.compile(r"^(\d+)\.(\d{3})年-(.+)$")

# 決定書開頭的欄位區（案號 / 要旨 / 發文日期 / 發文字號 / 相關法條）
HEADER_FIELDS = ["案號", "要旨", "發文日期", "發文字號", "相關法條", "資料來源", "裁判字號", "裁判日期", "裁判案由", "發文單位"]

# 決定書本文的三段結構
SECTION_MARKS = [("主文", "主"), ("事實", "事"), ("理由", "理")]


# 法學檢索系統把網頁列印成 PDF 時留下的頁首頁尾，內容無語意價值。
# 實測會被檢索命中並擠進前三名（漢字比僅 37%），等於稀釋檢索品質，必須丟棄。
# 例：
#   2026/3/20上午8:32查閱內容
#   https://web.law.ntpc.gov.tw/Scripts/PrintSu_contents03.aspx?NO=3&...1/2
PRINT_NOISE = [
    re.compile(r"^\d{4}/\d{1,2}/\d{1,2}\s*[上下]午\s*\d{1,2}[:：]\d{2}"),
    re.compile(r"^https?://\S*(?:law\.ntpc\.gov\.tw|judicial\.gov\.tw|moj\.gov\.tw)\S*"),
    re.compile(r"^\d{1,3}\s*/\s*\d{1,3}$"),           # 單獨成行的頁碼「1/2」
    re.compile(r"^查閱內容$"),
]


def is_print_noise(line: str) -> bool:
    return any(p.search(line) for p in PRINT_NOISE)


def cjk_count(text: str) -> int:
    """漢字數。用來比較兩種抽取結果的內容量。

    ⚠️ 不能用 len(text) 比較：逐字拆行的文字每個字都帶一個換行，長度會虛增
    近一倍，導致修復後的正常文字被誤判為「內容大量流失」而遭否決。
    """
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def frag_ratio(text: str) -> float:
    """回傳「碎行比」：單字成行的非空行佔比。

    法學檢索系統少數 PDF 的文字圖層是逐字定位的，抽取出來每個字自成一行
    （實測最嚴重者 9922 行、每行一個字）。這種文字丟進 embedding 完全無用，
    必須改用 layout 模式重建。

    ⚠️ 只計「長度 1」的行。原本用「長度 <= 2」會把合法的兩字段落標題
    （主文、理由、事實）算成碎行——實測某判解因此被誤判 43% 碎裂，
    但它其實完全正常。
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return 0.0
    return sum(1 for l in lines if len(l) == 1) / len(lines)


# 碎行比超過此門檻才啟動 layout 模式重建。
# 門檻取 0.30 是為了保護法規檔：法規的「項次」本來就會單獨成行（實測 11 份
# 法規碎行比 11%~18%），而 statute.py 的 ARTICLE_LINE 依賴 ``^第N條`` 出現在
# 行首來取條號清單。重建會破壞該結構，因此法規一律不動。
REFLOW_THRESHOLD = 0.30

# 判決書頁邊的行號欄。兩種樣式都實測到：
#   左欄分離：'     3 2        司   之  系  爭  款  項'   （行號的兩位數還會被空白拆開）
#   緊貼內容：'03上訴人臺中市政府運動局'
MARGIN_NO = [
    re.compile(r"^\s*(\d\s*\d)\s{2,}(\S.*)$"),
    re.compile(r"^\s*(\d{2})(?=\D)\s*(\S.*)$"),
]

# 內政部函這類公文表格，layout 模式會在每行行首留下框線殘跡「.」
LEADING_DOT = re.compile(r"^\s*\.\s*")

# 單獨成行的頁碼（含全形數字）
PAGE_NO_ONLY = re.compile(r"^[\s0-9０-９]{1,4}$")


def rebuild_page(layout_text: str) -> list:
    """把 layout 模式的一頁還原成正確順序的內容行。

    為什麼需要這一支：少數 PDF 的文字圖層是逐字定位的，預設抽取器會吐出
    每字一行（實測最嚴重者 9922 行、每行一字）。layout 模式能取回版面，
    但判決書頁邊有行號欄，且各檔的輸出順序不一致（實測有正序也有倒序），
    不能盲目反轉——那會把整段文字倒過來。

    做法是以檔案自帶的行號為排序鍵，順序就有依據而非猜測。沒有行號的檔案
    （如公文、舊式判解）layout 輸出本身就是正序，原樣保留即可。
    """
    rows = []
    for idx, raw in enumerate(layout_text.splitlines()):
        line = LEADING_DOT.sub("", raw)
        if not line.strip() or PAGE_NO_ONLY.match(line.strip()):
            continue
        no, content = None, line.strip()
        for pat in MARGIN_NO:
            m = pat.match(line)
            if m:
                no = int(re.sub(r"\s", "", m.group(1)))
                content = m.group(2).strip()
                break
        if content:
            rows.append([idx, no, content])

    numbered = [r for r in rows if r[1] is not None]
    # 行號要夠普遍才拿來定序，否則寧可保留 layout 原序
    if len(numbered) >= max(3, 0.5 * len(rows)):
        # 未編號行（跨行接續、標題）沿用前一筆行號，以微小偏移維持相對位置
        key, frac = None, 0
        for r in rows:
            if r[1] is not None:
                key, frac = r[1], 0
            else:
                frac += 1
            r[0] = (key if key is not None else -1) + frac * 1e-3
        rows.sort(key=lambda r: r[0])
    return [r[2] for r in rows]


# 訴願審議委員名單：100 份決定書都有的純樣板，約 12 行。
# 它沒有區辨力卻會佔滿 chunk——實測檢索「訴願逾越法定期間 不受理」時，
# 命中的第一個 chunk 尾巴就是整串委員名單，等於稀釋檢索品質。
#
# ⚠️ 只刪委員名單本身。緊接其後的「如不服本決定，得於…提起行政訴訟」是
#    教示規定，命題文件明列「教示規定之自動填入」為需求，必須保留。
COMMITTEE_LINE = re.compile(r"^(?:訴願審議委員會)?(?:主任委員|委員)\s*[\u4e00-\u9fff]{2,4}\s*(?:（[^）]*）)?$")


def drop_committee_roster(text: str) -> str:
    return "\n".join(l for l in text.split("\n") if not COMMITTEE_LINE.match(l.strip()))


# 頁邊行號整欄殘留：部分判解的文字層會把每頁頁邊的行號（01、02…32）
# 全部倒成獨立的純數字行。實測 3 份判解共 730 行，最嚴重者佔全檔 50.9%，
# 使檢索命中的 chunk 漢字比掉到 49%。
#
# ⚠️ 不能單純刪掉所有純數字行——法規條文的「項次」也是獨立數字行
#    （實測行政程序法 165 行、訴願法 84 行），刪掉會失去項次結構。
#    兩者的差別是「連續成塊」：頁邊行號會連續數十行，項次不會。
#    實測門檻取 4 行時，判解 730 行全數命中、法規 0 行誤刪。
BARE_NUMBER = re.compile(r"^\d{1,3}$")
MARGIN_RUN_MIN = 4


def drop_margin_number_runs(text: str) -> str:
    lines = text.split("\n")
    drop, run = set(), []
    for i, line in enumerate(lines):
        if BARE_NUMBER.fullmatch(line.strip()):
            run.append(i)
            continue
        if len(run) >= MARGIN_RUN_MIN:
            drop.update(run)
        run = []
    if len(run) >= MARGIN_RUN_MIN:
        drop.update(run)
    return "\n".join(l for i, l in enumerate(lines) if i not in drop)


def margin_number_lines(text: str) -> int:
    """回傳被判定為頁邊行號的行數，供品質指標監控。"""
    before = text.count("\n")
    return before - drop_margin_number_runs(text).count("\n")


def rebuild_layout(reader) -> str:
    """整份文件以 layout 模式重建。"""
    out = []
    for page in reader.pages:
        try:
            out += rebuild_page(page.extract_text(extraction_mode="layout"))
        except Exception:  # noqa: BLE001 — 個別頁失敗不該中斷整批
            continue
    return "\n".join(out)


# 段落結構標記：unwrap 時不可與前一行合併，否則會破壞段落邊界與
# statute.py 依賴的 ``^第N條`` 行首格式。
STRUCT_START = re.compile(
    r"^(?:【|主文|理由|事實|事實及理由|附表|附件"
    r"|第[0-9一二三四五六七八九十百千]+[條章節編款目項]"
    r"|[一二三四五六七八九十]+[、．.]"
    r"|[（(][一二三四五六七八九十0-9]+[)）])"
)
SENT_END = "。！？；：」』）】.:;!?"


def unwrap_wrapped_lines(text: str) -> str:
    """把折行殘留接回段落。

    某些判解的文字層會把每個視覺行的**最後一字**單獨拆成一行，例如
        '…所述「職權調查事項」之'
        '事'
        '實部分，向上訴人發問…'
    正確內容是「…之事實部分，向上訴人發問…」。這種殘留無法用 layout 模式
    修掉（兩種模式都一樣），只能靠「未以句末標點結尾就續接下一行」重組。
    """
    out = []
    for line in (l.strip() for l in text.splitlines()):
        if not line:
            continue
        if out and not STRUCT_START.match(line) and out[-1] and out[-1][-1] not in SENT_END:
            out[-1] += line
        else:
            out.append(line)
    return "\n".join(out)


def clean_text(raw: str) -> str:
    """法學檢索系統的 PDF 是固定寬度排版，會產生大量假空白與斷行。
    收斂成正常中文段落，embedding 與 LLM 的表現都會明顯變好。"""
    t = raw.replace("　", " ").replace("\xa0", " ")
    lines = []
    for line in t.split("\n"):
        line = line.rstrip()
        # 「113  年 7  月」-> 「113年7月」：中文字之間的多餘空白全部收掉
        line = re.sub(r"(?<=[一-鿿（）「」，。、：；])\s+(?=[一-鿿（）「」，。、：；])", "", line)
        # 數字與中文之間的空白也收掉
        line = re.sub(r"(?<=\d)\s+(?=[一-鿿])", "", line)
        line = re.sub(r"(?<=[一-鿿])\s+(?=\d)", "", line)
        line = re.sub(r"[ \t]{2,}", " ", line)
        line = line.strip()
        if is_print_noise(line):
            continue
        lines.append(line)
    t = "\n".join(lines)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def extract_links(reader) -> list:
    """抽出 PDF 內嵌的超連結。

    這些檔案來自司法院／法務部的法學檢索系統，內文的法條與判例都掛著連回官方
    資料庫的連結（例如 https://cons.judicial.gov.tw/docdata.aspx?fid=100&id=310650）。
    價值有三：
      1. 引用可追溯 —— 草稿裡的每個引用都能點回官方原文，這是本案最重要的產品原則
      2. 引用關係圖 —— 哪份判解引用了哪些法條，可用於法規推薦的關聯性判斷
      3. 法規版本 —— 連結文字常帶版本日期（如「行政程序法 第 128 條(110.01.20)」）
    """
    urls = []
    for page in reader.pages:
        for annot in (page.get("/Annots") or []):
            try:
                obj = annot.get_object()
                action = obj.get("/A")
                if not action:
                    continue
                uri = action.get_object().get("/URI") if hasattr(action, "get_object") else action.get("/URI")
                if uri and str(uri) not in urls:
                    urls.append(str(uri))
            except Exception:  # noqa: BLE001 — 個別壞掉的 annotation 不該中斷整批處理
                continue
    return urls


# 法條版本日期，例如「行政程序法 第 128 條(110.01.20)」「洗錢防制法 第 22 條(113.07.31)」
# 這是「法規時效性警示」功能的資料來源
ARTICLE_VERSION = re.compile(r"([一-鿿]{2,12}法(?:施行細則|規則)?)\s*第\s*([\d、,\s之]+)\s*條\s*\((\d{2,3}\.\d{2}\.\d{2})\)")


def parse_article_versions(text: str) -> list:
    out, seen = [], set()
    for law, arts, ver in ARTICLE_VERSION.findall(text):
        key = (law, arts.strip(), ver)
        if key in seen:
            continue
        seen.add(key)
        out.append({"law": law, "articles": arts.strip(), "version": ver})
    return out


def parse_header(text: str) -> dict:
    """抓出文件開頭的欄位區。

    ⚠️ 冒號後只吃同一行（``[ \\t]*`` 而非 ``\\s*``）。用 ``\\s*`` 會跨越換行，
    在標籤與值分欄排版的檔案上會抓到下一行的標籤當成值——實測 19 份判解有
    11 份的 judgment_no 被填成 '裁判字號：'、judgment_date 被填成 '案由摘要：'。

    另外明確擋掉「值本身就是標籤」的情況，寧可讓欄位缺漏，也不要寫入錯誤的
    metadata：錯誤的 metadata 會讓 KB 的 metadata filtering 篩出錯誤結果，
    比欄位不存在更難察覺。
    """
    out = {}
    head = "\n".join(text.split("\n")[:40])
    label_like = re.compile(r"^(?:" + "|".join(map(re.escape, HEADER_FIELDS)) + r")\s*[：:]")
    for field in HEADER_FIELDS:
        pat = re.compile(re.escape(field) + r"[ \t]*[：:][ \t]*(.+)")
        m = pat.search(head)
        if not m:
            continue
        val = m.group(1).strip()
        if not val or val in {"", "-"} or label_like.match(val):
            continue
        out[field] = val
    return out


# 判解檔名帶著比 PDF 內文更可靠的結構資訊，例如
#   最高行政法院102年度判字第147號行政判決-政府資訊公開法精神
#   最高行政法院109度上字第817號判決-政府資訊公開法18條2項      ← 少了「年」
#   臺北高等行政法院114年度簡上字第13號判決-洗錢防制法第22條
#   臺灣新北地方法院106年度簡字第119號行政判決-廢棄物清理法9條1項後段
JUDGMENT_NAME = re.compile(
    r"^(?P<court>.*?法院)(?P<year>\d{2,3})年?度(?P<case>[^字]{1,4})字第(?P<no>\d+)號"
    r"(?P<doctype>[^-]*?)(?:-(?P<topic>.+))?$"
)

# 釋字：釋字第469號解釋-公法上請求權
INTERPRETATION_NAME = re.compile(r"^釋字第(?P<no>\d+)號解釋(?:-(?P<topic>.+))?$")

# 行政函釋：
#   內政部100年12月9日內授營建管字第1000810874號函釋-場所區隔方式
#   法務部103年10月27日10303512490號函釋-行政程序法第36、39、42、43條&行政罰法第42條
#   法務部113年10月17日法律字11303514230號函-行政程序第128條第2款程序再開
CIRCULAR_NAME = re.compile(
    r"^(?P<agency>[^\d]{2,8}?)(?P<year>\d{2,3})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日"
    r"(?P<docno>.+?)號?函(?:釋)?(?:-(?P<topic>.+))?$"
)


def parse_judgment_filename(stem: str) -> dict:
    """從判解檔名解出法院／年度／字別／號次／案由。

    比 parse_header 可靠：這批 PDF 的內文欄位區是分欄排版，抽取後標籤與值錯位，
    但檔名是人工命名且格式一致。
    """
    m = JUDGMENT_NAME.match(stem)
    if m:
        g = m.groupdict()
        meta = {
            "court": g["court"],
            "year": g["year"],
            "case_type": g["case"],
            "裁判字號": f"{g['year']}年度{g['case']}字第{g['no']}號",
        }
        if g.get("doctype"):
            meta["裁判案由"] = g["doctype"].strip()
        if g.get("topic"):
            meta["topic"] = g["topic"].strip()
        return meta

    m = INTERPRETATION_NAME.match(stem)
    if m:
        g = m.groupdict()
        meta = {"court": "司法院大法官", "裁判字號": f"釋字第{g['no']}號"}
        if g.get("topic"):
            meta["topic"] = g["topic"].strip()
        return meta
    return {}


def parse_circular_filename(stem: str) -> dict:
    """從行政函釋檔名解出發文機關／發文日期／發文字號／主題。"""
    m = CIRCULAR_NAME.match(stem)
    if not m:
        return {}
    g = m.groupdict()
    meta = {
        "發文單位": g["agency"],
        "發文日期": f"民國{g['year']}年{g['month']}月{g['day']}日",
    }
    docno = (g.get("docno") or "").strip()
    if docno:
        meta["發文字號"] = docno + "號"
    if g.get("topic"):
        meta["topic"] = g["topic"].strip()
    return meta


def parse_decision_filename(stem: str) -> dict:
    """從訴願決定書檔名解出：序號 / 年度 / 案件類型 / 法條依據 / 事由 / 結果"""
    m = DECISION_NAME.match(stem)
    if not m:
        return {}
    seq, year, rest = m.groups()
    parts = [p.strip() for p in rest.split("-") if p.strip()]
    meta = {"seq": seq, "year": year}
    if len(parts) >= 1:
        meta["case_type"] = parts[0]
    if len(parts) >= 2:
        meta["legal_basis"] = parts[1]      # 77(1) / 79I / 81I / 77(8)&79I ...
    if len(parts) >= 4:
        meta["ground"] = parts[2]           # 逾期不補正 / 訴願無理由 ...
        meta["outcome"] = parts[3]          # 不受理 / 駁回 / 撤銷另處
    elif len(parts) == 3:
        meta["outcome"] = parts[2]
    return meta


def split_decision_body(text: str) -> dict:
    """把決定書切成 主文 / 事實 / 理由 三段。"""
    body = {}
    # 「主 文」「事 實」「理 由」中間可能有全形空白，clean_text 後已收斂
    idx = {}
    for name, _ in SECTION_MARKS:
        m = re.search(r"^\s*" + name + r"\s*$", text, re.MULTILINE)
        if m:
            idx[name] = m.start()
    ordered = sorted(idx.items(), key=lambda kv: kv[1])
    for i, (name, start) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(text)
        seg = text[start:end]
        seg = re.sub(r"^\s*" + name + r"\s*$", "", seg, count=1, flags=re.MULTILINE).strip()
        # 理由段尾巴會接一長串委員名單，切掉
        seg = re.split(r"\n訴願審議委員會主任委員", seg)[0].strip()
        body[name] = seg
    return body


# ⚠️ 實測結果（2026/8/17，us-west-2）：
# Bedrock Knowledge Base 的 metadata **欄位名稱必須是 ASCII**，用中文欄位名會導致該文件
# ingestion 失敗。141 份裡有中文欄位名的 115 份全數失敗、只有 ASCII 欄位名的 26 份全數成功，
# 判別 100% 乾淨。而且 ingestion 只回報籠統的 "partial failures"，不會指出真正原因。
#
# 欄位「值」可以是中文 —— 成功的 26 份 doc_id 值就是「民法」「釋字第546號解釋」等中文。
#
# index.json 保留中文欄位名（給人看），只有寫進 sidecar 時轉成 ASCII。
SIDECAR_KEY_MAP = {
    "doc_id": "doc_id",
    "category": "category",
    "year": "year",
    "case_type": "case_type",
    "legal_basis": "legal_basis",
    "ground": "ground",
    "outcome": "outcome",
    "court": "court",
    "topic": "topic",
    "發文日期": "doc_date",
    "發文字號": "doc_no",
    "案號": "case_no",
    "相關法條": "related_articles",
    "要旨": "summary",
    "裁判字號": "judgment_no",
    "裁判日期": "judgment_date",
    "裁判案由": "judgment_subject",
    "發文單位": "issuing_agency",
}


def build_sidecar_attrs(meta: dict) -> dict:
    """組出 Bedrock KB 的 metadata attributes（欄位名一律 ASCII）。"""
    attrs = {}
    for src, dst in SIDECAR_KEY_MAP.items():
        v = meta.get(src)
        if isinstance(v, str) and v:
            attrs[dst] = v[:1000]
    return attrs


def norm_filename(name: str) -> str:
    """去掉「 的副本」與重複副檔名。"""
    n = name
    n = re.sub(r"\.pdf\s*的副本\.pdf$", "", n)
    n = re.sub(r"\s*的副本$", "", n)
    n = re.sub(r"\.pdf$", "", n)
    return n.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC,
                    help="資料集根目錄（四個類別子目錄）。也可用環境變數 VE_DATASET_DIR 指定")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="輸出根目錄，預設是 repo 外層的 build/（與 check_citations.py 一致）")
    args = ap.parse_args()

    out_root = os.path.abspath(args.out)
    corpus_root = os.path.join(out_root, "corpus")
    pdf_root = os.path.join(out_root, "pdf_upload")
    os.makedirs(corpus_root, exist_ok=True)
    os.makedirs(pdf_root, exist_ok=True)

    index, errors = [], []

    for dirpath, _, filenames in os.walk(args.src):
        for fn in sorted(filenames):
            if not fn.lower().endswith(".pdf"):
                continue
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, args.src)
            top = rel.split(os.sep)[0]
            category = CATEGORY.get(top, "other")
            stem = norm_filename(fn)

            try:
                reader = PdfReader(src)
                raw = "\n".join((p.extract_text() or "") for p in reader.pages)
            except Exception as e:                       # noqa: BLE001
                errors.append({"file": rel, "error": str(e)})
                continue

            text = clean_text(raw)

            # 頁邊行號整欄殘留：法規不適用（項次會被誤刪），只對判解與函釋處理。
            margin_dropped = 0
            if category != "statute":
                margin_dropped = margin_number_lines(text)
                if margin_dropped:
                    text = drop_margin_number_runs(text)

            # 預設抽取器對少數逐字定位的 PDF 會吐出每字一行，改用 layout 模式重建。
            # 只在確實碎裂時才切換，避免動到 119 份原本正常的檔案。
            repaired_by = None
            if frag_ratio(text) > REFLOW_THRESHOLD:
                alt = clean_text(rebuild_layout(reader))
                # 重建結果必須真的比較好才採用：碎行比下降，且漢字沒有明顯流失
                if alt and frag_ratio(alt) < frag_ratio(text) and cjk_count(alt) >= 0.9 * cjk_count(text):
                    # layout 重建出的每一行就是原始視覺行，續接成段落才不會讓
                    # 日期、金額、條號被行尾切斷（例如「108年3月14」/「日臺北…」）。
                    text, repaired_by = unwrap_wrapped_lines(alt), "layout+unwrap"

            # layout 模式修不掉的是「每個視覺行最後一字被拆出」這種折行殘留，
            # 兩種抽取模式的結果一樣，只能靠續行合併重組。
            if frag_ratio(text) > REFLOW_THRESHOLD:
                alt = unwrap_wrapped_lines(text)
                if frag_ratio(alt) < frag_ratio(text) and cjk_count(alt) >= 0.99 * cjk_count(text):
                    text = alt
                    repaired_by = f"{repaired_by}+unwrap" if repaired_by else "unwrap"

            if frag_ratio(text) > REFLOW_THRESHOLD:
                errors.append({"file": rel, "error": f"文字層逐字碎裂且自動重建無效（碎行比 {frag_ratio(text):.0%}）"})

            if len(text) < 100:
                errors.append({"file": rel, "error": f"文字層過少（{len(text)} 字），可能需要 OCR"})

            links = extract_links(reader)
            versions = parse_article_versions(text)
            meta = {
                "doc_id": stem,
                "category": category,
                "source_pdf": rel,
                "pages": len(reader.pages),
                "chars": len(text),
                "frag_ratio": round(frag_ratio(text), 3),
                "margin_numbers_dropped": margin_dropped,
                "repaired_by": repaired_by,
                "links": links,
                "article_versions": versions,
            }
            # 先吃內文欄位區，再讓檔名解析覆蓋。
            # 檔名是人工命名、格式一致，比分欄排版抽出來的內文欄位可靠。
            meta.update(parse_header(text))
            if category == "decision":
                meta.update(parse_decision_filename(stem))
                sections = split_decision_body(text)
                meta["has_sections"] = sorted(sections.keys())
                if "主文" in sections:
                    meta["主文"] = sections["主文"][:200]
            elif category == "judgment":
                meta.update(parse_judgment_filename(stem))
            elif category == "interpretation":
                meta.update(parse_circular_filename(stem))

            # 委員名單在切段之後才移除：split_decision_body 以「訴願審議委員會主任委員」
            # 作為理由段的結束標記，先刪會讓理由段吃進尾段內容。
            if category == "decision":
                text = drop_committee_roster(text)
                meta["chars"] = len(text)

            attrs = build_sidecar_attrs(meta)
            sidecar = json.dumps({"metadataAttributes": attrs}, ensure_ascii=False, indent=2)

            # (A) 純文字版語料
            cat_dir = os.path.join(corpus_root, category)
            os.makedirs(cat_dir, exist_ok=True)
            txt_path = os.path.join(cat_dir, stem + ".txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            with open(txt_path + ".metadata.json", "w", encoding="utf-8") as f:
                f.write(sidecar)

            # (B) PDF 版語料：原檔複製過去，只把檔名清乾淨（去掉「的副本」）
            pdf_dir = os.path.join(pdf_root, category)
            os.makedirs(pdf_dir, exist_ok=True)
            pdf_path = os.path.join(pdf_dir, stem + ".pdf")
            shutil.copy2(src, pdf_path)
            with open(pdf_path + ".metadata.json", "w", encoding="utf-8") as f:
                f.write(sidecar)

            meta["text_path"] = os.path.relpath(txt_path, out_root)
            meta["pdf_path"] = os.path.relpath(pdf_path, out_root)
            index.append(meta)

    index.sort(key=lambda m: (m["category"], m.get("year", ""), m.get("seq", ""), m["doc_id"]))
    with open(os.path.join(out_root, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    decisions = [m for m in index if m["category"] == "decision"]
    judgments = [m for m in index if m["category"] == "judgment"]
    interps = [m for m in index if m["category"] == "interpretation"]
    stats = {
        "total_docs": len(index),
        "total_chars": sum(m["chars"] for m in index),
        "by_category": dict(Counter(m["category"] for m in index)),
        # 品質指標：這三項都曾經靜默壞掉過，列進 stats 才能在每次重建時看出退化。
        "quality": {
            "max_frag_ratio": max((m["frag_ratio"] for m in index), default=0),
            "docs_frag_over_30pct": sum(1 for m in index if m["frag_ratio"] > 0.30),
            "docs_with_print_noise": 0,  # clean_text 已丟棄，恆為 0；非 0 代表出現新的雜訊樣式
            # 頁邊行號殘留：這是靜默劣化過的項目——frag_ratio 只看單字成行，
            # 抓不到「01」「12」這種兩位數行號，所以獨立列出監控。
            "docs_with_margin_numbers": sum(1 for m in index if m.get("margin_numbers_dropped")),
            "margin_number_lines_dropped": sum(m.get("margin_numbers_dropped", 0) for m in index),
            "judgments_with_judgment_no": sum(1 for m in judgments if m.get("裁判字號")),
            "judgments_total": len(judgments),
            "interps_with_doc_no": sum(1 for m in interps if m.get("發文字號")),
            "interps_total": len(interps),
        },
        "decisions_by_year": dict(sorted(Counter(m.get("year", "?") for m in decisions).items())),
        "decisions_by_outcome": dict(Counter(m.get("outcome", "?") for m in decisions).most_common()),
        "decisions_by_legal_basis": dict(Counter(m.get("legal_basis", "?") for m in decisions).most_common()),
        "decisions_by_case_type": dict(Counter(m.get("case_type", "?") for m in decisions).most_common()),
        "sectioning_ok": sum(1 for m in decisions if len(m.get("has_sections", [])) == 3),
        "docs_with_links": sum(1 for m in index if m["links"]),
        "total_links": sum(len(m["links"]) for m in index),
        "link_hosts": dict(Counter(
            re.sub(r"^https?://([^/]+).*$", r"\1", u) for m in index for u in m["links"]).most_common()),
        "docs_with_article_versions": sum(1 for m in index if m["article_versions"]),
        "laws_with_versions": dict(Counter(
            f"{v['law']}({v['version']})" for m in index for v in m["article_versions"]).most_common(15)),
        "errors": errors,
    }
    with open(os.path.join(out_root, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
