"""The ``Tool`` vocabulary: capabilities a technique needs in order to run.

The rule, verbatim from ``CLAUDE.md`` section 6:

    Every member names a **capability**: something that must exist in the world
    for a technique to be runnable. No member names a **transport** -- how the
    thing is reached. The test for a candidate: if the delivery mechanism
    changed but the resource stayed the same, would any record's requirement
    change? If not, it is transport, and it belongs to the capability broker,
    not here.

That is why ``mcp_client`` and ``mcp_gateway`` are absent and stay absent:
decision ``decisions/EL-002-mcp-tools-in-enum.md`` is closed and not reopenable.
MCP is a way of reaching a resource, not a resource. A record that needs a
vector store needs a vector store whether it is reached over MCP, a local
library or an HTTP API, so the requirement is ``vector_store`` and the
credentials and protocol belong to the capability broker.

The 15 members below are ``CLAUDE.md`` section 6's list, in its order, which is
grouped by what the capability is for (execution, reading, models, stores,
sensing, money, people) rather than alphabetised. Member value == lowercase
member name, as for ``Situation``; both conventions are asserted in
``tests/test_vocab.py``.

Capabilities the deep dives require that have no member
-------------------------------------------------------
Found while cross-checking the "How to do it properly" sections, recorded here
so the next reader does not re-derive them, and **not added**: per EL-104 each is
a decision ticket, not a code change.

* A2 asserts post-conditions by querying "a DB row, an API GET, a file on disk".
  ``db_connection`` names one of those three systems of record and ``repo_read``
  the third; a readable non-database system of record has no member. By EL-002's
  own test the protocol is transport, so the missing capability is the resource,
  not the HTTP call.
* A7's tier 1 is "a small fine-tuned classifier, under 50 ms, trained on 5,000+
  judge-labelled items". It must exist for A7 to run and it is neither
  ``llm_api`` nor ``llm_api_cross_family``.
* I7 pre-registers an A/B test and checks the traffic split; I9 shadows live
  traffic, ramps 1% -> 100% and automates rollback. Both need *control* of live
  traffic, where ``production_logs`` only reads it.
* E7 checks "13-gram overlap between the benchmark and any available training or
  corpus data", which needs a corpus outside the repo that ``source_doc_read``
  (retrieval source documents) does not name.
"""

from __future__ import annotations

from evalloop._compat import StrEnum

__all__ = ["Tool"]


class Tool(StrEnum):
    """A capability that must exist in the world for some technique to run."""

    sandbox = "sandbox"
    test_runner = "test_runner"
    repo_read = "repo_read"
    source_doc_read = "source_doc_read"
    llm_api = "llm_api"
    llm_api_cross_family = "llm_api_cross_family"
    vector_store = "vector_store"
    db_connection = "db_connection"
    ocr = "ocr"
    vision_model = "vision_model"
    trace_capture = "trace_capture"
    snapshot_restore = "snapshot_restore"
    cost_api = "cost_api"
    human_labels = "human_labels"
    production_logs = "production_logs"
