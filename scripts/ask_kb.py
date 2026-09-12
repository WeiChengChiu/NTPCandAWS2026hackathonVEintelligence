"""Query the VE Intelligence knowledge base from the terminal.

Examples:
    python scripts/ask_kb.py "停歇業建築物是否仍需辦理公安申報？"
    python scripts/ask_kb.py --mode retrieve --max-results 5 "公共安全檢查申報"
    python scripts/ask_kb.py --trace "申報期限規定"
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from botocore.exceptions import ClientError, NoCredentialsError  # noqa: E402

from ve_intelligence.kb import StreamEvent, default_client  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the Bedrock knowledge base.")
    parser.add_argument("query", help="Question or search phrase.")
    parser.add_argument(
        "--mode",
        choices=("agentic", "retrieve"),
        default="agentic",
        help="agentic = generated answer with citations; retrieve = raw chunks only.",
    )
    parser.add_argument("--max-results", type=int, default=5, help="retrieve mode: chunk count.")
    parser.add_argument("--max-iteration", type=int, default=5, help="agentic mode: agent steps.")
    parser.add_argument("--trace", action="store_true", help="Show agent planning steps.")
    return parser.parse_args()


def run_retrieve(client, args) -> int:
    chunks = client.retrieve(args.query, max_results=args.max_results)
    if not chunks:
        print("No results.")
        return 0
    for i, chunk in enumerate(chunks, 1):
        score = f"{chunk.score:.4f}" if chunk.score is not None else "n/a"
        print(f"\n[{i}] score={score}  source={chunk.source}")
        print(f"    {chunk.preview(400)}")
    return 0


def run_agentic(client, args) -> int:
    def on_trace(event: StreamEvent) -> None:
        if args.trace:
            print(f"  · [{event.step}/{event.status}] {event.text}", file=sys.stderr)

    print(f"Q: {args.query}\n")
    answer = client.ask(
        args.query,
        on_token=lambda t: print(t, end="", flush=True),
        on_trace=on_trace,
        max_agent_iteration=args.max_iteration,
    )

    print("\n")
    if answer.sources:
        print("Sources (unique documents):")
        for i, source in enumerate(answer.sources, 1):
            hits = sum(1 for c in answer.chunks if c.source == source)
            print(f"  {i}. {source}  ({hits} chunk{'s' if hits != 1 else ''})")
    print(f"\n({len(answer.chunks)} chunks, {len(answer.traces)} trace events)")
    return 0


def main() -> int:
    args = parse_args()
    client = default_client()
    print(f"KB={client.knowledge_base_id}  region={client.region_name}", file=sys.stderr)

    try:
        if args.mode == "retrieve":
            return run_retrieve(client, args)
        return run_agentic(client, args)
    except NoCredentialsError:
        print("No AWS credentials found. Refresh ~/.aws/credentials [default].", file=sys.stderr)
        return 1
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code", "Unknown")
        print(f"\nAWS error [{code}]: {error.get('Message', exc)}", file=sys.stderr)
        if code in {"ExpiredTokenException", "ExpiredToken", "UnrecognizedClientException"}:
            print("Temporary credentials expired -- get a fresh set from Workshop Studio.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
