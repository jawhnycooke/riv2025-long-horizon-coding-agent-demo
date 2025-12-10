# How to Set Up Claude Code Agent with AWS Bedrock

## Goal

Configure the Claude Code Agent to use Amazon Bedrock as the model provider instead of the Anthropic Direct API.

**Use cases**:
- Running the agent within AWS infrastructure using IAM roles
- Avoiding API key management by leveraging AWS credentials
- Deploying to production via Bedrock AgentCore on ECS Fargate

**Time required**: 10-15 minutes

## Prerequisites

### Required Access
- [ ] AWS account with Bedrock access
- [ ] Claude model access enabled in your AWS region
- [ ] AWS CLI installed and configured
- [ ] Python 3.11+ with `uv` or `pip`

### Required Permissions

Your AWS IAM user/role needs:
```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream"
  ],
  "Resource": "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
}
```

### Enable Claude Model Access

Before proceeding, request model access in AWS Console:
1. Navigate to **Amazon Bedrock** > **Model access**
2. Click **Manage model access**
3. Select Claude models (Opus 4.5, Sonnet 4.5, Haiku 4.5)
4. Submit request (usually instant for Claude models)

## Steps

### 1. Install Dependencies

```bash
uv pip install -r requirements.txt
```

**Expected result**: All packages install successfully including `boto3`.

### 2. Configure AWS Credentials

#### Where to Get AWS Credentials

1. Go to **AWS Console** → **IAM** → **Users**
2. Select your user (or create one with Bedrock permissions)
3. Click **Security credentials** tab
4. Under **Access keys**, click **Create access key**
5. Select **Command Line Interface (CLI)** use case
6. Copy the Access Key ID and Secret Access Key

**Important**: Save the secret key immediately—it's only shown once.

#### Option A: Named Profile (Recommended for Development)

```bash
aws configure --profile ClaudeCode
```

Enter:
- AWS Access Key ID (from step above)
- AWS Secret Access Key (from step above)
- Default region: `us-east-1` (or your preferred Bedrock region)
- Default output format: `json`

#### Option B: Environment Variables

```bash
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_REGION=us-east-1
```

#### Option C: IAM Role (Production)

For ECS/EC2, attach an IAM role with Bedrock permissions. No credential configuration needed.

### 3. Run the Setup Wizard

```bash
uv run python install.py
```

Follow the prompts:

```
? Select your model provider:
  > Amazon Bedrock
    Anthropic (Direct API)

? Select AWS region for Bedrock:
  > us-east-1
    us-west-2
    eu-west-1
    ap-northeast-1
    ap-southeast-2

? AWS Profile detected: ClaudeCode. Use this profile?
  > Yes, use ClaudeCode
    No, enter different profile
    No profile (use default credentials)
```

**Expected result**: Configuration saved to `.claude-code.json`

### 4. Verify Configuration

Check the generated configuration:

```bash
cat .claude-code.json
```

Expected output:
```json
{
  "provider": "bedrock",
  "model": "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
  "bedrock": {
    "region": "us-east-1",
    "profile": "ClaudeCode"
  },
  "anthropic": {
    "api_key_env_var": "ANTHROPIC_API_KEY"
  }
}
```

### 5. Validate Setup with Dry Run

```bash
uv run python agent.py --dry-run --project canopy
```

**Success indicator**:
```
Configuration valid, agent would run successfully
Dry run complete - configuration is valid
```

### 6. Run the Agent

```bash
uv run python agent.py --project canopy
```

The agent will now use AWS Bedrock for all Claude API calls.

## Alternative Approaches

### Override Provider via CLI

Skip the setup wizard and override the provider directly:

```bash
# Use Bedrock regardless of .claude-code.json
uv run python agent.py --project canopy --provider bedrock

# Force Anthropic API instead
uv run python agent.py --project canopy --provider anthropic
```

### Manual Configuration

Create `.claude-code.json` manually:

```bash
cat > .claude-code.json << 'EOF'
{
  "provider": "bedrock",
  "model": "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
  "bedrock": {
    "region": "us-east-1",
    "profile": null
  }
}
EOF
```

Set `"profile": null` to use default AWS credential chain (environment variables, IAM role, etc.).

### Production Deployment (Bedrock AgentCore)

For production on ECS Fargate:

1. Set environment variable in container:
   ```
   PROVIDER=bedrock
   AWS_REGION=us-east-1
   ```

2. Attach IAM role with Bedrock permissions to ECS task

3. Deploy via CDK:
   ```bash
   cd infrastructure && cdk deploy
   ```

## Supported Regions

| Region | Code |
|--------|------|
| US East (N. Virginia) | `us-east-1` |
| US West (Oregon) | `us-west-2` |
| Europe (Ireland) | `eu-west-1` |
| Asia Pacific (Tokyo) | `ap-northeast-1` |
| Asia Pacific (Sydney) | `ap-southeast-2` |

## Available Models

| Model | ID |
|-------|-----|
| Claude Opus 4.5 | `global.anthropic.claude-opus-4-5-20251101-v1:0` |
| Claude Sonnet 4.5 | `global.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| Claude Haiku 4.5 | `global.anthropic.claude-haiku-4-5-20250929-v1:0` |

## Troubleshooting

### Issue: "Could not connect to the endpoint URL"

**Symptoms**:
```
botocore.exceptions.EndpointConnectionError: Could not connect to the endpoint URL
```

**Cause**: Wrong region or network connectivity issue

**Solution**:
1. Verify region in `.claude-code.json` matches where you have model access
2. Check VPC/firewall allows outbound HTTPS to Bedrock endpoints
3. Ensure `AWS_REGION` environment variable isn't overriding config

### Issue: "Access Denied" or "UnauthorizedAccess"

**Symptoms**:
```
AccessDeniedException: User is not authorized to perform bedrock:InvokeModel
```

**Cause**: Missing IAM permissions or model access not enabled

**Solution**:
1. Check IAM policy includes `bedrock:InvokeModel` permission
2. Verify Claude model access is enabled in AWS Console
3. Confirm you're using the correct AWS profile:
   ```bash
   aws sts get-caller-identity --profile ClaudeCode
   ```

### Issue: "Model not found" or "ValidationException"

**Symptoms**:
```
ValidationException: Could not resolve the foundation model
```

**Cause**: Model not available in selected region

**Solution**:
1. Check model availability in your region via AWS Console
2. Switch to a region with broader model availability (e.g., `us-east-1`)
3. Update region in `.claude-code.json`

### Issue: "No credentials found"

**Symptoms**:
```
NoCredentialsError: Unable to locate credentials
```

**Cause**: AWS credentials not configured or wrong profile

**Solution**:
1. Verify profile exists:
   ```bash
   aws configure list --profile ClaudeCode
   ```
2. Check `AWS_PROFILE` environment variable isn't set incorrectly
3. For IAM roles, verify instance metadata service is accessible

### Issue: Dry run passes but agent fails

**Cause**: Dry run validates configuration but doesn't make actual API calls

**Solution**:
1. Check CloudWatch logs for detailed error messages
2. Test Bedrock access directly:
   ```bash
   aws bedrock-runtime invoke-model \
     --model-id anthropic.claude-3-sonnet-20240229-v1:0 \
     --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":100,"messages":[{"role":"user","content":"Hello"}]}' \
     --region us-east-1 \
     output.json
   ```

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `CLAUDE_CODE_USE_BEDROCK` | Set automatically by config | `0` |
| `AWS_REGION` | AWS region for Bedrock | `us-east-1` |
| `AWS_PROFILE` | AWS CLI profile name | None |
| `PROVIDER` | Provider override (bedrock/anthropic) | `anthropic` |

## Related Tasks

- [Deploy to AWS with CDK](../../infrastructure/README.md)
- [Configure GitHub Repository](./configure-github-repository.md)
- [Set Up OpenTelemetry Tracing](./setup-tracing.md)

## Summary

You've successfully configured the Claude Code Agent to use AWS Bedrock. The key steps were:

1. Enable Claude model access in AWS Bedrock
2. Configure AWS credentials (profile or IAM role)
3. Run `uv run python install.py` and select Bedrock
4. Validate with `--dry-run` flag
5. Run the agent

The agent will now authenticate via AWS credentials and invoke Claude models through the Bedrock API.
