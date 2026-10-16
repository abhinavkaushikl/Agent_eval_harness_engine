"""Gate V evidence driver. Calls ONLY already-built evalloop code and prints verbatim output.

Run from the repo root:  python -I gatev_gate.py  (with the venv active)
It builds nothing in evalloop/ and fixes no finding; it exercises the built pipeline against the
gatev-sample/ repo and the loopback stand-ins, exactly as a reviewer would.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from evalloop.capability.broker import CapabilityBroker, Caps
from evalloop.connect.classify_endpoint import classify
from evalloop.connect.discover import discover
from evalloop.connect.envelope import AuditLog, Caps as ECaps, ReadOnlyEnvelope, ReadOnlyViolation, reject_writes
from evalloop.connect.scan import inspect_sqlite
from evalloop.connect.sqlite import SqliteConnector
from evalloop.connect.vector_qdrant import QdrantConnector, reject_vector_writes
from evalloop.grade.rag_recall import RECALL_FACT, RecallQuery, evidence_after, faithfulness_readiness, measure_recall_at_k
from evalloop.grade.rag_stages import (
    CitationItem,
    FaithfulnessAnswer,
    citation_quality,
    distractor_robustness,
    failure_attribution,
    faithfulness,
    oracle_context_ceiling,
    render,
    unanswerable_handling,
)
from evalloop.grade.rag_stages import FailureStage
from evalloop.grade.sql_execution import Snapshot, grade_sql, summarize
from evalloop.memory.case import Verdict
from evalloop.vocab import Tool

SAMPLE = Path("gatev-sample")
KAPPA_GATE = 0.60  # caller-supplied (M4's calibration policy); never defaulted inside a grader


def banner(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------------------
# A real SQLite order DB, built from the sample repo's schema + seed.
# ---------------------------------------------------------------------------
def build_db(path: Path, *, with_distinguishing_row: bool = True) -> None:
    schema = (SAMPLE / "data" / "schema.sql").read_text()
    seed = (SAMPLE / "data" / "seed.sql").read_text()
    conn = sqlite3.connect(path)
    conn.executescript(schema)
    conn.executescript(seed)
    if not with_distinguishing_row:
        conn.execute("DELETE FROM orders WHERE id = 204")  # drop the refund=5000 boundary row
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# A loopback server speaking Qdrant's wire protocol (protocol-faithful stand-in).
# Ranking is honest lexical overlap over the sample repo's real passages.
# ---------------------------------------------------------------------------
PASSAGES = [json.loads(l) for l in (SAMPLE / "knowledge" / "passages.jsonl").read_text().splitlines() if l.strip()]
GOLD = [json.loads(l) for l in (SAMPLE / "knowledge" / "gold.jsonl").read_text().splitlines() if l.strip()]


def _rank(query_text: str) -> list[dict[str, object]]:
    q = set(query_text.lower().split())
    scored = []
    for p in PASSAGES:
        overlap = len(q & set(p["text"].lower().split()))
        scored.append((overlap, p))
    scored.sort(key=lambda s: (-s[0], s[1]["id"]))
    return [{"id": p["id"], "score": float(score), "payload": {"text": p["text"]}} for score, p in scored]


class QdrantStandIn(BaseHTTPRequestHandler):
    def log_message(self, *a: object) -> None:
        pass

    def _send(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/collections":
            self._send({"result": {"collections": [{"name": "help_center"}]}, "status": "ok"})
        elif self.path == "/collections/help_center":
            self._send({"result": {"config": {"params": {"vectors": {"size": 384, "distance": "Cosine", "model": "BAAI/bge-small-en-v1.5"}}}}})
        else:
            self._send({"result": {}})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else {}
        text = str(body.get("query_text", ""))
        self._send({"result": _rank(text)})


class QdrantRetriever:
    """A recall@k retriever that goes through the REAL QdrantConnector read path (envelope-guarded)."""

    def __init__(self, connector: QdrantConnector) -> None:
        self._c = connector

    def retrieve(self, query: RecallQuery, k: int) -> Sequence[str]:
        result = self._c.search("help_center", {"query_text": query.text, "limit": k})
        return [str(row[0]) for row in result.rows]


# ===========================================================================
# 0. THE ORACLE FIRST (E6). If this is not 100%, the gate is VOID.
# ===========================================================================
def run_oracle(db: Path, qdrant_base: str) -> bool:
    banner("0. ORACLE (E6) — a known-correct SQL and a known-good RAG answer. Must be 100%.")
    snap = Snapshot(db)
    ref = "SELECT c.name, COUNT(o.id) AS n FROM customers c JOIN orders o ON o.customer_id = c.id WHERE c.country = 'US' AND o.total > 1000 GROUP BY c.name"
    sql_grade = grade_sql(ref, snapshot=snap, reference=ref)  # identical to reference: must pass
    print(f"  known-correct SQL      -> {sql_grade.verdict.value.upper():12} ({sql_grade.detail})")
    snap.close()

    broker = CapabilityBroker()
    broker.grant(Tool.vector_store, granted_by="gate", reason="oracle", endpoint="qdrant://localhost")
    qc = QdrantConnector(qdrant_base, broker=broker, endpoint="qdrant://localhost")
    model = qc.describe().collections[0].embedding_model or ""
    queries = [RecallQuery(g["query_id"], tuple(g["gold_ids"]), g["text"]) for g in GOLD]
    recall = measure_recall_at_k(queries, k=3, embedding_model=model, retriever=QdrantRetriever(qc))
    print(f"  known-good retrieval   -> recall@3 {recall.recall:.3f} (must be 1.000)")

    class OracleJudge:
        family = "anthropic"
        kappa = 0.74

        def entails(self, claim: str, context: str) -> bool:
            words = set(claim.lower().replace(".", "").split())
            ctx = set(context.lower().replace(".", "").split())
            return len(words & ctx) >= max(2, len(words) // 2)

    good = FaithfulnessAnswer(
        claims=("Refunds are issued within 5 to 7 business days.",),
        context=PASSAGES[0]["text"],
    )
    fstage = faithfulness([good], judge=OracleJudge(), kappa_gate=KAPPA_GATE, generator_family="openai")
    faith = fstage.metrics[0].interval.estimate if fstage.metrics else 0.0
    print(f"  known-good faithfulness-> mean {faith:.3f} (must be 1.000; judge κ=0.74 ≥ {KAPPA_GATE})")

    ok = sql_grade.verdict is Verdict.passed and recall.recall == 1.0 and faith == 1.0
    print(f"\n  ORACLE VERDICT: {'PASS — harness is sound, gate may proceed' if ok else 'FAIL — GATE IS VOID'}")
    return ok


# ===========================================================================
# 2. DISCOVER -> CONSENT -> READ-ONLY PROBE -> VALIDATE (verbatim, unprompted)
# ===========================================================================
def run_discovery(db: Path) -> None:
    banner("2. DISCOVER (file:line provenance) — zero instruction, nothing opened")
    cands = discover(SAMPLE)
    prod = None
    local_db = None
    for c in cands:
        cl = classify(c)
        print(f"  [{c.category:12}] {c.detail}")
        print(f"      provenance : {c.provenance}  ({c.provenance.reason})")
        print(f"      posture    : {cl.posture.value}  default_deny={cl.default_deny} typed_confirm={cl.require_typed_confirmation}")
        if cl.posture.value == "production_suspected":
            prod = (c, cl)

    banner("2b. CONSENT + READ-ONLY PROBE + VALIDATE — the real SQLite dev DB")
    insp = inspect_sqlite(db, endpoint="sqlite:///data/shop.db")
    print(f"  granted + probed: {insp.probe.detail}")
    print(f"  read-only (probe + audit): {insp.read_only}")
    for t in insp.schema.tables:
        print(f"  table {t.name}: {', '.join(c.name + ':' + c.type for c in t.columns)}")
    return prod


# ===========================================================================
# 3. THE SAFETY ENVELOPE, PROVEN
# ===========================================================================
def run_safety(db: Path, prod) -> None:
    banner("3a. A generated DROP TABLE is rejected BEFORE transmission")
    calls: list[str] = []

    class RecordingExecutor:
        read_only = True

        def run(self, sql: str, *, max_rows: int | None) -> list[tuple[object, ...]]:
            calls.append(sql)  # only reached if the write got past layer 1
            return []

    env = ReadOnlyEnvelope(AuditLog())
    try:
        env.execute("DROP TABLE orders; SELECT 1", endpoint="sqlite:///data/shop.db", caps=ECaps(), executor=RecordingExecutor())
        print("  ERROR: DROP TABLE was NOT rejected")
    except ReadOnlyViolation as exc:
        print(f"  ReadOnlyViolation: {exc}")
        print(f"  executor.run called? {bool(calls)}  -> the write never reached the wire")

    banner("3b. Audit log over the whole validation run — zero writes against any live schema")
    audit = AuditLog()
    snap = Snapshot(db, envelope=ReadOnlyEnvelope(audit))
    snap.rows("SELECT COUNT(*) FROM orders")
    snap.rows("SELECT id FROM customers WHERE country = 'US'")
    kinds = sorted({k for e in audit.entries() for k in e.statement_kinds})
    print(f"  statements executed: {len(audit)}   kinds seen: {kinds}")
    print(f"  any write/DDL kind?  {any(k not in ('read',) for k in kinds)}")
    snap.close()

    banner("3c. A production-looking endpoint is refused without the typed name")
    cand, cl = prod
    print(f"  endpoint: {cl.endpoint_name}")
    print(f"  posture : {cl.posture.value}  (reason: {cl.rationale})")
    print(f"  wrong typed name 'yes'        -> confirmed? {cl.confirms('yes')}")
    print(f"  empty typed name ''           -> confirmed? {cl.confirms('')}")
    print(f"  exact name typed              -> confirmed? {cl.confirms(cl.endpoint_name)}")


# ===========================================================================
# 4. SQL VALIDATED BY EXECUTION MATCH
# ===========================================================================
def run_sql(db: Path) -> None:
    banner("4. SQL validated by EXECUTION MATCH (result sets, never text)")
    snap = Snapshot(db)
    ref = "SELECT c.name, COUNT(o.id) AS n FROM customers c JOIN orders o ON o.customer_id = c.id WHERE c.country = 'US' AND o.total > 1000 GROUP BY c.name"
    reordered = "SELECT c.name, COUNT(o.id) AS n FROM orders o JOIN customers c ON c.id = o.customer_id WHERE c.country = 'US' AND o.total > 1000 GROUP BY c.name"
    hallucinated = "SELECT c.name, o.discount FROM customers c JOIN orders o ON o.customer_id = c.id"

    g1 = grade_sql(reordered, snapshot=snap, reference=ref)
    print(f"  reordered JOIN (same result) -> {g1.verdict.value.upper():12} ({g1.detail})")
    g2 = grade_sql(hallucinated, snapshot=snap, reference=ref)
    print(f"  hallucinated column o.discount-> {g2.verdict.value.upper():12} [{g2.failure_class.value if g2.failure_class else '-'}] ({g2.detail})")
    s = summarize([g1, g2])
    print(f"  pass rate over decided: {s.passed}/{s.decided}  interval={s.interval}")
    snap.close()


# ===========================================================================
# 5. RAG STAGE BY STAGE — faithfulness gated behind recall@k via READINESS
# ===========================================================================
def run_rag(qdrant_base: str) -> None:
    banner("5a. Faithfulness is gated by recall@k through READINESS (requires), not the unlocks edge")
    before = faithfulness_readiness(evidence_after(None))
    print(f"  evidence WITHOUT recall fact ({RECALL_FACT} absent): met={before.met}")
    print(f"      reason: {before.reason}")

    broker = CapabilityBroker()
    broker.grant(Tool.vector_store, granted_by="gate", reason="rag", endpoint="qdrant://localhost")
    qc = QdrantConnector(qdrant_base, broker=broker, endpoint="qdrant://localhost")
    model = qc.describe().collections[0].embedding_model or ""
    queries = [RecallQuery(g["query_id"], tuple(g["gold_ids"]), g["text"]) for g in GOLD]
    recall = measure_recall_at_k(queries, k=3, embedding_model=model, retriever=QdrantRetriever(qc))
    after = faithfulness_readiness(evidence_after(recall))
    print(f"\n  {recall.describe()}")
    print(f"  evidence AFTER recall ran ({RECALL_FACT} present): met={after.met}")
    print(f"      reason: {after.reason}")

    banner("5b. Every RAG stage on its own line — no blended score")

    class XFamilyJudge:
        family = "anthropic"
        kappa = 0.71

        def entails(self, claim: str, context: str) -> bool:
            w = set(claim.lower().replace(".", "").split())
            c = set(context.lower().replace(".", "").split())
            return len(w & c) >= max(2, len(w) // 2)

    stages = [
        oracle_context_ceiling([True, True, True, False]),
        failure_attribution([FailureStage.not_retrieved, FailureStage.misread]),
        faithfulness(
            [FaithfulnessAnswer(("Refunds take 5 to 7 business days.",), PASSAGES[0]["text"]),
             FaithfulnessAnswer(("Cancelled orders are refunded in full automatically.",), PASSAGES[2]["text"])],
            judge=XFamilyJudge(), kappa_gate=KAPPA_GATE, generator_family="openai",
        ),
        distractor_robustness([True, True, False, True]),
        unanswerable_handling([False, False], [True, False]),
        citation_quality([CitationItem(("p1",), ("p1",)), CitationItem(("p2", "p6"), ("p2",))]),
    ]
    print(render(stages))

    banner("5c. Same-family judge is refused (self-preference) — the gate the reviewer warned about")
    same = faithfulness([FaithfulnessAnswer(("x",), "x")], judge=XFamilyJudge(), kappa_gate=KAPPA_GATE, generator_family="anthropic")
    print(f"  generator=anthropic, judge=anthropic -> status={same.status}  ({same.pending_reason})")


# ===========================================================================
# 6. NEGATIVE CONTROL + FALSE NEGATIVE
# ===========================================================================
def run_controls(db_with: Path, db_without: Path) -> None:
    banner("6a. Negative control — a CORRECT query and a FAITHFUL answer are NOT flagged")
    snap = Snapshot(db_with)
    ref = "SELECT id FROM orders WHERE refund > 5000"
    correct = "SELECT id FROM orders WHERE refund > 5000"
    g = grade_sql(correct, snapshot=snap, reference=ref)
    print(f"  correct query            -> {g.verdict.value.upper()} ({g.detail})  [not flagged]")
    snap.close()

    banner("6b. False negative — a WRONG boundary passes when the distinguishing row is absent")
    wrong = "SELECT id FROM orders WHERE refund >= 5000"  # >= vs > : differs only on refund == 5000
    snap_with = Snapshot(db_with)
    gw = grade_sql(wrong, snapshot=snap_with, reference=ref)
    print(f"  WITH distinguishing row (order 204, refund=5000):    {gw.verdict.value.upper()} ({gw.detail})  <- caught")
    snap_with.close()
    snap_wo = Snapshot(db_without)
    gwo = grade_sql(wrong, snapshot=snap_wo, reference=ref)
    print(f"  WITHOUT it:                                          {gwo.verdict.value.upper()} ({gwo.detail})  <- FALSE NEGATIVE")
    print("  explanation: the failure is not in the grader but in the fixture. Execution match is only")
    print("  as strong as the distinguishing rows seeded (corpus A:36). The sample seeds order 204 on")
    print("  purpose; a reviewer must check that every reference query has a boundary row that separates")
    print("  it from its likely wrong neighbours, or an execution-match pass means less than it looks.")
    snap_wo.close()


def main() -> None:
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    db = tmp / "shop.db"
    db_wo = tmp / "shop_no_boundary.db"
    build_db(db, with_distinguishing_row=True)
    build_db(db_wo, with_distinguishing_row=False)

    server = ThreadingHTTPServer(("127.0.0.1", 0), QdrantStandIn)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    oracle_ok = run_oracle(db, base)
    if not oracle_ok:
        print("\n*** ORACLE FAILED — stopping. The gate is VOID. ***")
        server.shutdown()
        return
    prod = run_discovery(db)
    run_safety(db, prod)
    run_sql(db)
    run_rag(base)
    run_controls(db, db_wo)
    server.shutdown()
    banner("END OF EVIDENCE")


if __name__ == "__main__":
    main()
