---
name: post-migration-validator
description: >-
  Validates post-migration playbook results for VMware-to-OpenShift Virtualization
  migrations. Verifies 39 checks across 9 categories derived from the customer's
  actual Ansible playbook: platform verification, ACM registration, pre/post fact
  comparison, vCenter cleanup, guest agent swap, cluster discovery, CMDB update,
  backup re-enrollment, and filesystem maintenance.
---

# Post-Migration Validator Instructions

When given post-migration playbook output (raw AAP output or pasted text),
validate that the migration completed successfully and all post-migration steps
were performed.

## Step 1: Load References

Read `references/post-migration-checklist.md` for the full list of 39 checks
with exact task names, pass criteria, and failure impact.

If the user says "analyze the sample post-migration output" (or similar), load
the bundled sample from `samples/post-migration-playbook-output.txt`.

## Step 2: Platform Verification
- `Verify OSV platform`: must be `ok` with "All assertions passed"
  - Confirms `ansible_facts.product_name == 'OpenShift Virtualization'`
  - If failed: **CRITICAL** -- VM is still on VMware or migration incomplete
- `Verify Linux OS`: must be `ok`
  - Confirms `os_family != 'Windows'`
  - If failed: **CRITICAL** -- wrong playbook for Windows VMs

## Step 3: ACM Registration
- `Retrieve ACM token`: OAuth 302 redirect with access_token
- `Search for VM in ACM`: GraphQL search for VirtualMachine by name (lowercase)
- `Verify that there is exactly one VM in ACM`: exactly one match with `cluster` field
- If not found or multiple matches: **CRITICAL**

## Step 4: Pre/Post Configuration Comparison

The playbook loads saved Ansible facts from the pre-migration working directory
(`/var/opt/osvmig_*/ansiblefacts.json`) and compares:

- **CPU**: `premig_facts.processor_vcpus` must exactly match current vCPUs
- **Memory**: Current memory must be within 10% of pre-migration value
- **Network**: Default IPv4 address, netmask, and gateway must all match

If `osvmig_dirs.files == []`, the comparison is skipped with a warning.
The `Verify CPU, Memory unchanged` task uses `ignore_errors: true` -- a mismatch
is logged but does not stop the playbook.

- If CPU mismatch: **WARNING** with details
- If memory outside 10%: **WARNING** with details
- If network mismatch: **WARNING** (may indicate DHCP or NIC remapping issue)

## Step 5: vCenter Cleanup

The playbook loops over all configured vCenters to find and reconfigure the source VM:

1. Searches for VM by lowercase name, then uppercase name (one will succeed)
2. `Rename the VM`: adds date suffix (e.g., `hostname-20260303`) -- must be `changed`
3. `set start_connected false for all nics`: disconnects all NICs -- must be `changed` per NIC
4. `Power off VM if running`: ensures source VM is stopped

**Expected ignored error**: The uppercase VM search (`Gather uppercase VM Info`)
often fails with `fatal...ignoring` when the lowercase search already found the VM.
This is normal, not a failure.

**Expected warning**: `Collection community.vmware does not support Ansible version 2.14.13`
is informational and does not affect functionality.

If cleanup tasks failed: **WARNING** (manual vCenter cleanup needed)

## Step 6: Guest Agent Swap
- `Verify that vmware-guest-tools are not installed`: rc != 0 means tools are gone (the task uses `failed_when: rc == 0`, so `ok` means tools are NOT present)
- `Install qemu-guest-agent`: installed from pre-downloaded RPMs
- `Check if qemu-ga is installed`: `qemu-ga --version` must succeed (rc=0)
- `Enable and start qemu-guest-agent`: systemd service enabled and started
- If qemu-ga not installed or not started: **WARNING**

## Step 7: ACM Cluster Discovery
- `Extract data from ACM lookup response`: gets hosted_cluster name
- `Get ManagedCluster`: queries ACM API for ManagedCluster object
- `Check ManagedCluster response`: verifies `oauthredirecturis.openshift.io` clusterClaim exists
- `Get OAuth redirect URI`: extracts redirect URL
- `Extract hosting cluster name`: parses hosting cluster from OAuth URL (regex: `.apps.{cluster_name}`)
- `Extract availability zone`: parses AZ letter from hosting cluster name (regex: `-{az_letter}{digits}`)
- `Show extracted data`: displays final values (hostingCluster, hostedCluster, availabilityZone)

If any step fails: **WARNING** (cluster discovery incomplete, manual CMDB update needed)

## Step 8: CMDB Update
- `Retrieve CloudView token`: CloudGateway authentication
- `Update VM in CMDB`: POST with hostingCluster, hostedCluster, ACM name, AZ, rcConsole
- `Get backup status of VM in CMDB`: checks backupRequired flag
- If CMDB update failed: **WARNING** (manual CMDB update needed)

## Step 9: Backup Re-Enrollment
- `Patch my name in the todo configmap`: only runs if `backupRequired` is true
- Patches `backup-vms` ConfigMap in ACM namespace `xyz-vmobj-bkp`
- If backup required but enrollment failed: **WARNING**

## Step 10: Filesystem Maintenance
- `Execute custom_fstrim.sh`: runs for RHEL/Rocky 8/9 only
- If skipped for other OS: expected, not a failure

## Step 11: Produce Validation Report

Output:
1. Overall status: **VALIDATED** / **PARTIALLY VALIDATED** / **FAILED**
2. Host info: hostname, OS, platform (should be OpenShift Virtualization)
3. Per-check results table with PASS/FAIL/WARNING/SKIP
4. Pre/post comparison table (CPU, memory, network)
5. vCenter cleanup status (renamed, NICs disconnected, powered off)
6. Guest agent status (VMware tools removed, qemu-ga installed and running)
7. ACM registration details (hosted cluster, hosting cluster, AZ)
8. CMDB update status
9. Backup enrollment status
10. Critical issues (must fix immediately)
11. Warnings (fix within SLA)
12. PLAY RECAP summary (ok/changed/failed/skipped/ignored counts)
