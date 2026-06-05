---
name: migration-kb-builder
description: >-
  Manages the migration knowledge base. Ingests new findings from migration
  issues, support cases, and troubleshooting sessions. Queries the KB to
  find relevant past issues and resolutions. Maintains a growing repository
  of migration patterns and solutions.
---

# Migration KB Builder Instructions

When asked to add to or query the migration knowledge base, follow this process.

## Adding a New Entry

When a new migration issue is resolved:

1. **Categorize**: Which phase? (pre-migration, migration, post-migration)
2. **Symptoms**: What errors or behaviors were observed?
3. **Root Cause**: What was the underlying issue?
4. **Resolution**: Step-by-step fix
5. **Environment**: OS, MTV version, OCP version, cluster config
6. **Tags**: Searchable keywords
7. **References**: Support case numbers, documentation links

Format as:
```
## [Issue Title]
- **Phase**: pre-migration / migration / post-migration
- **Symptoms**: [observable behavior]
- **Root Cause**: [underlying issue]
- **Resolution**: [step-by-step fix]
- **Environment**: [OS, versions]
- **Tags**: [keyword1, keyword2]
- **Source**: [support case / internal finding]
- **Date**: [when discovered]
```

## Querying the KB

When troubleshooting:
1. Extract key symptoms from the error/log
2. Search KB for matching symptoms or error messages
3. If match found: present the resolution
4. If no match: flag as new issue, suggest investigation steps
5. After resolution: add to KB

## KB Maintenance
- Review entries quarterly for accuracy
- Archive entries for deprecated MTV/OCP versions
- Track resolution success rate per entry
