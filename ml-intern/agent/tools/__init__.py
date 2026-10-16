"""
Hugging Face tools for the agent
"""

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
from agent.tools.types import ToolResult
from agent.tools.web_search_tool import WEB_SEARCH_TOOL_SPEC, web_search_handler

from agent.tools.local_ml_tools import (
    LIST_LOCAL_DATASETS_TOOL_SPEC,
    list_local_datasets_handler,
    LIST_LOCAL_MODELS_TOOL_SPEC,
    list_local_models_handler,
    SAVE_LOCAL_MODEL_TOOL_SPEC,
    save_local_model_handler,
)

__all__ = [
    "ToolResult",
    "GITHUB_FIND_EXAMPLES_TOOL_SPEC",
    "github_find_examples_handler",
    "GITHUB_LIST_REPOS_TOOL_SPEC",
    "github_list_repos_handler",
    "GITHUB_READ_FILE_TOOL_SPEC",
    "github_read_file_handler",
    "WEB_SEARCH_TOOL_SPEC",
    "web_search_handler",
    "LIST_LOCAL_DATASETS_TOOL_SPEC",
    "list_local_datasets_handler",
    "LIST_LOCAL_MODELS_TOOL_SPEC",
    "list_local_models_handler",
    "SAVE_LOCAL_MODEL_TOOL_SPEC",
    "save_local_model_handler",
]
