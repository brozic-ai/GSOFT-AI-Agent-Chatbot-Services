from pathlib import Path

_DIR = Path(__file__).parent / "v1"


def get_system_prompt() -> str:
    return (_DIR / "system.md").read_text(encoding="utf-8")


def get_examples() -> str:
    return (_DIR / "example.json").read_text(encoding="utf-8")


def get_user_prompt(
    query: str, chat_history: list[dict], few_shot_examples: str | None = None
) -> str:
    if few_shot_examples is None:
        few_shot_examples = get_examples()
    template = (_DIR / "user.md").read_text(encoding="utf-8")
    history_text = (
        "\n".join(f"{h['role']}: {h['content']}" for h in chat_history[-6:])
        or "(không có)"
    )
    return template.format(
        few_shot_examples=few_shot_examples,
        chat_history=history_text,
        query=query,
    )
