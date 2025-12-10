# Getting Started with Claude Code Agent

## Choose Your Setup Path

| Path | Time | Use Case |
|------|------|----------|
| **Local Development** | ~5 min | Test the agent locally, experiment with builds |
| **Production Deployment** | ~45 min | Full GitHub-triggered automation with previews |

---

## Path A: Local Development

Run the agent on your machine without GitHub Actions or AWS infrastructure.

### Prerequisites

- Python 3.11+
- `uv` package manager ([install](https://github.com/astral-sh/uv))
- Anthropic API key OR AWS account with Bedrock access

### Steps

#### 1. Clone and Install

```bash
git clone https://github.com/YOUR_USERNAME/long-horizon-coding-agent-demo.git
cd long-horizon-coding-agent-demo
uv pip install -r requirements.txt
```

#### 2. Configure Provider

Run the interactive setup wizard:

```bash
uv run python install.py
```

Choose your provider:
- **Anthropic**: Enter your API key
- **AWS Bedrock**: Select region and AWS profile

See [Set Up AWS Bedrock Provider](./setup-bedrock-provider.md) for detailed Bedrock configuration.

#### 3. Run the Agent

```bash
uv run python agent.py --project canopy
```

The agent will create a `generated-app/` directory and build the project.

#### 4. Verify (Optional)

```bash
# Dry run to validate configuration
uv run python agent.py --dry-run --project canopy
```

**You're done!** The agent runs locally using your configured provider.

---

## Path B: Production Deployment

Set up full GitHub-triggered automation where issues are automatically built by the agent.

### Prerequisites

- Everything from Path A
- AWS account with admin access
- GitHub repository with admin permissions
- AWS CLI and CDK installed

### Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRODUCTION SETUP SEQUENCE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Deploy Infrastructure ──► IAM roles, ECS, ECR, EFS         │
│           │                                                      │
│           ▼                                                      │
│  2. Configure Secrets ──────► API keys, GitHub tokens           │
│           │                                                      │
│           ▼                                                      │
│  3. Configure GitHub ───────► Secrets (use ARNs from step 1)    │
│           │                        Variables, Labels             │
│           ▼                                                      │
│  4. Test Locally ───────────► Verify everything works           │
│           │                                                      │
│           ▼                                                      │
│  5. Trigger via Issues ─────► 🚀 reaction starts build          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Step 1: Deploy AWS Infrastructure

Deploy the CDK stack to create required AWS resources:

```bash
cd infrastructure
npm install
cdk bootstrap  # First time only
cdk deploy
```

**Save the outputs** - you'll need these for GitHub configuration:
- `AgentCoreRoleArn`
- `PreviewDeployRoleArn`
- S3 bucket name
- CloudFront distribution ID

See [Infrastructure README](../../infrastructure/README.md) for detailed deployment options.

### Step 2: Configure AWS Secrets Manager

The agent reads secrets at runtime. Create these in your AWS region:

```bash
# Anthropic API key (required)
aws secretsmanager create-secret \
  --name claude-code/reinvent/anthropic-api-key \
  --secret-string "sk-ant-..." \
  --region us-west-2

# GitHub token for repo operations (required)
aws secretsmanager create-secret \
  --name claude-code/reinvent/github-token \
  --secret-string "ghp_..." \
  --region us-west-2
```

**Note**: Replace `reinvent` with your environment name if different.

### Step 3: Configure GitHub Repository

Set up secrets, variables, and labels using the outputs from Step 1.

```bash
# Secrets (use ARNs from CDK output)
gh secret set AWS_ACCESS_KEY_ID --body "AKIA..."
gh secret set AWS_SECRET_ACCESS_KEY --body "..."
gh secret set AWS_AGENTCORE_ROLE_ARN --body "arn:aws:iam::..."
gh secret set AWS_PREVIEW_DEPLOY_ROLE_ARN --body "arn:aws:iam::..."

# Variables
gh variable set AUTHORIZED_APPROVERS --body "your-username"
gh variable set PREVIEWS_BUCKET_NAME --body "your-bucket-name"
gh variable set PREVIEWS_CDN_DOMAIN --body "d123.cloudfront.net"
gh variable set PREVIEWS_DISTRIBUTION_ID --body "E123..."

# Labels
gh api repos/OWNER/REPO/labels -f name="agent-building" -f color="FBCA04"
gh api repos/OWNER/REPO/labels -f name="agent-complete" -f color="0E8A16"
gh api repos/OWNER/REPO/labels -f name="tests-failed" -f color="D93F0B"
```

See [Configure GitHub Repository](./configure-github-repository.md) for detailed instructions.

### Step 4: Test Locally

Before triggering via GitHub, verify your setup:

```bash
# Test provider configuration
uv run python agent.py --dry-run --project canopy

# Run a quick local build
uv run python agent.py --project canopy
```

### Step 5: Trigger via GitHub Issues

1. Create an issue describing a feature to build
2. Have an authorized user add a 🚀 reaction
3. Watch the **Actions** tab for the build workflow
4. Check the issue for progress updates and preview URL

---

## Quick Reference

| Task | Command/Action |
|------|----------------|
| Install dependencies | `uv pip install -r requirements.txt` |
| Configure provider | `uv run python install.py` |
| Run locally | `uv run python agent.py --project canopy` |
| Dry run | `uv run python agent.py --dry-run --project canopy` |
| Deploy infrastructure | `cd infrastructure && cdk deploy` |
| Trigger build | Add 🚀 to approved issue |

## Next Steps

- [GitHub Mode Setup](./github-mode-setup.md) - Target repo requirements and build flow
- [Set Up AWS Bedrock Provider](./setup-bedrock-provider.md) - Detailed Bedrock configuration
- [Configure GitHub Repository](./configure-github-repository.md) - Full GitHub setup guide
- [Infrastructure Deployment](../../infrastructure/README.md) - AWS CDK details

## Troubleshooting

### "No module named 'claude_agent_sdk'"
```bash
uv pip install -r requirements.txt
```

### "NoCredentialsError" with Bedrock
```bash
aws configure --profile ClaudeCode
# Then re-run install.py
```

### Workflow doesn't trigger on 🚀
- Check `AUTHORIZED_APPROVERS` variable includes your username
- Verify issue doesn't already have `agent-building` label
- Check Actions tab for workflow errors
