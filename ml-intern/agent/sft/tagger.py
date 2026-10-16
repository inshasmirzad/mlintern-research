"""Derive tags for a session trajectory.

``tag_session(trajectory)`` → ``list[str]``. Pure function. No filtering, no
mutation — tags are purely metadata so downstream pipelines can slice the raw
SFT dataset (``where 'hf_job:succeeded' in tags``) without re-reading trajectories.

Tag namespaces (all tags are ``"<namespace>:<value>"`` strings):

* ``tool:<name>``       — every tool called at least once (``tool:hf_jobs``, …)
* ``outcome:<end>``     — ``completed`` / ``errored`` / ``interrupted`` /
                          ``ongoing`` / ``doom_loop`` / ``context_exceeded``
* ``hf_job:<facet>``    — ``submitted``, ``succeeded``, ``failed``,
                          ``multi`` (>1), ``oom``, ``push_to_hub``
* ``gpu:<kind>``        — ``none``, ``t4``, ``a10g``, ``a100``, ``l40s``,
                          ``h100``, plus ``gpu:multi`` for x2/x4/x8 flavors
* ``sandbox:<facet>``   — ``created``, ``gpu``, ``cpu``, ``long_lived`` (>30 min)
* ``feedback:<kind>``   — ``up``, ``down``, ``mixed``, ``none``
* ``model:<family>``    — ``opus`` / ``sonnet`` / ``haiku`` / ``kimi`` /
                          ``gpt`` / ``deepseek`` / ``qwen`` / ``other``
* ``turns:<bucket>``    — ``short`` (<5) / ``medium`` (5–20) / ``long`` (>20)
* ``cost:<bucket>``     — ``low`` (<$0.10) / ``med`` (<$1) / ``high``
* ``task:<kind>``       — ``training`` / ``inference`` / ``data_prep`` /
                          ``research_only`` (heuristic on tools + scripts)

Tags are deduplicated before returning.
"""

from __future__ import annotations

from typing import Iterable

# Flavor → GPU-family mapping. Keep conservative; unknown flavors → "none".
_GPU_FAMILY = {
    "cpu-basic": "none",
    "cpu-upgrade": "none",
    "t4-small": "t4",
    "t4-medium": "t4",
    "l4x1": "l40s",
    "l4x4": "l40s",
    "l40sx1": "l40s",
    "l40sx4": "l40s",
    "l40sx8": "l40s",
    "a10g-small": "a10g",
    "a10g-large": "a10g",
    "a10g-largex2": "a10g",
    "a10g-largex4": "a10g",
    "a100-large": "a100",
    "a100x2": "a100",
    "a100x4": "a100",
    "a100x8": "a100",
    "h100": "h100",
    "h100x8": "h100",
}

# Substrings that count a flavor as multi-GPU.
_MULTI_GPU_MARKERS = ("x2", "x4", "x8")

# Tool names that don't touch training/inference or sandbox/jobs. If a session
# only used these, we tag it research_only.
_RESEARCH_ONLY_TOOLS = {
    "research",
    "github_find_examples",
    "github_read_file",
    "github_list_repos",
    "plan",
    "dataset_inspect",
    "web_search",
}

# Tool names that signal data manipulation workflows.
_DATA_PREP_TOOLS = {"dataset_inspect", "dataset_tools"}


def _model_family(model_name: str | None) -> str:
    if not model_name:
        return "other"
    n = model_name.lower()
    if "opus" in n:
        return "opus"
    if "sonnet" in n:
        return "sonnet"
    if "haiku" in n:
        return "haiku"
    if "kimi" in n:
        return "kimi"
    if "gpt" in n:
        return "gpt"
    if "deepseek" in n:
        return "deepseek"
    if "qwen" in n:
        return "qwen"
    if "llama" in n:
        return "llama"
    return "other"


def _turns_bucket(n: int) -> str:
    if n < 5:
        return "short"
    if n <= 20:
        return "medium"
    return "long"


def _cost_bucket(cost_usd: float) -> str:
    if cost_usd < 0.10:
        return "low"
    if cost_usd < 1.0:
        return "med"
    return "high"


def _flavor_to_gpu_tags(flavor: str) -> list[str]:
    family = _GPU_FAMILY.get(flavor, "none")
    tags = [f"gpu:{family}"]
    if any(m in flavor for m in _MULTI_GPU_MARKERS):
        tags.append("gpu:multi")
    return tags


def _has_oom_signal(tool_outputs: Iterable[str]) -> bool:
    for out in tool_outputs:
        if not isinstance(out, str):
            continue
        low = out.lower()
        if "outofmemoryerror" in low or "cuda out of memory" in low or "oom" in low:
            return True
    return False


def _infer_task_tag(
    tool_names: set[str],
    job_submit_scripts: list[str],
) -> str | None:
    """Return a ``task:*`` tag or None if we can't tell.

    Heuristic order: training > inference > data_prep > research_only.
    """
    # training: any script mentioning ML training keywords
    for script in job_submit_scripts:
        low = script.lower()
        if any(
            k in low
            for k in (
                "fit(",
                ".train(",
                "training",
                "fit_transform",
                "fine-tune",
                "finetune",
            )
        ):
            return "training"
    
    if tool_names & {"train_local_model"}:
        return "training"

    # inference: sessions that use inference tools but never compute sandbox
    uses_compute = bool(tool_names & {"sandbox_create", "sandbox_exec"})
    if not uses_compute and tool_names & {"inference", "generate", "run_inference", "predict"}:
        return "inference"

    # data_prep: primarily dataset tools and no training/inference
    if tool_names & _DATA_PREP_TOOLS and not uses_compute:
        return "data_prep"

    # research_only: every tool used is in the research allow-list
    if tool_names and tool_names <= _RESEARCH_ONLY_TOOLS:
        return "research_only"

    return None


def tag_session(trajectory: dict) -> list[str]:
    """Derive tags from a session trajectory. Pure function."""
    tags: set[str] = set()

    events: list[dict] = trajectory.get("events") or []
    messages: list[dict] = trajectory.get("messages") or []
    model_name: str | None = trajectory.get("model_name")

    # model
    tags.add(f"model:{_model_family(model_name)}")

    # turns
    user_turns = sum(1 for m in messages if m.get("role") == "user")
    tags.add(f"turns:{_turns_bucket(user_turns)}")

    # cost + tool-name enumeration + outcome detection
    cost_usd = 0.0
    tool_names: set[str] = set()
    tool_outputs: list[str] = []
    local_job_submit_scripts: list[str] = []
    gpu_tags_seen: set[str] = set()

    # Outcome is the *last* terminal signal. Seed with "ongoing" — overridden
    # if we see a terminal event.
    outcome = "ongoing"
    had_error = False
    had_doom_loop = False
    had_compact = False

    feedback_up = 0
    feedback_down = 0

    sandbox_created = False
    sandbox_hardware: str | None = None
    sandbox_lifetime_s: int | None = None

    for ev in events:
        et = ev.get("event_type")
        data = ev.get("data") or {}

        if et == "llm_call":
            cost_usd += float(data.get("cost_usd") or 0.0)

        elif et == "tool_call":
            name = data.get("tool")
            if name:
                tool_names.add(name)

        elif et == "tool_output":
            out = data.get("output")
            if isinstance(out, str):
                tool_outputs.append(out)

        elif et == "sandbox_create":
            sandbox_created = True
            sandbox_hardware = data.get("hardware")

        elif et == "sandbox_destroy":
            lt = data.get("lifetime_s")
            if isinstance(lt, (int, float)):
                sandbox_lifetime_s = int(lt)

        elif et == "feedback":
            rating = data.get("rating")
            if rating == "up":
                feedback_up += 1
            elif rating == "down":
                feedback_down += 1

        elif et == "error":
            had_error = True
        elif et == "turn_complete":
            if not had_error:
                outcome = "completed"
        elif et == "interrupted":
            outcome = "interrupted"
        elif et == "compacted":
            had_compact = True
        elif et == "tool_log":
            log_text = (data.get("log") or "").lower()
            if "doom loop" in log_text:
                had_doom_loop = True

    if had_error and outcome not in ("completed", "interrupted"):
        outcome = "errored"

    tags.add(f"outcome:{outcome}")
    if had_doom_loop:
        tags.add("outcome:doom_loop")
    if had_compact:
        tags.add("outcome:context_exceeded")

    # tools
    for name in tool_names:
        tags.add(f"tool:{name}")

    # gpu tags
    tags.update(gpu_tags_seen)
    if "gpu:none" in tags and len(gpu_tags_seen) > 1:
        # If any GPU flavor was used, drop the "none" tag for clarity.
        tags.discard("gpu:none")

    # sandbox facets
    if sandbox_created:
        tags.add("sandbox:created")
        if sandbox_hardware:
            fam = _GPU_FAMILY.get(sandbox_hardware, "none")
            tags.add("sandbox:cpu" if fam == "none" else "sandbox:gpu")
        if sandbox_lifetime_s is not None and sandbox_lifetime_s > 1800:
            tags.add("sandbox:long_lived")

    # feedback
    if feedback_up and feedback_down:
        tags.add("feedback:mixed")
    elif feedback_up:
        tags.add("feedback:up")
    elif feedback_down:
        tags.add("feedback:down")
    else:
        tags.add("feedback:none")

    # cost bucket
    tags.add(f"cost:{_cost_bucket(cost_usd)}")

    # task heuristic (needs scripts — pull from local compute/train jobs)
    for ev in events:
        if ev.get("event_type") == "tool_call":
            data = ev.get("data") or {}
            if data.get("tool") in ("train_local_model", "sandbox_exec"):
                args = data.get("arguments") or {}
                script = args.get("script") or args.get("command") or ""
                if isinstance(script, str):
                    local_job_submit_scripts.append(script)

    task_tag = _infer_task_tag(tool_names, local_job_submit_scripts)
    if task_tag:
        tags.add(f"task:{task_tag}")

    return sorted(tags)
