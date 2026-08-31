import os


def load_skill(skill_name: str) -> str:
    """Load a skill file from .claude/skills/ and return its contents."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    skill_path = os.path.join(project_root, ".claude", "skills", f"{skill_name}.md")
    with open(skill_path) as f:
        return f.read()
