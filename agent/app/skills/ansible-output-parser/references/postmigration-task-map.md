# Post-Migration Playbook Task Map

Maps each task name from the customer's post-migration playbook to its check
category. Use this to produce structured validation reports from parsed output.

Play name: `Post-migration Check Linux`

## Platform Verification

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Verify OSV platform | Platform | `ok` -- confirms `ansible_facts.product_name == "OpenShift Virtualization"` |
| Verify Linux OS | Platform | `ok` -- confirms `os_family != 'Windows'` |

## ACM Registration

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Get osvmigration service account | ACM | `ok` (loads env credentials -- no_log) |
| Retrieve ACM token | ACM | `ok` (OAuth 302 redirect with access_token) |
| Check ACM token response | ACM | `ok` (access_token present in redirect location) |
| Extract ACM token from response | ACM | `ok` |
| Search for VM in ACM | ACM | `ok` (GraphQL search via search-api returned results) |
| Verify that there is exactly one VM in ACM | ACM | `ok` -- exactly one VirtualMachine found with `cluster` field |

## ACM Cluster Discovery

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Extract data from ACM lookup response | ACM | `ok` -- hosted_cluster extracted |
| Get ManagedCluster | ACM | `ok` -- ManagedCluster API response valid |
| Check ManagedCluster response | ACM | `ok` -- `oauthredirecturis.openshift.io` clusterClaim present |
| Get OAuth redirect URI | ACM | `ok` |
| Extract hosting cluster name from OAuth redirect URL | ACM | `ok` -- hosting cluster parsed |
| Extract availability zone from hosting cluster name | ACM | `ok` -- AZ letter extracted |
| Show extracted data | ACM | `ok` -- displays hostingCluster, hostedCluster, availabilityZone in UPPERCASE |

## Pre-Migration Fact Comparison

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Get osvmig_ dirs from var opt | Validation | `ok` (found migration working directories) |
| Identify latest osvmig_dir | Validation | `ok` (selected most recent by mtime) |
| Slurp premig_facts | Validation | `ok` (read ansiblefacts.json) |
| Load premig_facts | Validation | `ok` (parsed JSON) |
| Verify CPU, Memory unchanged | Validation | `ok` -- vCPUs exact match, memory within 10% (uses `ignore_errors: true`) |
| Verify default network unchanged | Validation | `ok` -- IP, netmask, gateway must all match |
| Check if isBackedUp exists | Validation | `ok` (stat check for backup marker) |
| Warn about skipped premigration fact check | Validation | `ok` or `skipping` (only shown when no osvmig dir found) |

## vCenter Cleanup

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Get today's date in YYYYMMDD format | vCenter | `ok` |
| Reconfigure VM-as-Migrated Block | vCenter | included tasks follow (loops over vcenters) |
| Gather lowercase VM Info from vCenter | vCenter | `ok` (found VM by lowercase name) |
| Gather uppercase VM Info from vCenter | vCenter | `ok` or `fatal...ignoring` (tries uppercase; ignoring is expected if lowercase found it) |
| Merge upper and lower vm_info | vCenter | `ok` |
| Set VM Count to 0 if vm_info.virtual_machines undefined | vCenter | `ok` or `skipping` |
| Count VMs in vm_info.virtual_machines | vCenter | `ok` |
| Assert less than two VMs in list | vCenter | `ok` with "All assertions passed" |
| Rename the VM | vCenter | `changed` -- VM renamed with date suffix (e.g., hostname-20260303) |
| set start_connected false for all nics on VM | vCenter | `changed` per NIC (disconnects all NICs) |
| Power off VM if running | vCenter | `ok`/`changed` |

## Guest Agent Swap

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Verify that vmware-guest-tools are not installed | Guest Agent | `ok` (rc != 0 means tools gone; task uses `failed_when: rc == 0`) |
| Install qemu-guest-agent | Guest Agent | `changed` (installed from pre-downloaded RPMs; uses `ignore_errors: true`) |
| Check if qemu-ga is installed | Guest Agent | `changed` with rc=0 (`qemu-ga --version` succeeded; uses `ignore_errors: true`) |
| Enable and start qemu-guest-agent | Guest Agent | `ok` (systemd enabled and started; uses `ignore_errors: true`) |

## CMDB Update

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Retrieve CloudView token | CMDB | `ok` (CloudGateway POST) |
| Check CloudGateway token response | CMDB | `ok` (authToken present) |
| Extract CloudView token from response | CMDB | `ok` |
| Update VM in CMDB | CMDB | `ok` -- POST with hostingCluster, hostedCluster, ACM name, availabilityZone, rcConsole (uses `ignore_errors: true`) |
| Get backup status of VM in CMDB | CMDB | `ok` -- reads backupRequired flag |

## Backup Re-Enrollment

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Patch my name in the todo configmap | Backup | `ok` -- only runs if `backupRequired` is true; PATCH to backup-vms ConfigMap in ACM |

## Filesystem Maintenance

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Check if custom_fstrim.sh already exists | Disk | `ok` (stat check) |
| Copy custom_fstrim.sh to VM | Disk | `changed` (if not exists) |
| Execute custom_fstrim.sh | Disk | `changed` (RHEL/Rocky 8/9 only) |
| Display fstrim_result | Disk | `ok` (shows trim output) |
