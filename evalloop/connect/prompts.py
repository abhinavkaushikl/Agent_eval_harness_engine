"""The prompt registry: prompts under test, from files on disk and from MCP servers, through one interface.

Both connectors here implement :class:`~evalloop.connect.protocol.InputSource` and yield
:class:`~evalloop.connect.protocol.EvalInput` values of kind ``prompt``, so a caller cannot tell —
and need not care — whether a prompt came from ``prompts/support.md`` or from a server's
``prompts/get``. Each prompt's role-tagged ``messages`` are kept, its declared ``parameters`` named,
and its text redacted before it is returned.

**Prompt files on disk** (:class:`PromptFileConnector`) are the directory walk of
:mod:`evalloop.connect.files` — gitignore-aware, size-capped, binary-skipping — with a filter: a file
is a prompt when its name ends ``.prompt``, ``.prompt.md``, ``.prompt.txt`` or ``.prompty``, or when it
is a text file (``.md``, ``.txt``, ``.j2``, ``.jinja``, ``.jinja2``, ``.tmpl``) under a directory
named ``prompts``. A file is one ``user`` message; its ``{{ name }}`` placeholders are its parameters.

**MCP prompts** (:class:`MCPPromptConnector`) come through EL-301's typed façade only — ``Prompt``,
``PromptResult``, ``PromptLister`` — so no wire concept leaks out of ``evalloop/mcp/`` (EL-007). A
prompt whose server declares a *required* argument is rendered only with a value the caller supplies;
without one it is skipped with that reason, never rendered with a guessed value. A prompt carrying a
non-text block (an image) is skipped too: its text alone would not be the prompt under test.

Which capability
----------------
A prompt file is in the repository, so it is ``repo_read``. An MCP server's prompts are not; no
``Tool`` member names a prompt registry, and ``source_doc_read`` (read-only source documents outside
the repo) is the nearest. That is a stated interpretation, not a new member — adding one is a
decision ticket (EL-104). Both defaults are constructor arguments.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Protocol, runtime_checkable

from evalloop.capability.broker import CapabilityBroker
from evalloop.connect.envelope import AuditEntry, AuditLog, Caps, ResultShape
from evalloop.connect.files import DEFAULT_MAX_FILE_BYTES, DirectoryConnector, make_input
from evalloop.connect.protocol import (
    EvalInput,
    InputKind,
    InputSet,
    Message,
    NotAuthorized,
    ProbeResult,
    Skipped,
)
from evalloop.mcp import Discoverable, McpError, Prompt, PromptLister, ServerInfo
from evalloop.vocab import Tool

__all__ = ["MCPPromptConnector", "McpPromptClient", "PromptFileConnector", "is_prompt_file"]

_PROMPT_SUFFIXES = (".prompt", ".prompt.md", ".prompt.txt", ".prompty")
_TEMPLATE_SUFFIXES = (".md", ".txt", ".j2", ".jinja", ".jinja2", ".tmpl")
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_]\w*)\s*\}\}")


def is_prompt_file(rel: str) -> bool:
    """Whether a root-relative POSIX path names a prompt file (see the module docstring)."""
    parts = rel.split("/")
    name = parts[-1].lower()
    if name.endswith(_PROMPT_SUFFIXES):
        return True
    return "prompts" in parts[:-1] and name.endswith(_TEMPLATE_SUFFIXES)


class PromptFileConnector:
    """probe / inputs over the prompt files in a repository. The directory walk, filtered to prompts."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        broker: CapabilityBroker,
        endpoint: str | None = None,
        tool: Tool = Tool.repo_read,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        audit: AuditLog | None = None,
    ) -> None:
        self._walk = DirectoryConnector(
            root,
            broker=broker,
            endpoint=endpoint,
            tool=tool,
            kind=InputKind.prompt,
            include=is_prompt_file,
            max_file_bytes=max_file_bytes,
            audit=audit,
        )
        self.endpoint = self._walk.endpoint
        self.audit = self._walk.audit

    def probe(self) -> ProbeResult:
        return self._walk.probe()

    def inputs(self) -> InputSet:
        found = self._walk.inputs()
        # Already redacted by the walk; only the parameters are added, so the redaction count survives.
        prompts = tuple(
            replace(item, parameters=tuple(sorted(set(_PLACEHOLDER.findall(item.text))))) for item in found.inputs
        )
        return InputSet(prompts, found.skipped)


@runtime_checkable
class McpPromptClient(Discoverable, PromptLister, Protocol):
    """What this connector needs of a server: discover it, list its prompts, render one."""


class MCPPromptConnector:
    """probe / inputs over an MCP server's prompts, through the broker; rendered only as supplied."""

    def __init__(
        self,
        client: McpPromptClient,
        *,
        broker: CapabilityBroker,
        endpoint: str,
        tool: Tool = Tool.source_doc_read,
        arguments: Mapping[str, Mapping[str, str]] | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.endpoint = endpoint
        self._client = client
        self._broker = broker
        self._tool = tool
        self._arguments = {name: dict(values) for name, values in (arguments or {}).items()}
        self.audit = audit if audit is not None else AuditLog()

    def _authorize(self) -> Caps:
        decision = self._broker.check(self._tool, endpoint=self.endpoint)
        if not decision.granted or decision.grant is None:
            raise NotAuthorized(decision.reason or f"{self._tool.value} is not granted for {self.endpoint!r}")
        return decision.grant.caps

    def probe(self) -> ProbeResult:
        """Reachable, and does it offer prompts? The server's own discovery; no prompt is fetched."""
        caps = self._authorize()
        try:
            info: ServerInfo = self._client.discover()
        except McpError as error:
            self._log("probe", caps, None, error=repr(error))
            return ProbeResult(reachable=False, read_only=True, detail=f"unreachable: {error}")
        self._log("probe", caps, None)
        offers = "offers prompts" if "prompts" in info.capabilities else "declares no prompts capability"
        return ProbeResult(reachable=True, read_only=True, detail=f"MCP server {info.name} v{info.version}; {offers}")

    def inputs(self) -> InputSet:
        """Every prompt the server lists, rendered with the supplied arguments, redacted."""
        caps = self._authorize()
        found: list[EvalInput] = []
        skipped: list[Skipped] = []
        for prompt in sorted(self._client.list_prompts(), key=lambda p: p.name):
            item, reason = self._render(prompt)
            if item is None:
                skipped.append(Skipped(prompt.name, reason or "not rendered"))
            else:
                found.append(item)
        self._log("inputs", caps, ResultShape(len(found), sum(i.size_bytes for i in found), False))
        return InputSet(tuple(found), tuple(skipped))

    def _render(self, prompt: Prompt) -> tuple[EvalInput | None, str | None]:
        supplied = self._arguments.get(prompt.name, {})
        missing = [arg.name for arg in prompt.arguments if arg.required and arg.name not in supplied]
        if missing:
            return None, f"requires the argument(s) {', '.join(missing)} and none was supplied; not rendered"
        try:
            result = self._client.get_prompt(prompt.name, supplied)
        except McpError as error:
            return None, f"the server could not render it: {error}"
        messages: list[Message] = []
        for message in result.messages:
            if message.content.kind != "text" or message.content.text is None:
                return None, f"carries a non-text ({message.content.kind}) block; not read"
            messages.append(Message(message.role, message.content.text))
        parameters = [arg.name for arg in prompt.arguments]
        return make_input(InputKind.prompt, prompt.name, f"{self.endpoint}#{prompt.name}", messages, parameters=parameters), None

    def _log(self, operation: str, caps: Caps, shape: ResultShape | None, *, error: str | None = None) -> None:
        self.audit.append(
            AuditEntry(
                endpoint=self.endpoint,
                redacted_sql=f"<{operation}>",
                statement_kinds=(operation,),
                caps=caps,
                write_scope=None,
                result=shape,
                error=error,
            )
        )
