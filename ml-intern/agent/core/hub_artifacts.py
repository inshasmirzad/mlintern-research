"""Local stubs for previously HF-dependent artifact management."""

def remember_hub_artifact(*args, **kwargs) -> None:
    pass

def is_known_hub_artifact(*args, **kwargs) -> bool:
    return False

def augment_repo_card_content(content: str | None, *args, **kwargs) -> str:
    return content or ""

def register_hub_artifact(*args, **kwargs) -> bool:
    return False

def build_hub_artifact_sitecustomize(*args, **kwargs) -> str:
    return ""

def wrap_shell_command_with_hub_artifact_bootstrap(command: str, *args, **kwargs) -> str:
    return command
