"""The file and prompt-registry connectors (EL-310): documents and prompts as read-only eval inputs.

The load-bearing proofs: a docs directory and a prompt file are both read and come back as eval
inputs through one interface; an MCP-served prompt (the stdlib reference server, over stdio, no
network) comes back through that same interface; a binary or oversized file is skipped with a
reason and an oversized one is never opened; the walk honours ``.gitignore`` and never descends into
``node_modules`` or a virtualenv; and every byte of text crosses the redactor before it is returned.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from evalloop.capability.broker import CapabilityBroker, Caps
from evalloop.connect.files import DirectoryConnector, GitIgnore
from evalloop.connect.prompts import MCPPromptConnector, PromptFileConnector, is_prompt_file
from evalloop.connect.protocol import InputKind, InputSet, InputSource, NotAuthorized
from evalloop.connect.redact import REDACTED, redact_secrets
from evalloop.mcp import (
    Content,
    Prompt,
    PromptArgument,
    PromptMessage,
    PromptResult,
    ServerInfo,
    StdioClient,
    ToolFailed,
)
from evalloop.vocab import Tool

_SERVER = Path(__file__).resolve().parent / "fixtures" / "mcp" / "reference_server.py"
_MCP_ENDPOINT = "mcp://reference"
_SECRET = "sk-live-abcdefghijklmnop0123"


def _broker(tool: Tool, endpoint: str, caps: Caps | None = None) -> CapabilityBroker:
    broker = CapabilityBroker()
    broker.grant(tool, granted_by="test", reason="read-only eval inputs", endpoint=endpoint, caps=caps)
    return broker


def _write(root: Path, files: Mapping[str, str | bytes]) -> None:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(body, encoding="utf-8")


def _docs(root: Path, **kwargs: object) -> DirectoryConnector:
    endpoint = f"dir:{root.as_posix()}"
    caps = kwargs.pop("caps", None)
    assert caps is None or isinstance(caps, Caps)
    return DirectoryConnector(root, broker=_broker(Tool.source_doc_read, endpoint, caps), endpoint=endpoint, **kwargs)  # type: ignore[arg-type]


def _reasons(found: InputSet) -> dict[str, str]:
    return {s.name: s.reason for s in found.skipped}


@pytest.fixture
def live_client() -> Iterator[StdioClient]:
    with StdioClient.launch([sys.executable, str(_SERVER)]) as client:
        yield client


# -- the done-when: docs, a prompt file and an MCP prompt, all as eval inputs ---------------


def test_a_docs_directory_and_a_prompt_file_are_both_eval_inputs(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "docs/refunds.md": "# Refunds\nRefunds are issued within 14 days.\n",
            "docs/shipping.txt": "Orders ship in 2 business days.\n",
            "prompts/support.md": "You are a support agent. Answer {{ question }} using {{context}}.\n",
        },
    )
    docs = _docs(tmp_path / "docs")
    prompts = PromptFileConnector(
        tmp_path, broker=_broker(Tool.repo_read, "repo"), endpoint="repo"
    )
    assert isinstance(docs, InputSource) and isinstance(prompts, InputSource)

    documents = docs.inputs()
    assert [d.name for d in documents.inputs] == ["refunds.md", "shipping.txt"]
    assert all(d.kind is InputKind.document for d in documents.inputs)
    assert "14 days" in documents.inputs[0].text

    found = prompts.inputs()
    assert [p.name for p in found.inputs] == ["prompts/support.md"]
    prompt = found.inputs[0]
    assert prompt.kind is InputKind.prompt
    assert prompt.parameters == ("context", "question")
    assert [m.role for m in prompt.messages] == ["user"]


def test_an_mcp_served_prompt_comes_through_the_same_interface(live_client: StdioClient) -> None:
    conn = MCPPromptConnector(
        live_client,
        broker=_broker(Tool.source_doc_read, _MCP_ENDPOINT),
        endpoint=_MCP_ENDPOINT,
        arguments={"summarize": {"document": "The order shipped late."}},
    )
    assert isinstance(conn, InputSource)
    probe = conn.probe()
    assert probe.reachable and probe.read_only and "offers prompts" in probe.detail

    found = conn.inputs()
    by_name = {p.name: p for p in found.inputs}
    assert sorted(by_name) == ["greeting", "summarize"]
    summarize = by_name["summarize"]
    assert summarize.kind is InputKind.prompt
    assert summarize.source == f"{_MCP_ENDPOINT}#summarize"
    assert summarize.parameters == ("document",)
    assert "The order shipped late." in summarize.text
    assert [m.role for m in by_name["greeting"].messages] == ["user", "assistant"]
    # an image-only prompt is skipped with its reason, not flattened to empty text
    assert "non-text (image)" in _reasons(found)["picture"]


def test_a_required_mcp_argument_is_never_guessed(live_client: StdioClient) -> None:
    conn = MCPPromptConnector(live_client, broker=_broker(Tool.source_doc_read, _MCP_ENDPOINT), endpoint=_MCP_ENDPOINT)
    found = conn.inputs()
    assert "summarize" not in {p.name for p in found.inputs}
    assert "requires the argument(s) document" in _reasons(found)["summarize"]


def test_files_and_mcp_prompts_are_interchangeable(tmp_path: Path, live_client: StdioClient) -> None:
    _write(tmp_path, {"triage.prompt": "Classify the ticket."})
    sources: list[InputSource] = [
        PromptFileConnector(tmp_path, broker=_broker(Tool.repo_read, "repo"), endpoint="repo"),
        MCPPromptConnector(live_client, broker=_broker(Tool.source_doc_read, _MCP_ENDPOINT), endpoint=_MCP_ENDPOINT),
    ]
    names = [p.name for source in sources for p in source.inputs().of_kind(InputKind.prompt)]
    assert names == ["triage.prompt", "greeting"]


# -- binary and oversized: skipped with a reason, never read ---------------------------------


def test_binary_and_oversized_files_are_skipped_with_a_reason(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "ok.md": "fine",
            "logo.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            "latin1.txt": "caf\xe9".encode("latin-1"),
            "dump.sql": "x" * 5000,
        },
    )
    found = _docs(tmp_path, max_file_bytes=4096).inputs()
    assert [d.name for d in found.inputs] == ["ok.md"]
    reasons = _reasons(found)
    assert reasons["logo.png"].startswith("binary")
    assert reasons["latin1.txt"].startswith("not UTF-8")
    assert reasons["dump.sql"].startswith("oversized (4.9 KiB > the 4.0 KiB per-file cap)")


def test_an_oversized_file_is_never_opened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    big = tmp_path / "huge.log"
    with big.open("wb") as handle:  # sparse: 2 GiB on paper, nothing on disk
        handle.truncate(2 * 1024**3)
    _write(tmp_path, {"small.md": "ok"})
    opened: list[str] = []
    real_open = Path.open

    def spy(self: Path, *args: object, **kwargs: object) -> object:
        opened.append(self.name)
        return real_open(self, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(Path, "open", spy)
    found = _docs(tmp_path).inputs()
    assert "oversized" in _reasons(found)["huge.log"]
    assert opened == ["small.md"]


def test_the_grants_byte_cap_bounds_the_whole_read(tmp_path: Path) -> None:
    _write(tmp_path, {"a.md": "a" * 60, "b.md": "b" * 60, "c.md": "c" * 30})
    found = _docs(tmp_path, caps=Caps(max_bytes=100)).inputs()
    assert [d.name for d in found.inputs] == ["a.md", "c.md"]
    assert "byte cap (100 bytes)" in _reasons(found)["b.md"]
    assert found.inputs and sum(d.size_bytes for d in found.inputs) <= 100


# -- gitignore-aware, and never into node_modules / a venv / dotfiles ---------------------------


def test_the_walk_honours_gitignore_and_prunes_vendored_trees(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            ".gitignore": "build/\n*.log\n/secret.md\n!keep.log\n",
            "guide.md": "kept",
            "keep.log": "re-included by negation",
            "server.log": "ignored",
            "secret.md": "anchored ignore",
            "sub/secret.md": "the anchor does not reach here",
            "sub/.gitignore": "draft-*.md\n",
            "sub/draft-1.md": "ignored by the nested file",
            "build/out.md": "ignored dir",
            "node_modules/pkg/README.md": "vendored",
            "venv/pyvenv.cfg": "home = /usr",
            "venv/lib/notes.md": "a virtualenv",
            ".env": f"API_KEY={_SECRET}",
            ".cache/x.md": "hidden dir",
        },
    )
    found = _docs(tmp_path).inputs()
    assert [d.name for d in found.inputs] == ["guide.md", "keep.log", "sub/secret.md"]
    reasons = _reasons(found)
    assert reasons["build/"] == "ignored by .gitignore; not walked"
    assert reasons["server.log"] == "ignored by .gitignore; not read"
    assert reasons["secret.md"] == "ignored by .gitignore; not read"
    assert reasons["sub/draft-1.md"] == "ignored by .gitignore; not read"
    assert "vendored" in reasons["node_modules/"]
    assert reasons["venv/"] == "a virtualenv; not walked"
    assert ".env" in reasons[".env"]
    assert "hidden" in reasons[".cache/"]
    assert not any(n.startswith("node_modules/pkg") for n in reasons), "node_modules was descended into"


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_symlinks_are_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    _write(outside, {"private.md": "outside the root"})
    root = tmp_path / "root"
    _write(root, {"a.md": "inside"})
    (root / "link.md").symlink_to(outside / "private.md")
    (root / "linkdir").symlink_to(outside, target_is_directory=True)
    found = _docs(root).inputs()
    assert [d.name for d in found.inputs] == ["a.md"]
    assert "symlink" in _reasons(found)["link.md"]
    assert "symlinked directory" in _reasons(found)["linkdir/"]


@pytest.mark.parametrize(
    ("patterns", "path", "is_dir", "ignored"),
    [
        ("*.log", "a/b/x.log", False, True),
        ("/top.md", "top.md", False, True),
        ("/top.md", "a/top.md", False, False),
        ("docs/*.md", "docs/a.md", False, True),
        ("docs/*.md", "docs/sub/a.md", False, False),
        ("docs/**/*.md", "docs/sub/deep/a.md", False, True),
        ("**/tmp", "a/b/tmp", True, True),
        ("out/", "out", False, False),
        ("out/", "out", True, True),
        ("data[0-9].csv", "data7.csv", False, True),
        ("*.md\n!README.md", "README.md", False, False),
        ("# a comment\n\n", "a.md", False, False),
    ],
)
def test_the_gitignore_subset(tmp_path: Path, patterns: str, path: str, is_dir: bool, ignored: bool) -> None:
    (tmp_path / ".gitignore").write_text(patterns + "\n", encoding="utf-8")
    rules = GitIgnore()
    rules.add_file(tmp_path / ".gitignore", "")
    assert rules.ignored(path, is_dir=is_dir) is ignored


# -- the redactor at the boundary ----------------------------------------------------------------


def test_every_input_crosses_the_redactor(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "runbook.md": f"Connect with postgres://app:hunter2pass@db:5432/shop\nkey: {_SECRET}\n",
            "prompts/agent.md": "Use password = CorrectHorse99 when asked.",
        },
    )
    docs = _docs(tmp_path).inputs()
    runbook = {d.name: d for d in docs.inputs}["runbook.md"]
    assert _SECRET not in runbook.text and "hunter2pass" not in runbook.text
    assert "postgres://app:<redacted>@db" in runbook.text
    assert runbook.redactions == 2

    prompts = PromptFileConnector(tmp_path, broker=_broker(Tool.repo_read, "repo"), endpoint="repo").inputs()
    agent = prompts.inputs[0]
    assert "CorrectHorse99" not in agent.text and agent.redactions == 1
    assert all("CorrectHorse99" not in m.text for m in agent.messages)


def test_an_mcp_prompt_is_redacted_before_it_is_returned(live_client: StdioClient) -> None:
    conn = MCPPromptConnector(live_client, broker=_broker(Tool.source_doc_read, _MCP_ENDPOINT), endpoint=_MCP_ENDPOINT)
    greeting = {p.name: p for p in conn.inputs().inputs}["greeting"]
    assert "sk-test-0123456789abcdefghij" not in greeting.text
    assert REDACTED in greeting.messages[1].text and greeting.redactions == 1


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("token: none", 0),
        ("password: TBD", 0),
        ("The API key rotates monthly.", 0),
        ("export OPENAI_API_KEY=sk-proj-AAAAAAAAAAAAAAAAAAAA", 1),
        ("aws AKIAABCDEFGHIJKLMNOP", 1),
        ("ghp_abcdefghijklmnopqrstuvwxyz0123", 1),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----", 1),
        ("mysql://root:s3cr3t@localhost/app", 1),
    ],
)
def test_the_redactor_takes_credentials_and_leaves_prose(text: str, count: int) -> None:
    redacted, replaced = redact_secrets(text)
    assert replaced == count
    if count == 0:
        assert redacted == text
    else:
        assert REDACTED in redacted


def test_the_content_hash_is_of_the_redacted_text(tmp_path: Path) -> None:
    _write(tmp_path, {"a.md": f"key={_SECRET}"})
    first = _docs(tmp_path).inputs().inputs[0]
    (tmp_path / "a.md").write_text("key=sk-another-secret-value-xyz", encoding="utf-8")
    second = _docs(tmp_path).inputs().inputs[0]
    assert first.content_hash == second.content_hash  # two different secrets look identical once redacted


# -- the broker, the audit log, determinism -------------------------------------------------------


def test_an_ungranted_source_is_refused_before_anything_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, {"a.md": "x", "prompts/p.md": "y"})
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("a file was opened without a grant"))
    with pytest.raises(NotAuthorized):
        DirectoryConnector(tmp_path, broker=CapabilityBroker()).inputs()
    with pytest.raises(NotAuthorized):
        PromptFileConnector(tmp_path, broker=CapabilityBroker()).probe()
    # a grant for a different capability does not cover it
    wrong = _broker(Tool.db_connection, f"dir:{tmp_path.as_posix()}")
    with pytest.raises(NotAuthorized):
        DirectoryConnector(tmp_path, broker=wrong).inputs()


def test_an_ungranted_mcp_server_is_not_contacted() -> None:
    class Untouchable:
        def discover(self) -> ServerInfo:
            raise AssertionError("contacted without a grant")

        def list_prompts(self) -> tuple[Prompt, ...]:
            raise AssertionError("contacted without a grant")

        def get_prompt(self, name: str, arguments: Mapping[str, str]) -> PromptResult:
            raise AssertionError("contacted without a grant")

    conn = MCPPromptConnector(Untouchable(), broker=CapabilityBroker(), endpoint=_MCP_ENDPOINT)
    with pytest.raises(NotAuthorized):
        conn.probe()
    with pytest.raises(NotAuthorized):
        conn.inputs()


def test_a_server_error_on_one_prompt_skips_only_that_prompt() -> None:
    class Flaky:
        def discover(self) -> ServerInfo:
            return ServerInfo("flaky", "1", ("2026-07-28",), ("prompts",))

        def list_prompts(self) -> tuple[Prompt, ...]:
            return (Prompt("bad", None, ()), Prompt("good", None, (PromptArgument("x", None, False),)))

        def get_prompt(self, name: str, arguments: Mapping[str, str]) -> PromptResult:
            if name == "bad":
                raise ToolFailed(-32603, "render failed")
            return PromptResult(None, (PromptMessage("user", Content("text", "hello")),))

    found = MCPPromptConnector(Flaky(), broker=_broker(Tool.source_doc_read, "mcp://flaky"), endpoint="mcp://flaky").inputs()
    assert [p.name for p in found.inputs] == ["good"]
    assert found.inputs[0].parameters == ("x",)
    assert "render failed" in _reasons(found)["bad"]


def test_the_audit_log_records_shape_and_never_content(tmp_path: Path) -> None:
    _write(tmp_path, {"a.md": f"secret={_SECRET} and the body text"})
    conn = _docs(tmp_path)
    conn.probe()
    conn.inputs()
    entries = conn.audit.entries()
    assert [e.statement_kinds for e in entries] == [("probe",), ("inputs",)]
    assert entries[1].result is not None and entries[1].result.row_count == 1
    assert all(_SECRET not in repr(e) and "body text" not in repr(e) for e in entries)


def test_nothing_in_the_root_is_written(tmp_path: Path) -> None:
    _write(tmp_path, {"a.md": "x", "prompts/b.md": "y", ".gitignore": "*.tmp\n"})
    before = sorted((p.relative_to(tmp_path).as_posix(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*"))
    _docs(tmp_path).inputs()
    PromptFileConnector(tmp_path, broker=_broker(Tool.repo_read, "repo"), endpoint="repo").inputs()
    after = sorted((p.relative_to(tmp_path).as_posix(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*"))
    assert before == after


def test_the_same_directory_gives_the_same_inputs(tmp_path: Path) -> None:
    _write(tmp_path, {f"d{i}/f{j}.md": f"{i}-{j}" for i in (3, 1, 2) for j in (2, 1)})
    assert _docs(tmp_path).inputs() == _docs(tmp_path).inputs()


def test_a_missing_root_probes_unreachable(tmp_path: Path) -> None:
    probe = _docs(tmp_path / "nope").probe()
    assert probe.reachable is False and probe.read_only is True


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("support.prompt", True),
        ("a/b/triage.prompt.md", True),
        ("x.prompty", True),
        ("prompts/system.md", True),
        ("app/prompts/v2/agent.j2", True),
        ("prompts/loader.py", False),
        ("docs/guide.md", False),
        ("prompts.md", False),
    ],
)
def test_which_files_are_prompts(path: str, expected: bool) -> None:
    assert is_prompt_file(path) is expected
