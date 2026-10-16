"""
Tool system for the agent
Provides ToolSpec and ToolRouter for managing both built-in and MCP tools
"""

import logging
import warnings
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.types import EmbeddedResource, ImageContent, TextContent

from agent.config import MCPServerConfig
from agent.tools.dataset_inspect_tool import (
    DATASET_INSPECT_TOOL_SPEC,
    dataset_inspect_handler,
)
from agent.tools.docs_tools import (
    FETCH_DOCS_TOOL_SPEC,
    fetch_docs_handler,
)
from agent.tools.github_find_examples import (
    GITHUB_FIND_EXAMPLES_TOOL_SPEC,
    github_find_examples_handler,
)
from agent.tools.github_list_repos import (
    GITHUB_LIST_REPOS_TOOL_SPEC,
    github_list_repos_handler,
)
from agent.tools.github_read_file import (
    GITHUB_READ_FILE_TOOL_SPEC,
    github_read_file_handler,
)
from agent.tools.local_ml_tools import (
    LIST_LOCAL_DATASETS_TOOL_SPEC,
    LIST_LOCAL_MODELS_TOOL_SPEC,
    SAVE_DATASET_METADATA_TOOL_SPEC,
    SAVE_LOCAL_MODEL_TOOL_SPEC,
    TRAIN_LOCAL_MODEL_TOOL_SPEC,
    list_local_datasets_handler,
    list_local_models_handler,
    save_dataset_metadata_handler,
    save_local_model_handler,
    train_local_model_handler,
)
from agent.tools.notify_tool import NOTIFY_TOOL_SPEC, notify_handler
from agent.tools.papers_tool import PAPERS_TOOL_SPEC, papers_handler
from agent.tools.plan_tool import PLAN_TOOL_SPEC, plan_tool_handler
from agent.tools.research_tool import RESEARCH_TOOL_SPEC, research_handler
from agent.tools.training_job_tools import (
    GET_BEST_LOCAL_MODEL_TOOL_SPEC,
    GET_LOCAL_TRAINING_JOB_TOOL_SPEC,
    QUEUE_LOCAL_TRAINING_TOOL_SPEC,
    get_best_local_model_handler,
    get_local_training_job_handler,
    queue_local_training_handler,
)
from agent.tools.web_search_tool import WEB_SEARCH_TOOL_SPEC, web_search_handler

# Suppress aiohttp deprecation warning
warnings.filterwarnings(
    "ignore", category=DeprecationWarning, module="aiohttp.connector"
)

logger = logging.getLogger(__name__)

NOT_ALLOWED_TOOL_NAMES = []


def convert_mcp_content_to_string(content: list) -> str:
    """
    Convert MCP content blocks to a string format compatible with LLM messages.

    Based on FastMCP documentation, content can be:
    - TextContent: has .text field
    - ImageContent: has .data and .mimeType fields
    - EmbeddedResource: has .resource field with .text or .blob

    Args:
        content: List of MCP content blocks

    Returns:
        String representation of the content suitable for LLM consumption
    """
    if not content:
        return ""

    parts = []
    for item in content:
        if isinstance(item, TextContent):
            # Extract text from TextContent blocks
            parts.append(item.text)
        elif isinstance(item, ImageContent):
            # TODO: Handle images
            # For images, include a description with MIME type
            parts.append(f"[Image: {item.mimeType}]")
        elif isinstance(item, EmbeddedResource):
            # TODO: Handle embedded resources
            # For embedded resources, try to extract text
            resource = item.resource
            if hasattr(resource, "text") and resource.text:
                parts.append(resource.text)
            elif hasattr(resource, "blob") and resource.blob:
                parts.append(
                    f"[Binary data: {resource.mimeType if hasattr(resource, 'mimeType') else 'unknown'}]"
                )
            else:
                parts.append(
                    f"[Resource: {resource.uri if hasattr(resource, 'uri') else 'unknown'}]"
                )
        else:
            # Fallback: try to convert to string
            parts.append(str(item))

    return "\n".join(parts)


@dataclass
class ToolSpec:
    """Tool specification for LLM"""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[tuple[str, bool]]] | None = None


class ToolRouter:
    """
    Routes tool calls to appropriate handlers.
    Based on codex-rs/core/src/tools/router.rs
    """

    def __init__(
        self,
        mcp_servers: dict[str, MCPServerConfig],
        hf_token: str | None = None,
        local_mode: bool = False,
    ):
        self.tools: dict[str, ToolSpec] = {}
        self.mcp_servers: dict[str, dict[str, Any]] = {}

        for tool in create_builtin_tools(local_mode=local_mode):
            self.register_tool(tool)

        self.mcp_client: Client | None = None
        if mcp_servers:
            mcp_servers_payload = {}
            for name, server in mcp_servers.items():
                data = server.model_dump()
                if hf_token:
                    data.setdefault("headers", {})["Authorization"] = (
                        f"Bearer {hf_token}"
                    )
                mcp_servers_payload[name] = data
            self.mcp_client = Client({"mcpServers": mcp_servers_payload})
        self._mcp_initialized = False

    def register_tool(self, tool: ToolSpec) -> None:
        self.tools[tool.name] = tool

    async def register_mcp_tools(self) -> None:
        tools = await self.mcp_client.list_tools()
        registered_names = []
        skipped_count = 0
        for tool in tools:
            if tool.name in NOT_ALLOWED_TOOL_NAMES:
                skipped_count += 1
                continue
            registered_names.append(tool.name)
            self.register_tool(
                ToolSpec(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.inputSchema,
                    handler=None,
                )
            )
        logger.info(
            f"Loaded {len(registered_names)} MCP tools: {', '.join(registered_names)} ({skipped_count} disabled)"
        )

    async def register_openapi_tool(self) -> None:
        """Removed OpenAPI search tool (HF specific)"""

    def get_tool_specs_for_llm(self) -> list[dict[str, Any]]:
        """Get tool specifications in OpenAI format"""
        specs = []
        for tool in self.tools.values():
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return specs

    async def __aenter__(self) -> "ToolRouter":
        if self.mcp_client is not None:
            try:
                await self.mcp_client.__aenter__()
                await self.mcp_client.initialize()
                await self.register_mcp_tools()
                self._mcp_initialized = True
            except Exception as e:
                logger.warning(
                    "MCP connection failed, continuing without MCP tools: %s", e
                )
                self.mcp_client = None

        await self.register_openapi_tool()

        total_tools = len(self.tools)
        logger.info(f"Agent ready with {total_tools} tools total")

        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.mcp_client is not None:
            await self.mcp_client.__aexit__(exc_type, exc, tb)
            self._mcp_initialized = False

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session: Any = None,
        tool_call_id: str | None = None,
    ) -> tuple[str, bool]:
        """
        Call a tool and return (output_string, success_bool).

        For MCP tools, converts the CallToolResult content blocks to a string.
        For built-in tools, calls their handler directly.
        """
        # Check if this is a built-in tool with a handler
        tool = self.tools.get(tool_name)
        if tool and tool.handler:
            import inspect

            # Check if handler accepts session argument
            sig = inspect.signature(tool.handler)
            if "session" in sig.parameters:
                # Check if handler also accepts tool_call_id parameter
                if "tool_call_id" in sig.parameters:
                    return await tool.handler(
                        arguments, session=session, tool_call_id=tool_call_id
                    )
                return await tool.handler(arguments, session=session)
            return await tool.handler(arguments)

        # Otherwise, use MCP client
        if self._mcp_initialized:
            try:
                result = await self.mcp_client.call_tool(tool_name, arguments)
                output = convert_mcp_content_to_string(result.content)
                return output, not result.is_error
            except ToolError as e:
                # Catch MCP tool errors and return them to the agent
                error_msg = f"Tool error: {e!s}"
                return error_msg, False

        return "MCP client not initialized", False


# ============================================================================
# BUILT-IN TOOL HANDLERS
# ============================================================================


def create_builtin_tools(local_mode: bool = False) -> list[ToolSpec]:
    """Create built-in tool specifications"""
    # in order of importance
    tools = [
        # Research sub-agent (delegates to read-only tools in independent context)
        ToolSpec(
            name=RESEARCH_TOOL_SPEC["name"],
            description=RESEARCH_TOOL_SPEC["description"],
            parameters=RESEARCH_TOOL_SPEC["parameters"],
            handler=research_handler,
        ),
        # Documentation search tools
        ToolSpec(
            name=FETCH_DOCS_TOOL_SPEC["name"],
            description=FETCH_DOCS_TOOL_SPEC["description"],
            parameters=FETCH_DOCS_TOOL_SPEC["parameters"],
            handler=fetch_docs_handler,
        ),
        # Paper discovery and reading
        ToolSpec(
            name=PAPERS_TOOL_SPEC["name"],
            description=PAPERS_TOOL_SPEC["description"],
            parameters=PAPERS_TOOL_SPEC["parameters"],
            handler=papers_handler,
        ),
        ToolSpec(
            name=DATASET_INSPECT_TOOL_SPEC["name"],
            description=DATASET_INSPECT_TOOL_SPEC["description"],
            parameters=DATASET_INSPECT_TOOL_SPEC["parameters"],
            handler=dataset_inspect_handler,
        ),
        ToolSpec(
            name=WEB_SEARCH_TOOL_SPEC["name"],
            description=WEB_SEARCH_TOOL_SPEC["description"],
            parameters=WEB_SEARCH_TOOL_SPEC["parameters"],
            handler=web_search_handler,
        ),
        # Planning and job management tools
        ToolSpec(
            name=PLAN_TOOL_SPEC["name"],
            description=PLAN_TOOL_SPEC["description"],
            parameters=PLAN_TOOL_SPEC["parameters"],
            handler=plan_tool_handler,
        ),
        ToolSpec(
            name=NOTIFY_TOOL_SPEC["name"],
            description=NOTIFY_TOOL_SPEC["description"],
            parameters=NOTIFY_TOOL_SPEC["parameters"],
            handler=notify_handler,
        ),
        # Local ML tools
        ToolSpec(
            name=LIST_LOCAL_DATASETS_TOOL_SPEC["name"],
            description=LIST_LOCAL_DATASETS_TOOL_SPEC["description"],
            parameters=LIST_LOCAL_DATASETS_TOOL_SPEC["parameters"],
            handler=list_local_datasets_handler,
        ),
        ToolSpec(
            name=SAVE_DATASET_METADATA_TOOL_SPEC["name"],
            description=SAVE_DATASET_METADATA_TOOL_SPEC["description"],
            parameters=SAVE_DATASET_METADATA_TOOL_SPEC["parameters"],
            handler=save_dataset_metadata_handler,
        ),
        ToolSpec(
            name=LIST_LOCAL_MODELS_TOOL_SPEC["name"],
            description=LIST_LOCAL_MODELS_TOOL_SPEC["description"],
            parameters=LIST_LOCAL_MODELS_TOOL_SPEC["parameters"],
            handler=list_local_models_handler,
        ),
        ToolSpec(
            name=SAVE_LOCAL_MODEL_TOOL_SPEC["name"],
            description=SAVE_LOCAL_MODEL_TOOL_SPEC["description"],
            parameters=SAVE_LOCAL_MODEL_TOOL_SPEC["parameters"],
            handler=save_local_model_handler,
        ),
        ToolSpec(
            name=TRAIN_LOCAL_MODEL_TOOL_SPEC["name"],
            description=TRAIN_LOCAL_MODEL_TOOL_SPEC["description"],
            parameters=TRAIN_LOCAL_MODEL_TOOL_SPEC["parameters"],
            handler=train_local_model_handler,
        ),
        ToolSpec(
            name=QUEUE_LOCAL_TRAINING_TOOL_SPEC["name"],
            description=QUEUE_LOCAL_TRAINING_TOOL_SPEC["description"],
            parameters=QUEUE_LOCAL_TRAINING_TOOL_SPEC["parameters"],
            handler=queue_local_training_handler,
        ),
        ToolSpec(
            name=GET_LOCAL_TRAINING_JOB_TOOL_SPEC["name"],
            description=GET_LOCAL_TRAINING_JOB_TOOL_SPEC["description"],
            parameters=GET_LOCAL_TRAINING_JOB_TOOL_SPEC["parameters"],
            handler=get_local_training_job_handler,
        ),
        ToolSpec(
            name=GET_BEST_LOCAL_MODEL_TOOL_SPEC["name"],
            description=GET_BEST_LOCAL_MODEL_TOOL_SPEC["description"],
            parameters=GET_BEST_LOCAL_MODEL_TOOL_SPEC["parameters"],
            handler=get_best_local_model_handler,
        ),
        ToolSpec(
            name=GITHUB_FIND_EXAMPLES_TOOL_SPEC["name"],
            description=GITHUB_FIND_EXAMPLES_TOOL_SPEC["description"],
            parameters=GITHUB_FIND_EXAMPLES_TOOL_SPEC["parameters"],
            handler=github_find_examples_handler,
        ),
        ToolSpec(
            name=GITHUB_LIST_REPOS_TOOL_SPEC["name"],
            description=GITHUB_LIST_REPOS_TOOL_SPEC["description"],
            parameters=GITHUB_LIST_REPOS_TOOL_SPEC["parameters"],
            handler=github_list_repos_handler,
        ),
        ToolSpec(
            name=GITHUB_READ_FILE_TOOL_SPEC["name"],
            description=GITHUB_READ_FILE_TOOL_SPEC["description"],
            parameters=GITHUB_READ_FILE_TOOL_SPEC["parameters"],
            handler=github_read_file_handler,
        ),
    ]

    # Sandbox or local tools (highest priority)
    from agent.tools.local_tools import get_local_tools

    tools = get_local_tools() + tools

    tool_names = ", ".join([t.name for t in tools])
    logger.info(f"Loaded {len(tools)} built-in tools: {tool_names}")

    return tools
