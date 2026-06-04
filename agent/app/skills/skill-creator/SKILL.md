---
name: skill-creator
description: >-
  Creates new ADK-compatible skill definitions from requirements.
  Generates complete SKILL.md files following the Agent Skills
  specification at agentskills.io.
---

# Skill Creator Instructions

When asked to create a new skill, generate a complete SKILL.md file.

Read `references/skill-spec.md` for the format specification.
Read `references/example-skill.md` for a working example.

Follow these rules:
1. Name must be kebab-case, max 64 characters
2. Description must be under 1024 characters
3. Instructions should be clear, step-by-step
4. Reference files in references/ for detailed domain knowledge
5. Keep SKILL.md under 500 lines
6. Output the complete file content the user can save directly
