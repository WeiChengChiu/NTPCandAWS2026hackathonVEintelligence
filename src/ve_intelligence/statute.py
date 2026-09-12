"""法規條文解析與「引用條次是否仍存在」檢查。

為什麼需要這一支：
    承辦人引用到已經刪除或移列的條次，是實質的被撤銷風險。最典型的例子是
    洗錢防制法第 15 條之 2 於 113/7/31 修法後移列為第 22 條——舊決定書引用
    §15-2，拿今天的法規去對照會查無此條。

    原本的做法是把這個例子寫死在 prompt 裡（見 prompts/draft_decision.md），
    等於是「告訴模型答案」。本模組改成從語料實際比對，任何法規、任何條次都適用。

資料來源：
    build/corpus/statute/*.txt，每份的格式是

        法規名稱：噪音管制法
        修正日期：民國114年12月26日
        第一章總則
        第1條
        為維護國民健康…

    條號行（``第N條``）可靠，但 PDF 版面會讓「條號」與「條文內容」錯位，
    所以本模組只信任條號清單，不宣稱能取出條文全文。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# 法規檔的條號行用連字號寫增訂條文：``第77條`` / ``第77-1條``。
# （實測 build/corpus/statute/ 一律是這個格式，不是「第77條之1」。）
ARTICLE_LINE = re.compile(r"^第([0-9]+(?:-[0-9]+)?)條", re.MULTILINE)
LAW_NAME = re.compile(r"法規名稱：(\S+)")
AMEND_DATE = re.compile(r"修正日期：(\S+)")

# 決定書內文的引用寫法與法規檔不同，是「第七十七條之三」「第15條之2」（條在前、之在後），
# 且可能列舉（第48、72、73、74條）。兩種數字系統都要吃。
#
# ⚠️ PDF 版面會在數字中間插入假空白（「第1 5條」其實是第15條），所以數字群組允許空白，
#    但切分列舉時**只以頓號逗號為界**，切完才去掉空白——用空白切會把「1 5」拆成第1條和第5條，
#    憑空捏造出兩筆不存在的引用。
CITATION = re.compile(
    r"([一-鿿]{2,20}?法(?:施行細則|規則)?)"
    r"\s*第\s*([0-9一二三四五六七八九十百零、，,\s]+?)\s*條"
    r"(?:\s*之\s*([0-9一二三四五六七八九十百零]+))?"
)

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

# 引用前常見的贅字，會被 CITATION 的法規名稱群組一起吃進去，需剝除。
_NAME_PREFIXES = ("依同法", "按同法", "次按", "揆諸", "此觀", "爰依", "併依", "復按",
                  "依據", "違反", "按照", "依照", "本件", "首揭", "上開", "前揭",
                  "按", "依", "爰", "查", "又", "而", "及", "與", "或", "暨")


def cn_to_int(s: str) -> int | None:
    """把「七十七」「一百十五」這類中文數字轉成整數；純阿拉伯數字直接回傳。"""
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)

    total, section, seen = 0, 0, False
    for ch in s:
        if ch in _CN_DIGITS:
            section = _CN_DIGITS[ch]
            seen = True
        elif ch == "十":
            section = (section or 1) * 10
            total += section
            section = 0
            seen = True
        elif ch == "百":
            section = (section or 1) * 100
            total += section
            section = 0
            seen = True
        else:
            return None
    return (total + section) if seen else None


def normalize_article(token: str, suffix: str | None = None) -> str | None:
    """把條號正規化成法規檔的寫法：``"77"`` / ``"77-1"``。

    ``token`` 是「條」之前的數字（可能是中文數字，也可能夾雜 PDF 假空白），
    ``suffix`` 是「條之N」的 N。回傳格式刻意對齊 ``ARTICLE_LINE`` 抽出的鍵。
    """
    n = cn_to_int(re.sub(r"\s+", "", token))
    if n is None:
        return None
    if suffix is None:
        return str(n)
    s = cn_to_int(re.sub(r"\s+", "", suffix))
    return f"{n}-{s}" if s is not None else str(n)


def format_article(article: str) -> str:
    """把內部鍵值還原成人看的寫法：``"77-1"`` → ``"第77條之1"``。"""
    head, sep, tail = article.partition("-")
    return f"第{head}條之{tail}" if sep else f"第{head}條"


def clean_law_name(name: str) -> str:
    """剝掉引用前的贅字（「按訴願法」→「訴願法」）。"""
    for _ in range(3):          # 可能疊兩層，如「次按行政程序法」
        for p in _NAME_PREFIXES:
            if name.startswith(p) and len(name) > len(p) + 1:
                name = name[len(p):]
                break
        else:
            break
    return name


@dataclass(slots=True)
class Statute:
    """一部法規的現行狀態。"""

    name: str
    amend_date: str
    articles: set[str] = field(default_factory=set)

    def has(self, article: str) -> bool:
        return article in self.articles


@dataclass(slots=True)
class Citation:
    """決定書裡的一次法條引用。"""

    law: str
    article: str
    doc_id: str
    raw: str


@dataclass(slots=True)
class StaleCitation:
    """引用到現行法規中查無此條的條次。"""

    law: str
    article: str
    doc_id: str
    amend_date: str
    raw: str


def load_statutes(corpus_dir: str | os.PathLike) -> dict[str, Statute]:
    """讀入 ``corpus/statute/`` 下所有法規。鍵是法規名稱。"""
    out: dict[str, Statute] = {}
    for path in sorted(Path(corpus_dir).glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        name = (LAW_NAME.search(text) or [None, path.stem])[1] if LAW_NAME.search(text) else path.stem
        date = m.group(1) if (m := AMEND_DATE.search(text)) else "未載"
        out[name] = Statute(name=name, amend_date=date,
                            articles=set(ARTICLE_LINE.findall(text)))
    return out


def extract_citations(text: str, doc_id: str, known_laws: set[str]) -> list[Citation]:
    """從決定書內文抽出法條引用。

    只保留 ``known_laws`` 裡有的法規——我們無法驗證語料中沒有的法規，
    硬報結果只會製造假警訊。
    """
    found: list[Citation] = []
    for law_raw, arts_raw, suffix in CITATION.findall(text):
        law = clean_law_name(law_raw)
        if law not in known_laws:
            continue
        # 只以頓號／逗號切分；不可用空白切（見 CITATION 的說明）。
        tokens = [t for t in re.split(r"[、，,]", arts_raw) if t.strip()]
        for i, token in enumerate(tokens):
            # 「第77條之3」的之3 只屬於最後一個條號，列舉中的前幾個不帶後綴。
            sfx = suffix if (suffix and i == len(tokens) - 1) else None
            art = normalize_article(token, sfx)
            if art:
                found.append(Citation(law=law, article=art, doc_id=doc_id,
                                      raw=f"{law}{format_article(art)}"))
    return found


def find_stale(citations: list[Citation], statutes: dict[str, Statute]) -> list[StaleCitation]:
    """找出引用到「現行法規查無此條」的條次。"""
    stale: list[StaleCitation] = []
    for c in citations:
        st = statutes.get(c.law)
        if st and not st.has(c.article):
            stale.append(StaleCitation(law=c.law, article=c.article, doc_id=c.doc_id,
                                       amend_date=st.amend_date, raw=c.raw))
    return stale
