# How to Configure GitHub Repository for Claude Code Agent

## Goal

Set up a GitHub repository with the required secrets, variables, and labels to enable automated agent builds triggered by issue approval.

**Use cases**:
- Setting up a new repository for agent-driven development
- Configuring GitHub Actions to trigger AgentCore builds
- Enabling preview deployments for completed builds

**Time required**: 15-20 minutes

## Prerequisites

### Required Access
- [ ] GitHub repository with admin permissions
- [ ] AWS account with deployed AgentCore infrastructure
- [ ] GitHub CLI (`gh`) installed (optional, for scripted setup)

### Required Information
Before starting, gather:
- AWS IAM credentials for GitHub Actions
- AgentCore IAM role ARN
- Preview deployment role ARN (if using previews)
- S3 bucket and CloudFront details (if using previews)
- List of GitHub usernames authorized to approve builds

## Steps

### 1. Configure Repository Secrets

Navigate to **Settings → Secrets and variables → Actions → Secrets**.

Add these repository secrets:

| Secret | Value |
|--------|-------|
| `AWS_ACCESS_KEY_ID` | IAM user access key for GitHub Actions |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret access key |
| `AWS_AGENTCORE_ROLE_ARN` | ARN of IAM role for invoking AgentCore |
| `AWS_PREVIEW_DEPLOY_ROLE_ARN` | ARN of IAM role for preview deployments |

#### Using GitHub CLI

```bash
# Set AWS credentials
gh secret set AWS_ACCESS_KEY_ID --body "AKIA..."
gh secret set AWS_SECRET_ACCESS_KEY --body "wJalrXUtnFEMI..."

# Set IAM role ARNs
gh secret set AWS_AGENTCORE_ROLE_ARN --body "arn:aws:iam::123456789012:role/AgentCoreInvokeRole"
gh secret set AWS_PREVIEW_DEPLOY_ROLE_ARN --body "arn:aws:iam::123456789012:role/PreviewDeployRole"
```

**Expected result**: Secrets appear in repository settings (values hidden).

### 2. Configure Repository Variables

Navigate to **Settings → Secrets and variables → Actions → Variables**.

Add these repository variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `AUTHORIZED_APPROVERS` | Comma-separated GitHub usernames | `alice,bob,charlie` |
| `PREVIEWS_BUCKET_NAME` | S3 bucket for preview deployments | `my-app-previews` |
| `PREVIEWS_CDN_DOMAIN` | CloudFront domain for previews | `d1234567890.cloudfront.net` |
| `PREVIEWS_DISTRIBUTION_ID` | CloudFront distribution ID | `E1234567890ABC` |

#### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ISSUE_LABELS` | (none) | Filter issues by labels (comma-separated) |
| `LOCK_TIMEOUT_SECONDS` | `600` | Lock timeout before auto-release (10 min) |
| `HEARTBEAT_STALENESS_SECONDS` | `300` | Session health threshold (5 min) |

#### Using GitHub CLI

```bash
# Required variables
gh variable set AUTHORIZED_APPROVERS --body "alice,bob,charlie"
gh variable set PREVIEWS_BUCKET_NAME --body "my-app-previews"
gh variable set PREVIEWS_CDN_DOMAIN --body "d1234567890.cloudfront.net"
gh variable set PREVIEWS_DISTRIBUTION_ID --body "E1234567890ABC"

# Optional variables
gh variable set ISSUE_LABELS --body "feature,approved"
gh variable set LOCK_TIMEOUT_SECONDS --body "600"
gh variable set HEARTBEAT_STALENESS_SECONDS --body "300"
```

**Expected result**: Variables appear in repository settings with their values visible.

### 3. Create Required Labels

Navigate to **Settings → Labels** or use the CLI.

Create these labels:

| Label | Color | Description |
|-------|-------|-------------|
| `agent-building` | `#FBCA04` (yellow) | Agent is actively working on this issue |
| `agent-complete` | `#0E8A16` (green) | Agent has completed this issue |
| `tests-failed` | `#D93F0B` (red) | Tests failed during agent build |

#### Using GitHub CLI

```bash
# Replace OWNER/REPO with your repository
gh api repos/OWNER/REPO/labels -f name="agent-building" -f color="FBCA04" -f description="Agent is actively working on this issue"
gh api repos/OWNER/REPO/labels -f name="agent-complete" -f color="0E8A16" -f description="Agent has completed this issue"
gh api repos/OWNER/REPO/labels -f name="tests-failed" -f color="D93F0B" -f description="Tests failed during agent build"
```

#### Batch Script

Create all labels at once:

```bash
#!/bin/bash
REPO="OWNER/REPO"

labels=(
  "agent-building:FBCA04:Agent is actively working on this issue"
  "agent-complete:0E8A16:Agent has completed this issue"
  "tests-failed:D93F0B:Tests failed during agent build"
)

for label in "${labels[@]}"; do
  IFS=':' read -r name color description <<< "$label"
  gh api "repos/$REPO/labels" -f name="$name" -f color="$color" -f description="$description" || true
done
```

**Expected result**: Labels appear in repository with correct colors.

### 4. Configure AWS Secrets Manager

The agent reads credentials from AWS Secrets Manager at runtime.

```bash
# Create Anthropic API key secret
aws secretsmanager create-secret \
  --name claude-code/reinvent/anthropic-api-key \
  --secret-string "sk-ant-..." \
  --region us-west-2

# Create GitHub token secret (for repo operations)
aws secretsmanager create-secret \
  --name claude-code/reinvent/github-token \
  --secret-string "ghp_..." \
  --region us-west-2
```

#### For Multi-Organization Setups

Create org-specific tokens:

```bash
# Org-specific token (checked first)
aws secretsmanager create-secret \
  --name claude-code/reinvent/github-token-myorg \
  --secret-string "ghp_..." \
  --region us-west-2
```

**Expected result**: Secrets exist in AWS Secrets Manager.

### 5. Verify Workflow Files

Ensure these workflow files exist in `.github/workflows/`:

| File | Purpose |
|------|---------|
| `issue-poller.yml` | Polls for approved issues every 5 minutes |
| `agent-builder.yml` | Invokes AgentCore when issue approved |
| `deploy-preview.yml` | Deploys completed builds to CloudFront |
| `stop-agent-on-close.yml` | Cleanup when issues are closed |

Check workflow status at **Actions** tab in your repository.

### 6. Test the Configuration

#### Verify Secrets Are Set

```bash
# List secrets (names only, not values)
gh secret list
```

Expected output:
```
AWS_ACCESS_KEY_ID          Updated 2025-01-15
AWS_SECRET_ACCESS_KEY      Updated 2025-01-15
AWS_AGENTCORE_ROLE_ARN     Updated 2025-01-15
AWS_PREVIEW_DEPLOY_ROLE_ARN Updated 2025-01-15
```

#### Verify Variables Are Set

```bash
gh variable list
```

Expected output:
```
AUTHORIZED_APPROVERS       alice,bob,charlie
PREVIEWS_BUCKET_NAME       my-app-previews
PREVIEWS_CDN_DOMAIN        d1234567890.cloudfront.net
PREVIEWS_DISTRIBUTION_ID   E1234567890ABC
```

#### Verify Labels Exist

```bash
gh api repos/OWNER/REPO/labels --jq '.[].name' | grep -E "agent-|tests-"
```

Expected output:
```
agent-building
agent-complete
tests-failed
```

#### Test Workflow Trigger

1. Create a test issue
2. Have an authorized approver add a `🚀` reaction
3. Check **Actions** tab for workflow execution
4. Verify `agent-building` label is applied

## Alternative Approaches

### Using GitHub Web UI Only

If you prefer not to use the CLI:

1. **Secrets**: Settings → Secrets and variables → Actions → New repository secret
2. **Variables**: Settings → Secrets and variables → Actions → Variables tab → New repository variable
3. **Labels**: Issues → Labels → New label

### Minimal Setup (No Previews)

Skip preview-related configuration if you don't need CloudFront deployments:

```bash
# Only required variables
gh variable set AUTHORIZED_APPROVERS --body "alice,bob"

# Skip these:
# PREVIEWS_BUCKET_NAME
# PREVIEWS_CDN_DOMAIN
# PREVIEWS_DISTRIBUTION_ID
```

### Issue Label Filtering

Filter which issues the agent picks up:

```bash
# Only build issues with both "feature" AND "approved" labels
gh variable set ISSUE_LABELS --body "feature,approved"
```

Issues must have **ALL** specified labels to be eligible.

## Troubleshooting

### Issue: Workflow doesn't trigger on 🚀 reaction

**Symptoms**: Adding rocket reaction does nothing

**Causes**:
1. User not in `AUTHORIZED_APPROVERS`
2. `issue-poller.yml` workflow disabled
3. Issue already has `agent-building` label

**Solution**:
```bash
# Check if user is authorized
gh variable get AUTHORIZED_APPROVERS

# Check workflow is enabled
gh workflow list

# Check issue labels
gh issue view ISSUE_NUMBER --json labels
```

### Issue: "Resource not accessible by integration"

**Symptoms**: Workflow fails with permission error

**Cause**: Workflow permissions too restrictive

**Solution**: Ensure workflow has required permissions:
```yaml
permissions:
  issues: write
  contents: read
  actions: write
```

### Issue: AWS credentials invalid

**Symptoms**: `InvalidClientTokenId` or `SignatureDoesNotMatch`

**Cause**: Incorrect AWS secrets

**Solution**:
```bash
# Verify credentials work locally
aws sts get-caller-identity

# Re-set secrets
gh secret set AWS_ACCESS_KEY_ID --body "AKIA..."
gh secret set AWS_SECRET_ACCESS_KEY --body "..."
```

### Issue: Label already exists

**Symptoms**: `422 Validation Failed` when creating labels

**Cause**: Label with same name exists

**Solution**: Update existing label instead:
```bash
gh api repos/OWNER/REPO/labels/agent-building \
  -X PATCH \
  -f color="FBCA04" \
  -f description="Agent is actively working on this issue"
```

### Issue: Stale lock prevents new builds

**Symptoms**: New issues not picked up, existing issue has `agent-building` label

**Cause**: Previous build crashed without releasing lock

**Solution**:
```bash
# Remove the stale label
gh issue edit ISSUE_NUMBER --remove-label agent-building

# Or wait for auto-release (default 10 minutes)
```

### Issue: Agent can't access repository

**Symptoms**: `git clone` fails in agent logs

**Cause**: GitHub token missing or invalid in Secrets Manager

**Solution**:
```bash
# Verify secret exists
aws secretsmanager describe-secret \
  --secret-id claude-code/reinvent/github-token \
  --region us-west-2

# Update if needed
aws secretsmanager update-secret \
  --secret-id claude-code/reinvent/github-token \
  --secret-string "ghp_new_token" \
  --region us-west-2
```

## Configuration Reference

### Required Secrets

| Secret | Description | Where to Get |
|--------|-------------|--------------|
| `AWS_ACCESS_KEY_ID` | IAM access key | AWS IAM Console → Users → Security credentials |
| `AWS_SECRET_ACCESS_KEY` | IAM secret key | Generated with access key |
| `AWS_AGENTCORE_ROLE_ARN` | AgentCore invoke role | CDK output or IAM Console |
| `AWS_PREVIEW_DEPLOY_ROLE_ARN` | Preview deploy role | CDK output or IAM Console |

### Required Variables

| Variable | Format | Example |
|----------|--------|---------|
| `AUTHORIZED_APPROVERS` | Comma-separated usernames | `alice,bob` |
| `PREVIEWS_BUCKET_NAME` | S3 bucket name | `my-previews-bucket` |
| `PREVIEWS_CDN_DOMAIN` | CloudFront domain | `d123.cloudfront.net` |
| `PREVIEWS_DISTRIBUTION_ID` | CloudFront ID | `E1234567890` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ISSUE_LABELS` | (none) | Filter by labels |
| `LOCK_TIMEOUT_SECONDS` | `600` | Lock auto-release timeout |
| `HEARTBEAT_STALENESS_SECONDS` | `300` | Session health check threshold |

## Related Tasks

- [Set Up AWS Bedrock Provider](./setup-bedrock-provider.md)
- [Deploy Infrastructure with CDK](../../infrastructure/README.md)
- [Configure Issue Label Filtering](./configure-issue-labels.md)

## Summary

You've successfully configured your GitHub repository for the Claude Code Agent. The key steps were:

1. Add AWS credentials as repository secrets
2. Set authorized approvers and preview config as variables
3. Create required labels (`agent-building`, `agent-complete`, `tests-failed`)
4. Configure AWS Secrets Manager with API keys and tokens
5. Verify workflows are enabled and test with a rocket reaction

The agent will now respond to `🚀` reactions from authorized users and automatically build features from approved issues.
