"""Offline evaluation harness: gold Q&A -> retrieval hit-rate + faithfulness %.

For each gold question it calls POST /ask and scores:
  - retrieval hit: a cited clause's section matches expected_sections, OR an
    expected keyword appears in a cited clause's text
  - answer hit:    any expected keyword appears in the answer
  - faithful:      the runtime judge returned confidence == "high"

Usage:
  python scripts/run_eval.py --contract-id <id> --contract-file 01_msa_orion_helix
  python scripts/run_eval.py --contract-id <id1> --contract-file 01_msa_orion_helix \
                             --contract-id <id2> --contract-file 02_saas_nova_atlas
Options: --api http://localhost:8000  --gold ../data/eval/gold_qa.json  --no-agent
"""
import argparse
import json
from pathlib import Path

import requests


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--gold", default=str(Path(__file__).resolve().parents[2] / "data" / "eval" / "gold_qa.json"))
    ap.add_argument("--contract-id", action="append", required=True, dest="contract_ids")
    ap.add_argument("--contract-file", action="append", required=True, dest="contract_files",
                    help="gold-set contract_file key matching each --contract-id, in order")
    ap.add_argument("--no-agent", action="store_true", help="evaluate the single-shot RAG path")
    args = ap.parse_args()

    if len(args.contract_ids) != len(args.contract_files):
        ap.error("--contract-id and --contract-file must be given the same number of times")
    id_by_file = dict(zip(args.contract_files, args.contract_ids))

    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    gold = [g for g in gold if g["contract_file"] in id_by_file]
    if not gold:
        raise SystemExit("No gold questions match the given --contract-file keys.")

    retrieval_hits = answer_hits = faithful_count = 0
    for i, g in enumerate(gold, 1):
        cid = id_by_file[g["contract_file"]]
        resp = requests.post(f"{args.api}/ask", json={
            "contract_id": cid, "question": g["question"], "use_agent": not args.no_agent,
        }, timeout=300)
        resp.raise_for_status()
        data = resp.json()

        cited_sections = {c.get("section") for c in data["citations"] if c.get("section")}
        cited_text = " ".join(
            requests.get(f"{args.api}/clauses/{c['clause_id']}", timeout=30).json().get("text", "")
            for c in data["citations"]
        ).lower()

        r_hit = bool(set(g["expected_sections"]) & cited_sections) or \
            any(k.lower() in cited_text for k in g["expected_keywords"])
        a_hit = any(k.lower() in data["answer"].lower() for k in g["expected_keywords"])
        faithful = data["confidence"] == "high"

        retrieval_hits += r_hit
        answer_hits += a_hit
        faithful_count += faithful
        print(f"[{i:>2}/{len(gold)}] retrieval={'HIT ' if r_hit else 'MISS'} "
              f"answer={'HIT ' if a_hit else 'MISS'} faithful={'Y' if faithful else 'N'} "
              f"({data['mode']})  {g['question'][:70]}")

    n = len(gold)
    print("\n================ EVAL SUMMARY ================")
    print(f"questions:            {n}")
    print(f"retrieval hit-rate:   {retrieval_hits}/{n} = {100 * retrieval_hits / n:.0f}%")
    print(f"answer keyword hits:  {answer_hits}/{n} = {100 * answer_hits / n:.0f}%")
    print(f"faithfulness (judge): {faithful_count}/{n} = {100 * faithful_count / n:.0f}%")


if __name__ == "__main__":
    main()
