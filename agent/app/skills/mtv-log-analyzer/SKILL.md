---
name: mtv-log-analyzer
description: >-
  Analyzes Migration Toolkit for Virtualization (MTV) logs and Custom Resource
  statuses on OpenShift. Identifies migration failures, stuck migrations,
  performance issues, and common error patterns. Builds knowledge from
  past issues to improve future troubleshooting.
---

# MTV Log Analyzer Instructions

When asked to analyze MTV migration status or troubleshoot issues,
follow this methodology.

## Step 1: Identify the Migration

Determine which MTV resources to examine:
- **Migration**: The top-level migration CR
- **Plan**: The migration plan with VM list
- **VirtualMachineImport**: Per-VM import status
- **DataVolume**: Disk transfer status

## Step 2: Check Migration Status

For each VM in the migration, check:
- **Phase**: Pending, Running, Succeeded, Failed
- **Conditions**: Ready, Progressing, Available
- **Progress**: Disk transfer percentage
- **Duration**: Time elapsed vs expected

## Step 3: Identify Failure Patterns

Read `references/common-mtv-failures.md` for known issues.

Common failure categories:
- **Network**: VDDK connection failures, SSL certificate issues
- **Storage**: Insufficient space, PV provisioning failures
- **Conversion**: virt-v2v errors, driver issues
- **Timeout**: Migration exceeded time limit
- **Resource**: OOM kills, CPU throttling

## Step 4: Correlate with Logs

Check relevant pod logs:
- `forklift-controller` -- orchestration errors
- `virt-v2v` pod -- conversion errors
- `cdi-importer` -- disk import errors

## Step 5: Recommend Actions

For each issue found:
1. Severity (Critical/Warning/Info)
2. Root cause (if known from KB)
3. Resolution steps
4. Whether to retry or escalate
5. Link to relevant support article/KB entry

## Step 6: Update Knowledge Base

If a new pattern is found:
- Document the symptoms
- Document the resolution
- Tag with MTV version and environment details
