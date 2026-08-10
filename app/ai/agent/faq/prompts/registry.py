from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


class PromptLoader:
    def __init__(self, task: str, version: str = "v1"):
        self.task_dir = PROMPTS_DIR / task / version
        if not self.task_dir.exists():
            raise FileNotFoundError(f"Không tìm thấy prompt: {task}/{version}")

    def load_system(self) -> str:
        return (self.task_dir / "system.md").read_text(encoding="utf-8")

    def load_user(self, **kwargs) -> str:
        template = (self.task_dir / "user.md").read_text(encoding="utf-8")
        return template.format(**kwargs)  # cho phép user.md có {placeholder}
