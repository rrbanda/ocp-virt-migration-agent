"""ADK Skills Agent — loads all skills dynamically from a configurable directory.

Skills are SKILL.md files following the agentskills.io specification.
They can be mounted as ConfigMaps/Volumes without rebuilding the image.

Configuration via environment variables:
  ADK_MODEL      - LLM model string (default: openai/gemini/models/gemini-2.5-flash)
  SKILLS_DIR     - Path to skills directory (default: /skills)
  AGENT_NAME     - Agent name (default: skills_agent)
  AGENT_DESC     - Agent description
  AGENT_INSTRUCTION - Agent system instruction (or loaded from AGENT_INSTRUCTION_FILE)
  AGENT_INSTRUCTION_FILE - Path to a markdown file with the agent instruction
"""

import os
import pathlib

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

ADK_MODEL = os.environ.get("ADK_MODEL", "openai/gemini/models/gemini-2.5-flash")
SKILLS_DIR = pathlib.Path(os.environ.get("SKILLS_DIR", "/skills"))
AGENT_NAME = os.environ.get("AGENT_NAME", "skills_agent")
AGENT_DESC = os.environ.get("AGENT_DESC", "An agent powered by configurable skills.")

DEFAULT_INSTRUCTION = (
    "You are a helpful assistant with specialized skills.\n\n"
    "Use `list_skills` to see what skills are available.\n"
    "Use `load_skill` to load a skill's detailed instructions.\n"
    "Use `load_skill_resource` to access reference materials.\n\n"
    "Always explain which skill you're using and why."
)


def _load_instruction() -> str:
    instruction_file = os.environ.get("AGENT_INSTRUCTION_FILE")
    if instruction_file and pathlib.Path(instruction_file).exists():
        return pathlib.Path(instruction_file).read_text()
    return os.environ.get("AGENT_INSTRUCTION", DEFAULT_INSTRUCTION)


def _discover_skills(skills_dir: pathlib.Path) -> list:
    """Discover and load all skills from subdirectories containing SKILL.md."""
    skills = []
    if not skills_dir.exists():
        print(f"WARNING: Skills directory {skills_dir} does not exist")
        return skills

    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir() and (entry / "SKILL.md").exists():
            try:
                skill = load_skill_from_dir(entry)
                skills.append(skill)
                print(f"Loaded skill: {entry.name}")
            except Exception as e:
                print(f"WARNING: Failed to load skill from {entry}: {e}")
    return skills


skills = _discover_skills(SKILLS_DIR)
print(f"Discovered {len(skills)} skills from {SKILLS_DIR}")

skill_toolset = SkillToolset(skills=skills) if skills else None

root_agent = Agent(
    model=LiteLlm(model=ADK_MODEL),
    name=AGENT_NAME,
    description=AGENT_DESC,
    instruction=_load_instruction(),
    tools=[skill_toolset] if skill_toolset else [],
)
