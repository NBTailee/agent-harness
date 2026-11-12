from pathlib import Path
import yaml


SKILL_DIRS = Path.cwd() / "skills"

def find_skills():
    skills = {}

    for path in sorted(SKILL_DIRS.glob("*/SKILL.md")):
        _, frontmatter, _ = path.read_text().split("---")
        meta = yaml.safe_load(frontmatter) 
        skills[meta["name"]] = {"description": meta["description"], "path": path}
    return skills

SKILLS = find_skills()

def skills_prompt() -> str:
    prompt = ""
    for skill in SKILLS.items():
        skill_prt = f"""
name: {skill[0]}
description: {skill[1]["description"]}
        """

        prompt += skill_prt
    return prompt

def read_skill(skill_name: str) -> str:
    if skill_name not in SKILLS.keys():
        return f"No Skill named {skill_name}"

    return SKILLS[skill_name]["path"].read_text()

def list_skills() -> str:
    return "\n".join(f"- {skill}" for skill in SKILLS)
