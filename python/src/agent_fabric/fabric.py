"""The ``Fabric`` public surface (§3.2).

    from agent_fabric import Fabric
    fabric = Fabric.from_env()

    client = fabric.llm.client()                 # AsyncOpenAI at the proxy
    fabric.langgraph.chat_model("gpt-4o")        # native ChatOpenAI

Per-framework adapters are lazy attributes. Accessing one whose extra is not
installed raises :class:`ImportError` with the exact install command — never a
bare ``ModuleNotFoundError`` (§3.2).
"""

from __future__ import annotations

import importlib
import importlib.util
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any

from .core import _verify
from .core.auth import AnypointConnectedApp, AuthProvider
from .core.config import FabricConfig
from .core.telemetry import run_context
from .core.transport import (
    FabricAsyncClient,
    FabricClient,
    build_http_client,
    build_sync_http_client,
)
from .integrations import ADAPTERS
from .llm.client import LLMClient
from .registry.exchange import ExchangeRegistry
from .registry.governance import GovernanceCriteria
from .tools.session import ToolSet

if TYPE_CHECKING:
    from .integrations._base import Adapter
    from .integrations.adk import ADKAdapter
    from .integrations.agent_framework import AgentFrameworkAdapter
    from .integrations.anthropic import AnthropicAdapter
    from .integrations.crewai import CrewAIAdapter
    from .integrations.langgraph import LangGraphAdapter
    from .integrations.llamaindex import LlamaIndexAdapter
    from .integrations.openai_agents import OpenAIAgentsAdapter
    from .integrations.strands import StrandsAdapter


def _framework_installed(probe: str) -> bool:
    """Whether a framework's representative module can be located, without
    importing it. Any error locating it means 'not installed'."""
    try:
        return importlib.util.find_spec(probe) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


class _ToolsFacade:
    """``fabric.tools`` — discovery + lock (§4.1, §4.2)."""

    def __init__(self, registry: ExchangeRegistry) -> None:
        self._registry = registry

    async def discover(
        self,
        *,
        domain: str | None = None,
        tags: list[str] | None = None,
        governed: bool | GovernanceCriteria | None = None,
        governance: Any | None = None,
        locked: bool = False,
    ) -> ToolSet:
        """Discover a governed tool catalog and return a bindable ``ToolSet``.

        ``governed`` defaults to ``None`` (no filtering) in v1, with a startup
        log line stating discovery is unfiltered (§6.1.2). Flipping the default
        to ``True`` is a breaking change reserved for a later major version.

        Blocked until Exchange search + the governed-state join are verified
        (§0.3 / §6.7).
        """

        raise _verify.blocked(
            "Exchange search + governed-state join (§6.1, §6.7). ToolSet filtering "
            "and binding scaffolding exist; wire discover() once the APIs are "
            "confirmed and use registry.explain() for the empty-result reason."
        )

    def lock(self) -> None:
        """Write a ``fabric.lock`` of resolved versions + digests (§4.2)."""
        raise _verify.blocked("resolution API needed for the lockfile (§4.2, §6.7).")


class Fabric:
    # Adapters are resolved lazily by __getattr__ so an uninstalled framework
    # never breaks ``import agent_fabric``. These annotations exist purely so an
    # editor knows what each one is: without them a type checker only sees the
    # ``Adapter`` return type of __getattr__, and `fabric.langgraph.chat_model`
    # gets no completion and reads as an unknown attribute. Annotations bind no
    # value, so __getattr__ still runs at import-safe runtime.
    if TYPE_CHECKING:
        langgraph: LangGraphAdapter
        adk: ADKAdapter
        strands: StrandsAdapter
        agent_framework: AgentFrameworkAdapter
        openai: OpenAIAgentsAdapter
        anthropic: AnthropicAdapter
        crewai: CrewAIAdapter
        llamaindex: LlamaIndexAdapter

    def __init__(
        self,
        config: FabricConfig | None = None,
        *,
        auth: AuthProvider | None = None,
    ) -> None:
        self._cfg = config or FabricConfig.from_env()
        self._auth = auth if auth is not None else self._default_auth(self._cfg)
        self._http: FabricAsyncClient = build_http_client(self._cfg, self._auth)
        # Built only if someone asks for a blocking client, so the common async
        # path never opens a connection pool it will not use.
        self._sync_http: FabricClient | None = None
        self._llm = LLMClient(self._cfg, self._http, self._sync_http_client)
        self._registry = ExchangeRegistry(self._cfg, self._http)
        self._tools = _ToolsFacade(self._registry)
        self._adapter_cache: dict[str, Adapter] = {}

    @classmethod
    def from_env(cls) -> Fabric:
        return cls(FabricConfig.from_env())

    # --- framework-free surfaces -------------------------------------------
    @property
    def config(self) -> FabricConfig:
        return self._cfg

    @property
    def llm(self) -> LLMClient:
        return self._llm

    @property
    def registry(self) -> ExchangeRegistry:
        return self._registry

    @property
    def tools(self) -> _ToolsFacade:
        return self._tools

    def run_context(self, run_id: str | None = None) -> AbstractContextManager[str]:
        """Bind a correlation ID for one logical agent run (§2.3)."""
        return run_context(run_id)

    def _sync_http_client(self) -> FabricClient:
        if self._sync_http is None:
            self._sync_http = build_sync_http_client(self._cfg)
        return self._sync_http

    async def aclose(self) -> None:
        await self._http.aclose()
        self.close()

    async def __aenter__(self) -> Fabric:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    def close(self) -> None:
        """Close the blocking transport. ``aclose()`` calls this too, so an async
        caller who also used ``client(sync=True)`` still closes both."""
        if self._sync_http is not None:
            self._sync_http.close()
            self._sync_http = None

    def __enter__(self) -> Fabric:
        """Sync context manager for the blocking surface. ``__exit__`` cannot
        await, so it does not touch the async transport — harmless, because httpx
        opens no connection until a request is actually made, and a purely
        synchronous caller never makes one through it."""
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- lazy per-framework adapters ---------------------------------------
    def __getattr__(self, name: str) -> Adapter:
        # Only called for attributes not found normally.
        spec = ADAPTERS.get(name)
        if spec is None:
            raise AttributeError(f"{type(self).__name__!r} has no attribute {name!r}")
        if name in self._adapter_cache:
            return self._adapter_cache[name]
        if not _framework_installed(spec.probe):
            raise ImportError(
                f"The {name!r} integration is not installed. Install it with:\n"
                f'    pip install "mulesoft-agent-fabric[{spec.extra}]"'
            )
        module = importlib.import_module(spec.module, package="agent_fabric.integrations")
        adapter_cls = getattr(module, spec.cls)
        adapter: Adapter = adapter_cls(self._cfg, self._http)
        self._adapter_cache[name] = adapter
        return adapter

    @staticmethod
    def _default_auth(cfg: FabricConfig) -> AuthProvider | None:
        """Build control-plane auth when credentials are present. The LLM proxy
        credential is separate and handled by the OpenAI client (§2.2)."""
        if cfg.client_id and cfg.client_secret:
            return AnypointConnectedApp(
                client_id=cfg.client_id,
                client_secret=cfg.client_secret,
                control_plane_url=cfg.control_plane_url,
                http_client=build_http_client(cfg, None),  # token fetches need no auth
            )
        return None
