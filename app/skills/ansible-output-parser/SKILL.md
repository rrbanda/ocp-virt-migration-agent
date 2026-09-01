---
name: ansible-output-parser
description: >-
  Parses Ansible playbook output from AAP/Tower job output format into structured
  data. Handles the customer's specific output format including Slice/partition
  headers, SSH key passphrase prompts, assertion results, ignored errors, and
  deprecation warnings. Extracts each task's name, status, host, and details.
  Specialized for VMware-to-OCP Virt pre-migration and post-migration playbooks.
---

# Ansible Output Parser Instructions

When given raw Ansible playbook output (from AAP or pasted), parse it into a
structured analysis.

## Step 1: Handle AAP Job Output Preamble

The customer's AAP output starts with a preamble before the Ansible output:

```
STDOUT_lines :
No STDOUT available for this Task

STDERR_lines :
No STDERR available for this Task
Playbook Output:
Slice 1.map.0:
JOB partition 1 : Slice number 0:

Enter passphrase for /runner/artifacts/{job_id}/ssh_key_data:
Identity added: /runner/artifacts/{job_id}/ssh_key_data (...)
```

**Skip this entire preamble.** The actual playbook output begins at the `PLAY [...]` line.

## Step 2: Identify the Play

Look for lines starting with `PLAY [` to identify the play name:
- `PLAY [Pre-migration Check]` -- pre-migration assessment playbook
- `PLAY [Post-migration Check Linux]` -- post-migration validation playbook

## Step 3: Parse Each Task

For each `TASK [task name]` block, extract:

- **Task name**: The text inside `TASK [...]`
- **Status**: One of:
  - `ok` -- task succeeded without changes
  - `changed` -- task succeeded with changes
  - `failed` / `fatal` -- task failed
  - `skipping` -- task was skipped (conditional not met)
- **Host**: The hostname in the status line (e.g., `ok: [hostname.xyz.com]`)
- **Details**: assertion messages, debug output, error messages

### Status Line Formats

```
ok: [hostname.xyz.com]
ok: [hostname.xyz.com] => { "changed": false, "msg": "All assertions passed" }
ok: [hostname.xyz.com] => { "msg": "RedHat 8.10" }
changed: [hostname.xyz.com]
changed: [hostname.xyz.com] => (item=xmlsec1-openssl)
skipping: [hostname.xyz.com]
skipping: [hostname.xyz.com] => (item=xmlsec1-openssl)
fatal: [hostname.xyz.com]: FAILED! => {"changed": true, "cmd": "...", "rc": 127, ...}
fatal: [hostname.xyz.com -> 127.0.0.1]: FAILED! => {"changed": false, "msg": "Failed to find virtual machine VM-NAME"}
failed: [hostname.xyz.com] (item=libffi-devel) => {"rc": 1, "stderr": "Error:\nPackage libffi-devel is not installed.", ...}
```

### Assertion Results
Assertions use this format:
```
ok: [hostname.xyz.com] => {
"changed": false,
"msg": "All assertions passed"
}
```

### Debug Output
Debug tasks show structured data:
```
ok: [hostname.xyz.com] => {
"msg": "cpu: 4, memory_mb: 15729"
}
```

Or complex structures:
```
ok: [hostname.xyz.com] => {
"proccmdline_list": [
"root=/dev/mapper/rootvg-rootlv",
"ro",
...
]
}
```

### Loop Items
Tasks with loops show per-item results:
```
ok: [hostname.xyz.com] => (item=lo) => { "msg": "lo []: {'address': '127.0.0.1', ...}" }
ok: [hostname.xyz.com] => (item=eth0) => { "msg": "eth0 [00:50:56:ab:c5:04]: ..." }
```

Mount point assertions loop over all mounts:
```
ok: [hostname.xyz.com] => (item={'mount': '/', 'device': '/dev/mapper/rootvg-rootlv', ...}) => {
"msg": "All assertions passed"
}
skipping: [hostname.xyz.com] => (item={'mount': '/boot', ...})
```

## Step 4: Handle Warnings

Lines starting with `[WARNING]:` or `[DEPRECATION WARNING]:` are informational:
```
[WARNING]: Consider using the yum, dnf or zypper module rather than running 'rpm'.
[DEPRECATION WARNING]: Distribution redhat 8.10 on host hostname.xyz.com should use /usr/libexec/platform-python...
[WARNING]: Collection community.vmware does not support Ansible version 2.14.13
```

These do NOT indicate failures. Note them but do not classify as errors.

## Step 5: Handle Ignored Errors

The pattern `fatal: [...] FAILED! => {...}\n...ignoring` means the task failed
but had `ignore_errors: true`. The playbook continues.

```
fatal: [hostname.xyz.com]: FAILED! => {"rc": 127, "stderr": "No such file or directory", ...}
...ignoring
```

Also, failed items in a loop followed by `...ignoring`:
```
failed: [hostname.xyz.com] (item=libffi-devel) => {"rc": 1, "stderr": "Package libffi-devel is not installed.", ...}
changed: [hostname.xyz.com] => (item=pciutils)
...ignoring
```

Classify these as **WARNING** or **INFO**, not FAIL.

## Step 6: Parse the PLAY RECAP

The `PLAY RECAP` line contains the summary:
```
PLAY RECAP *********************************************************************
hostname.xyz.com : ok=58 changed=23 unreachable=0 failed=0 skipped=73 rescued=0 ignored=2
```

Extract each counter. Key interpretation:
- `failed=0` means the playbook completed successfully overall
- `ignored` count reflects tasks that failed but had `ignore_errors`
- High `skipped` count is normal due to OS-specific branching
- `unreachable` > 0 means SSH connection issues

## Step 7: Categorize Results

Use `load_skill_resource` to read the appropriate task map:
- For `Pre-migration Check`: read `references/premigration-task-map.md`
- For `Post-migration Check Linux`: read `references/postmigration-task-map.md`

Classify each task:
- **PASS**: Status `ok` with "All assertions passed", or just `ok`/`changed`
- **FAIL**: Status `failed` or `fatal` (not followed by `...ignoring`)
- **WARNING**: Status `failed`/`fatal` but with `...ignoring`
- **SKIP**: Status `skipping` (conditional not met -- often OS-specific branching)
- **INFO**: Debug messages, variable outputs, set_fact operations

## Step 8: Output Format

```
## Playbook Summary
- Play: [play name]
- Host: [hostname]
- OS: [distribution + version]
- Result: [overall pass/fail based on PLAY RECAP]
- Tasks: ok=[N] changed=[N] failed=[N] skipped=[N] ignored=[N]

## Task Results by Category
| # | Task | Category | Status | Details |
|---|------|----------|--------|---------|
| 1 | task name | category | PASS/FAIL/WARN/SKIP/INFO | details |

## Failures & Warnings
- [list any failed or warning tasks with full details and error messages]

## Key Findings
- Hostname: [from output]
- OS: [distribution + version from "Operating System" task]
- CPU: [vCPUs from "CPU and Memory" task]
- Memory: [MB from "CPU and Memory" task]
- Disk: [mount points and free space from "Mount points" task]
- Network: [interfaces and IPs from "Network Interfaces" task]
- Platform: [VMware / OpenShift Virtualization]
- Kernel: [grub consistency status]
- RPM DB: [corruption check result]
- Backup: [NetBackup status]
- CMDB: [lifecycle status]
```
