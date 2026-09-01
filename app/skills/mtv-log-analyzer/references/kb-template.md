# KB Article Template

Use this format when documenting a new finding from MTV log analysis.

## Article Structure

```markdown
# KB-YYYY-NNN: [Short Title]

## Symptoms
- What the user/operator sees (error messages, stuck states, pod statuses)
- Exact log lines or CR conditions that indicate this issue

## Environment
- MTV version: [e.g., 2.6.x]
- OCP version: [e.g., 4.14.x]
- Source: [vCenter version, ESXi version]
- Guest OS: [e.g., RHEL 8.10, Windows 2019]
- Storage: [StorageClass, CSI driver]

## Root Cause
- Technical explanation of why this happens
- Link to upstream bug if applicable

## Resolution
1. Step-by-step fix instructions
2. Commands to run
3. Expected outcome after fix

## Workaround (if no fix available)
- Temporary mitigation steps
- Limitations of the workaround

## Prevention
- Pre-migration checks that would catch this (reference playbook task names)
- Configuration changes to avoid recurrence

## Related
- Links to Red Hat KB articles, Bugzilla, or GitHub issues
- Other KB articles for similar symptoms
```

## Tagging Convention

Tag each article with:
- **Component**: `network`, `storage`, `conversion`, `resources`, `pre-migration`, `post-migration`
- **Severity**: `critical`, `high`, `medium`, `low`
- **MTV Version**: version range where this applies
- **Guest OS**: affected guest operating systems
