# Post-Migration Validation Checklist

Derived from the customer's actual 333-line post-migration Ansible playbook.
Each check maps directly to a named task in the playbook output.

## Critical Checks (Migration Failed if Not Met)

| # | Category | Ansible Task Name | Pass Criteria | Failure Impact |
|---|----------|-------------------|---------------|----------------|
| 1 | Platform | `Verify OSV platform` | `ok` with "All assertions passed" -- `ansible_facts.product_name == 'OpenShift Virtualization'` | VM is still on VMware or migration incomplete |
| 2 | Platform | `Verify Linux OS` | `ok` with "All assertions passed" -- `os_family != 'Windows'` | Wrong OS for this playbook |
| 3 | ACM | `Retrieve ACM token` | `ok` (OAuth 302 redirect with access_token) | Cannot verify ACM registration |
| 4 | ACM | `Search for VM in ACM` | `ok` (GraphQL search returned results) | VM not found in ACM |
| 5 | ACM | `Verify that there is exactly one VM in ACM` | `ok` -- exactly one VirtualMachine match with cluster field | None or multiple VMs indicates registration problem |
| 6 | Validation | `Verify CPU, Memory unchanged` | `ok` -- vCPUs must match exactly, memory within 10% | Resource mismatch after migration |
| 7 | Validation | `Verify default network unchanged` | `ok` -- IP address, netmask, and gateway must all match pre-migration values | Network configuration lost during migration |

## Pre-Migration Fact Loading

| # | Category | Ansible Task Name | Pass Criteria |
|---|----------|-------------------|---------------|
| 8 | Validation | `Get osvmig_ dirs from var opt` | `ok` (found migration working directories) |
| 9 | Validation | `Identify latest osvmig_dir` | `ok` (selected most recent by mtime) |
| 10 | Validation | `Slurp premig_facts` | `ok` (read ansiblefacts.json from working dir) |
| 11 | Validation | `Load premig_facts` | `ok` (parsed JSON into premig_facts variable) |
| 12 | Validation | `Check if isBackedUp exists` | `ok` (checks for backup marker from pre-migration) |

If `osvmig_dirs.files == []`, the playbook prints a warning and skips comparison.

## vCenter Cleanup

| # | Category | Ansible Task Name | Pass Criteria |
|---|----------|-------------------|---------------|
| 13 | vCenter | `Reconfigure VM-as-Migrated Block` | included tasks follow (loops over vcenters list) |
| 14 | vCenter | `Gather lowercase VM Info from vCenter` | `ok` (found VM by lowercase name) |
| 15 | vCenter | `Gather uppercase VM Info from vCenter` | `ok` or `fatal...ignoring` (tries uppercase if lowercase not found) |
| 16 | vCenter | `Merge upper and lower vm_info` | `ok` |
| 17 | vCenter | `Count VMs in vm_info.virtual_machines` | `ok` |
| 18 | vCenter | `Assert less than two VMs in list` | `ok` with "All assertions passed" |
| 19 | vCenter | `Rename the VM` | `changed` -- VM renamed with date suffix (e.g., `hostname-20260303`) |
| 20 | vCenter | `set start_connected false for all nics on VM` | `changed` per NIC (disconnects all NICs) |
| 21 | vCenter | `Power off VM if running` | `ok`/`changed` (ensures source VM is powered off) |

**Note**: The vCenter block uses `community.vmware` collection. The warning
`Collection community.vmware does not support Ansible version 2.14.13` is expected
and does not indicate failure.

The uppercase VM search failing with `fatal...ignoring` is expected when the
lowercase search already found the VM.

## Guest Agent Swap

| # | Category | Ansible Task Name | Pass Criteria |
|---|----------|-------------------|---------------|
| 22 | Guest Agent | `Verify that vmware-guest-tools are not installed` | `ok` (rc != 0 means tools gone -- `failed_when: rc == 0`) |
| 23 | Guest Agent | `Install qemu-guest-agent` | `changed` (installed from pre-downloaded RPMs in working dir) |
| 24 | Guest Agent | `Check if qemu-ga is installed` | `changed` with rc=0 (`qemu-ga --version` succeeded) |
| 25 | Guest Agent | `Enable and start qemu-guest-agent` | `ok` (systemd service enabled and started) |

## ACM Cluster Discovery

| # | Category | Ansible Task Name | Pass Criteria |
|---|----------|-------------------|---------------|
| 26 | ACM | `Extract data from ACM lookup response` | `ok` -- hosted_cluster extracted from ACM search |
| 27 | ACM | `Get ManagedCluster` | `ok` -- ManagedCluster API returned valid response |
| 28 | ACM | `Check ManagedCluster response` | `ok` -- `oauthredirecturis.openshift.io` clusterClaim present |
| 29 | ACM | `Get OAuth redirect URI` | `ok` -- extracted redirect URI |
| 30 | ACM | `Extract hosting cluster name from OAuth redirect URL` | `ok` -- hosting cluster name parsed from URI |
| 31 | ACM | `Extract availability zone from hosting cluster name` | `ok` -- AZ letter extracted (e.g., "B") |
| 32 | ACM | `Show extracted data` | `ok` -- displays hostingCluster, hostedCluster, availabilityZone |

## CMDB Update

| # | Category | Ansible Task Name | Pass Criteria |
|---|----------|-------------------|---------------|
| 33 | CMDB | `Retrieve CloudView token` | `ok` (CloudGateway authentication) |
| 34 | CMDB | `Check CloudGateway token response` | `ok` (authToken present) |
| 35 | CMDB | `Extract CloudView token from response` | `ok` |
| 36 | CMDB | `Update VM in CMDB` | `ok` -- POST to CloudGateway with hostingCluster, hostedCluster, ACM name, availabilityZone, rcConsole |
| 37 | CMDB | `Get backup status of VM in CMDB` | `ok` -- checks backupRequired flag |

## Backup Re-Enrollment

| # | Category | Ansible Task Name | Pass Criteria |
|---|----------|-------------------|---------------|
| 38 | Backup | `Patch my name in the todo configmap` | `ok` -- only runs if `cmdb_ci_details.json.backupRequired` is true; patches `backup-vms` ConfigMap in ACM namespace `xyz-vmobj-bkp` |

## Filesystem Maintenance

| # | Category | Ansible Task Name | Pass Criteria |
|---|----------|-------------------|---------------|
| 39 | Disk | `Execute custom_fstrim.sh` | `changed` (only runs for RHEL/Rocky 8/9) |

## Comparison Tolerances (Pre vs Post)

| Property | Source Field | Tolerance |
|----------|-------------|-----------|
| CPU vCPUs | `premig_facts.processor_vcpus` vs `ansible_facts.processor_vcpus` | Exact match |
| Memory MB | `premig_facts.memtotal_mb` vs `ansible_facts.memtotal_mb` | Within 10% (ratio between 0.9 and 1.1) |
| Default IPv4 address | `premig_facts.default_ipv4.address` vs `ansible_facts.default_ipv4.address` | Exact match |
| Default netmask | `premig_facts.default_ipv4.netmask` vs `ansible_facts.default_ipv4.netmask` | Exact match |
| Default gateway | `premig_facts.default_ipv4.gateway` vs `ansible_facts.default_ipv4.gateway` | Exact match |
