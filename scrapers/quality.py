"""Audit candidate breadth and published-deal quality from the database."""

from __future__ import annotations

import argparse
import json

from scrapers.db import connect, init_db


def build_quality_report(conn) -> dict:
    """Return policy-conformance and breadth metrics from persisted state."""
    candidate = conn.execute(
        """
        SELECT COUNT(*) AS candidates,
               COUNT(DISTINCT source) AS sources,
               COUNT(DISTINCT source_tier) AS tiers,
               SUM(CASE WHEN decision = 'accepted' THEN 1 ELSE 0 END) AS accepted,
               SUM(CASE WHEN decision = 'pending' THEN 1 ELSE 0 END) AS pending,
               SUM(CASE WHEN decision = 'rejected' THEN 1 ELSE 0 END) AS rejected
        FROM deal_candidates
        """
    ).fetchone()
    published = conn.execute(
        """
        SELECT COUNT(*) AS deals,
               COUNT(DISTINCT source) AS sources,
               COUNT(DISTINCT category) AS categories,
               SUM(CASE WHEN placement = 'physical'
                             AND geocode_status = 'ok'
                             AND lat IS NOT NULL
                             AND lng IS NOT NULL
                        THEN 1 ELSE 0 END) AS map_pins,
               MIN(quality_score) AS minimum_quality_score
        FROM deals
        """
    ).fetchone()
    violations = conn.execute(
        """
        SELECT COUNT(*) AS violations
        FROM deals d
        LEFT JOIN deal_candidates c ON c.id = d.candidate_id
        WHERE d.deal_type NOT IN ('free', 'bogo')
           OR d.verification_status IS NULL
           OR d.verification_status NOT IN ('official', 'corroborated')
           OR d.quality_score IS NULL
           OR d.quality_score < 90
           OR c.id IS NULL
           OR c.decision != 'accepted'
        """
    ).fetchone()
    category_rows = conn.execute(
        "SELECT category, COUNT(*) AS n FROM deals GROUP BY category ORDER BY category"
    ).fetchall()
    source_rows = conn.execute(
        """
        SELECT source, decision, COUNT(*) AS n
        FROM deal_candidates
        GROUP BY source, decision
        ORDER BY source, decision
        """
    ).fetchall()

    violation_count = int(violations["violations"] or 0)
    return {
        "quality_gate_passed": violation_count == 0,
        "published_policy_violations": violation_count,
        "candidate_count": int(candidate["candidates"] or 0),
        "candidate_source_count": int(candidate["sources"] or 0),
        "candidate_source_tier_count": int(candidate["tiers"] or 0),
        "candidate_decisions": {
            "accepted": int(candidate["accepted"] or 0),
            "pending": int(candidate["pending"] or 0),
            "rejected": int(candidate["rejected"] or 0),
        },
        "published_deal_count": int(published["deals"] or 0),
        "published_source_count": int(published["sources"] or 0),
        "published_category_count": int(published["categories"] or 0),
        "published_map_pins": int(published["map_pins"] or 0),
        "minimum_published_quality_score": (
            int(published["minimum_quality_score"])
            if published["minimum_quality_score"] is not None
            else None
        ),
        "published_by_category": {
            str(row["category"]): int(row["n"]) for row in category_rows
        },
        "candidates_by_source_and_decision": {
            f"{row['source']}:{row['decision']}": int(row["n"])
            for row in source_rows
        },
    }


def format_quality_report(report: dict) -> str:
    decision = report["candidate_decisions"]
    return "\n".join(
        [
            "FreeMap information quality:",
            (
                "  quality_gate="
                f"{'PASS' if report['quality_gate_passed'] else 'FAIL'} "
                f"violations={report['published_policy_violations']} "
                f"minimum_score={report['minimum_published_quality_score']}"
            ),
            (
                f"  candidates={report['candidate_count']} "
                f"sources={report['candidate_source_count']} "
                f"tiers={report['candidate_source_tier_count']} "
                f"accepted={decision['accepted']} pending={decision['pending']} "
                f"rejected={decision['rejected']}"
            ),
            (
                f"  published={report['published_deal_count']} "
                f"sources={report['published_source_count']} "
                f"categories={report['published_category_count']} "
                f"map_pins={report['published_map_pins']}"
            ),
        ]
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="scrapers.quality",
        description="Audit candidate breadth and published-deal quality.",
    )
    parser.add_argument("--db", default="db/deals.db")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    conn = connect(args.db)
    try:
        init_db(conn)
        report = build_quality_report(conn)
    finally:
        conn.close()
    print(json.dumps(report, indent=2) if args.json else format_quality_report(report))
    return 0 if report["quality_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
