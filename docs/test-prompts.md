# Test Prompts

Categorized test prompts for the OCP Virt Migration Agent. Each prompt includes
expected behavior so testers know what to look for in the response.

## 1. Migration Readiness Assessment

### 1.1 Analyze Bundled Sample (No AAP Required)

**Prompt:**
> Analyze the sample pre-migration output and produce a readiness assessment report.

**Expected behavior:**
- Agent loads `pre-migration-analyzer` skill
- Agent loads `samples/pre-migration-playbook-output.txt` via `load_skill_resource`
- Agent loads `ansible-output-parser` skill to parse the output
- Report includes:
  - VM profile: hostname.xyz.com, RedHat 8.10, 4 vCPU, 15729 MB RAM
  - 11 check categories evaluated (Hypervisor, OS, Kernel, RPM DB, Disk, Packages, NFS, Backup, CMDB, Timezone, Uptime)
  - PLAY RECAP parsed: ok=58, changed=23, failed=0, skipped=73, ignored=2
  - Verdict: READY (or READY WITH WARNINGS)
  - NetBackup not found noted as INFO (ignored error, not a failure)
  - libffi-devel not installed noted as WARNING (ignored error)
  - Kernel/grub consistency: PASS (proccmdline matches grubgen)
  - rpmdb_fix.sh: "RPMDB not corrupted", 583 packages

### 1.2 VMware Inventory Query

**Prompt:**
> List VMware VMs available for migration in mtv-user1

**Expected behavior:**
- Agent calls `list_vmware_vms("mtv-user1")`
- Returns VM names including haproxy-user1, database-user1, winweb01-user1
- Shows CPU, memory, disk, power state, firmware for each VM

### 1.3 Assess a Specific VM from Inventory

**Prompt:**
> Assess migration readiness for database-user1 based on its VMware inventory properties

**Expected behavior:**
- Agent calls `list_vmware_vms` to get VM details
- Loads `pre-migration-analyzer` skill
- Evaluates OS compatibility, firmware, disk size, CPU/memory against criteria
- Produces readiness verdict based on inventory data (not playbook output)

## 2. Migration Monitoring and Troubleshooting

### 2.1 Check Migration Status

**Prompt:**
> What is the current status of migrations in mtv-user1?

**Expected behavior:**
- Agent calls `get_migration_status("mtv-user1")`
- Reports plan names, VM counts, phases (Completed/Running/Failed)
- Lists any active migrations

### 2.2 Read MTV Logs

**Prompt:**
> Check the forklift-controller logs in openshift-mtv for any errors

**Expected behavior:**
- Agent calls `get_pod_logs("openshift-mtv", "forklift")`
- Summarizes log content
- Identifies any error patterns

### 2.3 Diagnose a Hypothetical Failure

**Prompt:**
> A VM migration is stuck at 45% disk transfer for over 2 hours. What could be wrong and how do I fix it?

**Expected behavior:**
- Agent loads `mtv-log-analyzer` skill
- References `common-mtv-failures.md` for disk transfer timeout pattern
- Suggests checking network bandwidth between ESXi and OCP
- Recommends warm migration for large disks
- Suggests checking virt-v2v and cdi-importer pod logs

## 3. Post-Migration Validation

### 3.1 Analyze Bundled Sample (No AAP Required)

**Prompt:**
> Analyze the sample post-migration output and produce a validation report.

**Expected behavior:**
- Agent loads `post-migration-validator` skill
- Agent loads `samples/post-migration-playbook-output.txt` via `load_skill_resource`
- Report includes:
  - Platform: OpenShift Virtualization confirmed
  - ACM: VM found, exactly one match
  - Pre/post comparison: CPU, memory, network all match
  - vCenter cleanup: VM renamed, NICs disconnected, powered off
  - Guest agent: VMware tools removed, qemu-guest-agent installed and running
  - CMDB updated with hosting/hosted cluster and availability zone
  - Backup enrollment completed
  - PLAY RECAP: ok=43, changed=4, failed=0, skipped=2, ignored=1
  - Uppercase VM search failure noted as expected (ignored error)
  - Overall: VALIDATED

### 3.2 Compare Before and After

**Prompt:**
> What differences should I look for between the pre-migration and post-migration output?

**Expected behavior:**
- Agent explains the comparison checks: CPU, memory (within 10%), network (IP/netmask/gateway)
- Notes platform change from VMware to OpenShift Virtualization
- Describes guest agent swap (VMware tools -> qemu-guest-agent)
- Mentions vCenter cleanup steps

## 4. Migration Planning and Capacity Insights

### 4.1 Risk Assessment

**Prompt:**
> Assess the migration risk for a RHEL 7 VM with 500GB disk, NFS mounts, and no recent backup.

**Expected behavior:**
- Agent loads `risk-assessor` skill
- Evaluates each factor with weights:
  - OS: MEDIUM (RHEL 7 is older)
  - Disk: HIGH (500GB, NFS)
  - Backup: HIGH (no verified backup)
- Produces weighted risk score
- Recommends late migration batch, pre-migration backup

### 4.2 Batch Planning

**Prompt:**
> I have 20 VMs to migrate: 10 RHEL 8, 5 RHEL 7, 3 Rocky 9, and 2 Windows. Suggest migration batches.

**Expected behavior:**
- Agent loads `batch-planner` skill
- Groups VMs by risk and OS diversity
- Suggests 3-4 batches of 5-7 VMs each
- Windows VMs isolated or flagged (Linux playbooks don't cover Windows)
- Provides timeline estimate per batch

### 4.3 Capacity Check

**Prompt:**
> Can the target cluster handle 10 more VMs with an average of 4 vCPU and 16GB RAM each?

**Expected behavior:**
- Agent loads `capacity-analyzer` skill
- Calculates total resource demand (40 vCPU, 160GB RAM)
- Notes it would need cluster data to give a precise answer
- Explains the headroom formula (20% buffer)

## 5. End-to-End Workflow

### 5.1 Full Migration (Use With Caution -- Triggers Real Migration)

**Prompt:**
> Run a full migration workflow for haproxy-user1 in mtv-user1

**Expected behavior:**
- Agent delegates to `MigrationPipeline` (SequentialAgent)
- Phase 1: Discovery -- lists VMware VMs, finds haproxy-user1
- Phase 2: Assessment -- evaluates readiness from inventory data
- Phase 3: Migration -- creates MTV plan and triggers migration
- Phase 4: Monitor -- polls status until complete
- Phase 5: Validation -- checks migrated VM on OCP Virt
- Phase 6: Report -- generates completion report

**WARNING**: This triggers a real migration. Use only in lab/demo environments.

### 5.2 Skills Discovery

**Prompt:**
> What skills do you have available?

**Expected behavior:**
- Agent calls `list_skills`
- Returns all 10+ skills with names and descriptions
- Grouped by function (analysis, reporting, planning, workflow)

## 6. AAP Integration (Requires AAP Configuration)

### 6.1 List Job Templates

**Prompt:**
> What Ansible job templates are available?

**Expected behavior:**
- Agent calls `list_job_templates()`
- If AAP configured: returns template list with IDs, names, status
- If AAP not configured: returns message explaining AAP_URL not set

### 6.2 Run Pre-Migration Assessment via AAP

**Prompt:**
> Run the pre-migration assessment playbook for hostname.example.com

**Expected behavior:**
- Agent calls `launch_job(PRE_MIGRATION_TEMPLATE_ID)` with hostname as extra_vars
- Polls `get_job_status` until complete
- Retrieves output with `get_job_output`
- Parses with `ansible-output-parser` skill
- Produces readiness report with `assessment-report-generator` skill
