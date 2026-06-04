# Agent Skills Specification (agentskills.io)

## SKILL.md Format
Every skill directory must contain a SKILL.md file.

### Frontmatter (YAML)
```yaml
---
name: my-skill-name          # kebab-case, max 64 chars
description: What this skill does.  # max 1024 chars
---
```

### Body (Markdown)
The body contains the skill instructions. Write clear,
step-by-step instructions the agent will follow.

### Directory Structure
```
my-skill-name/
  SKILL.md           # Required: metadata + instructions
  references/        # Optional: detailed reference docs
  assets/            # Optional: templates, data files
  scripts/           # Optional: executable scripts
```

### Key Rules
- Directory name MUST match the `name` field in frontmatter
- Name must be kebab-case: ^[a-z0-9]+(-[a-z0-9]+)*$
- Description is what the LLM uses to decide when to load the skill
- Keep instructions actionable -- tell the agent WHAT to do
- Use `load_skill_resource` references for detailed docs
