"""Live-coding scratchpad — a governed LangChain model in five lines, no asyncio.

`chat_model()` returns a real `langchain_openai.ChatOpenAI`, so typing `model.`
gives you LangChain's entire surface — invoke, ainvoke, stream, bind_tools, … —
already pointed at the governed proxy.

Drop the `_paths` line if you have already exported the three
AGENT_FABRIC_LLM_PROXY_* variables in your shell.
"""

# ruff: noqa: I001, E402  (the _paths shim must import before agent_fabric — do not reorder)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # demos/ (holds _paths.py)
import _paths  # noqa: F401  (loads demos/.env.local into the environment)

from agent_fabric.integrations.langgraph import chat_model

model = chat_model("gpt-4o")
print(model.invoke("Say hi in three words").content)
