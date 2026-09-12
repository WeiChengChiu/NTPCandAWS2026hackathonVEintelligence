"""掃描歷史決定書，找出引用到「現行法規已查無此條」的條次。

這支不需要 AWS，純本機批次，結果可直接交給法制局承辦人。

用法：
    python scripts/check_citations.py
    python scripts/check_citations.py --corpus ../build/corpus --out 報告.md
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from ve_intelligence.statute import (  # noqa: E402
    extract_citations,
    find_stale,
    format_article,
    load_statutes,
)

DEFAULT_CORPUS = pathlib.Path(__file__).resolve().parents[2] / "build" / "corpus"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="檢查決定書引用的條次是否仍存在於現行法規。")
    p.add_argument("--corpus", default=str(DEFAULT_CORPUS), help="corpus 目錄（含 statute/ 與 decision/）")
    p.add_argument("--out", default=None, help="輸出 Markdown 報告的路徑")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    corpus = pathlib.Path(args.corpus)
    statute_dir, decision_dir = corpus / "statute", corpus / "decision"
    if not statute_dir.is_dir() or not decision_dir.is_dir():
        print(f"找不到語料：{corpus}（需要 statute/ 與 decision/ 子目錄）", file=sys.stderr)
        return 1

    statutes = load_statutes(statute_dir)
    print(f"載入 {len(statutes)} 部法規：")
    for st in statutes.values():
        print(f"   {st.name:<24} {st.amend_date:<14} {len(st.articles):>4} 條")

    known = set(statutes)
    all_citations, stale = [], []
    decisions = sorted(decision_dir.glob("*.txt"))
    for path in decisions:
        text = path.read_text(encoding="utf-8", errors="ignore")
        cites = extract_citations(text, path.stem, known)
        all_citations += cites
        stale += find_stale(cites, statutes)

    print(f"\n掃描 {len(decisions)} 份決定書，抽出 {len(all_citations)} 筆可驗證引用。")

    if not stale:
        print("✅ 沒有引用到已失效的條次。")
        if args.out:
            pathlib.Path(args.out).write_text("# 條次時效檢查\n\n未發現失效引用。\n", encoding="utf-8")
        return 0

    by_article = collections.Counter((s.law, s.article) for s in stale)
    affected = {s.doc_id for s in stale}
    print(f"\n🔴 {len(stale)} 筆引用到現行法規查無此條，涉及 {len(affected)} 份決定書：\n")
    for (law, art), n in by_article.most_common():
        st = statutes[law]
        docs = sorted({s.doc_id for s in stale if s.law == law and s.article == art})
        print(f"   {law}{format_article(art)}  ← 引用 {n} 次／{len(docs)} 份")
        print(f"      現行版本 {st.amend_date}，共 {len(st.articles)} 條，查無此條")
        for d in docs[:3]:
            print(f"      · {d}")
        if len(docs) > 3:
            print(f"      · …另 {len(docs) - 3} 份")

    if args.out:
        lines = [
            "# 歷史訴願決定書：引用條次時效檢查",
            "",
            f"掃描 {len(decisions)} 份決定書、{len(statutes)} 部法規，"
            f"抽出 {len(all_citations)} 筆可驗證引用。",
            "",
            f"**發現 {len(stale)} 筆引用到現行法規查無此條，涉及 {len(affected)} 份決定書。**",
            "",
            "> 「查無此條」代表該條次在現行版本中已刪除或移列。引用時應改以新條次表述，",
            "> 或載明「修正前第 N 條」，避免決定書因條次錯誤而生爭議。",
            "",
            "| 引用條次 | 次數 | 涉及份數 | 該法現行版本 | 現行條數 |",
            "|---|---:|---:|---|---:|",
        ]
        for (law, art), n in by_article.most_common():
            st = statutes[law]
            docs = {s.doc_id for s in stale if s.law == law and s.article == art}
            lines.append(f"| {law}{format_article(art)} | {n} | {len(docs)} | {st.amend_date} | {len(st.articles)} |")

        lines += ["", "## 逐件明細", ""]
        for (law, art), _ in by_article.most_common():
            docs = sorted({s.doc_id for s in stale if s.law == law and s.article == art})
            lines.append(f"### {law}{format_article(art)}")
            lines += [f"- {d}" for d in docs]
            lines.append("")

        lines += [
            "## 方法與限制",
            "",
            f"- 條次清單取自 `corpus/statute/` 的 {len(statutes)} 部法規，"
            "以行首 `第N條` 辨識，未依賴任何模型推論。",
            "- 只檢查語料中有的法規；引用到語料外法規者一律略過，以免產生假警訊。",
            "- 「查無此條」不等於該規範已廢止——條文可能只是**移列**到新條次"
            "（如洗錢防制法第 15 條之 2 於 113/7/31 移列為第 22 條）。",
            "- 本檢查不判斷新舊條次的對應關係，該對應需人工或另行比對法規沿革。",
        ]
        pathlib.Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n✅ 報告已寫入 {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
