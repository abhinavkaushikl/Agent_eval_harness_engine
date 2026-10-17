# support-copilot (Gate V sample repo)

A small, deliberately realistic app: a customer-support assistant that answers questions over a
**SQLite order database** and a **Qdrant vector store** of help-centre passages. It is the fixture
EvalLoop is pointed at for the Gate V review — it is **not** rigged for the gate.

What is here, and why EvalLoop can see it:

| Path | What it is | What EvalLoop discovers from it |
|---|---|---|
| `.env` | app configuration | a database (`DATABASE_URL`), a vector store (`QDRANT_URL`), and a **production** database (`PROD_DATABASE_URL`) |
| `docker-compose.yml` | local services | a `postgres` service and a `qdrant` service, each with a port |
| `app/db.py` | data access | a `create_engine(...)` call site |
| `data/schema.sql`, `data/seed.sql` | the dev order DB | the real SQLite database EvalLoop connects to read-only |
| `knowledge/passages.jsonl` | help-centre corpus | the passages the RAG answers must be faithful to |
| `knowledge/gold.jsonl` | labelled retrieval set | the gold passages recall@k is measured against |

The `PROD_DATABASE_URL` is here on purpose: a real repo has one, and the point of the gate is that
EvalLoop refuses to touch it without a typed confirmation.
