// Copyright 2025-present Anthropic PBC.
// Licensed under Apache 2.0

import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as efs from 'aws-cdk-lib/aws-efs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as backup from 'aws-cdk-lib/aws-backup';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cr from 'aws-cdk-lib/custom-resources';
import { Construct } from 'constructs';

export interface ClaudeCodeStackProps extends cdk.StackProps {
  projectName: string;
  environment: string;
  logRetentionDays: number;
}

/**
 * Core Infrastructure Stack for Two-Container ECS Architecture
 *
 * This stack provides core infrastructure shared across the architecture:
 * - VPC (networking)
 * - ECR repository (stores container images)
 * - EFS file system (persistent storage for worker state)
 * - Secrets Manager (API keys)
 * - S3 + CloudFront (screenshots and app previews)
 * - CloudWatch dashboard (observability)
 * - Backup (EFS snapshots)
 *
 * Exports VPC, EFS, and ECR for use by ECS and Step Functions stacks.
 */
export class ClaudeCodeStack extends cdk.Stack {
  // Exported resources for dependent stacks
  public readonly vpc: ec2.Vpc;
  public readonly fileSystem: efs.FileSystem;
  public readonly accessPoint: efs.AccessPoint;
  public readonly repository: ecr.Repository;

  constructor(scope: Construct, id: string, props: ClaudeCodeStackProps) {
    super(scope, id, props);

    const { projectName, environment, logRetentionDays } = props;

    // ========================================================================
    // VPC - Required for EFS and ECS
    // ========================================================================
    // NOTE: VPC uses public subnets only (no NAT gateways) for cost savings.
    // ECS tasks use assignPublicIp: true for outbound internet access.
    // Trade-offs:
    // - Cost: No NAT gateway charges (~$0.045/hour/gateway)
    // - Security: Containers have public IPs (but security groups restrict inbound)
    // - Scaling: Limited by available public IPs (not typically an issue for this use case)
    // For production with strict security requirements, add natGateways: 1 and use PRIVATE subnets.
    this.vpc = new ec2.Vpc(this, 'VPC', {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        {
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
      ],
    });

    // ========================================================================
    // ECR Repository - Stores orchestrator and worker container images
    // ========================================================================
    this.repository = new ecr.Repository(this, 'Repository', {
      repositoryName: `${projectName}-${environment}`,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      lifecycleRules: [
        {
          description: 'Keep last 10 images',
          maxImageCount: 10,
        },
      ],
    });

    // ========================================================================
    // EFS File System - Persistent storage for worker state
    // ========================================================================
    this.fileSystem = new efs.FileSystem(this, 'FileSystem', {
      vpc: this.vpc,
      performanceMode: efs.PerformanceMode.GENERAL_PURPOSE,
      throughputMode: efs.ThroughputMode.BURSTING,
      encrypted: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      enableAutomaticBackups: true,
    });

    // Create access point for worker containers
    // UID/GID 1000 matches the default non-root user in the python:3.12-slim image.
    // If the container runs as root (UID 0), EFS access will work due to IAM authorization.
    // The access point enforces these credentials regardless of container user.
    this.accessPoint = this.fileSystem.addAccessPoint('AgentAccessPoint', {
      path: '/projects',
      createAcl: {
        ownerUid: '1000',
        ownerGid: '1000',
        permissions: '755',
      },
      posixUser: {
        uid: '1000',
        gid: '1000',
      },
    });

    // ========================================================================
    // Secrets Manager - Store API keys and tokens
    // ========================================================================
    // Note: Secrets are referenced by name in ECS stack using fromSecretNameV2().
    // This pattern avoids circular dependencies but requires secrets to exist before
    // deploying dependent stacks. If you need tighter coupling, export secret ARNs
    // via CfnOutput and use Fn.importValue() in consuming stacks.
    const anthropicApiKey = new secretsmanager.Secret(this, 'AnthropicApiKey', {
      secretName: `${projectName}/${environment}/anthropic-api-key`,
      description: 'Anthropic API key for Claude Code Agent',
    });

    // Import existing GitHub token secret (created manually)
    // To create: aws secretsmanager create-secret --name "project/env/github-token" --secret-string "ghp_..."
    const githubToken = secretsmanager.Secret.fromSecretNameV2(
      this,
      'GitHubToken',
      `${projectName}/${environment}/github-token`
    );

    // ========================================================================
    // CloudWatch Log Group - For core infrastructure observability
    // Note: ECS task logs are managed by EcsClusterStack
    // ========================================================================
    // Map logRetentionDays to CDK RetentionDays enum
    const retentionMap: { [key: number]: logs.RetentionDays } = {
      1: logs.RetentionDays.ONE_DAY,
      3: logs.RetentionDays.THREE_DAYS,
      5: logs.RetentionDays.FIVE_DAYS,
      7: logs.RetentionDays.ONE_WEEK,
      14: logs.RetentionDays.TWO_WEEKS,
      30: logs.RetentionDays.ONE_MONTH,
      60: logs.RetentionDays.TWO_MONTHS,
      90: logs.RetentionDays.THREE_MONTHS,
    };
    const logRetention = retentionMap[logRetentionDays] ?? logs.RetentionDays.TWO_WEEKS;

    const logGroup = new logs.LogGroup(this, 'LogGroup', {
      logGroupName: `/claude-code/${projectName}-${environment}`,
      retention: logRetention,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ========================================================================
    // AWS Backup - Daily EFS snapshots
    // ========================================================================
    const backupVault = new backup.BackupVault(this, 'BackupVault', {
      backupVaultName: `${projectName}-${environment}-vault`,
    });

    const backupPlan = new backup.BackupPlan(this, 'BackupPlan', {
      backupPlanName: `${projectName}-${environment}-daily`,
      backupPlanRules: [
        new backup.BackupPlanRule({
          ruleName: 'DailyBackup',
          scheduleExpression: cdk.aws_events.Schedule.cron({
            hour: '2',
            minute: '0',
          }),
          deleteAfter: cdk.Duration.days(35),
        }),
      ],
    });

    backupPlan.addSelection('EfsBackupSelection', {
      resources: [backup.BackupResource.fromEfsFileSystem(this.fileSystem)],
    });

    // ========================================================================
    // IAM Role for GitHub Actions (Orchestrator/Step Functions Invocation)
    // ========================================================================
    const githubOrchestratorRole = new iam.Role(this, 'GitHubOrchestratorRole', {
      roleName: `${projectName}-github-orchestrator-invoker`,
      description: 'Role for GitHub Actions to invoke ECS orchestrator and monitor Step Functions',
      assumedBy: new iam.AccountPrincipal(cdk.Stack.of(this).account),
      maxSessionDuration: cdk.Duration.hours(8),
    });

    githubOrchestratorRole.assumeRolePolicy?.addStatements(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        principals: [new iam.AccountPrincipal(cdk.Stack.of(this).account)],
        actions: ['sts:TagSession'],
      })
    );

    // Grant ECS permissions to start/stop orchestrator tasks
    githubOrchestratorRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'ecs:RunTask',
        'ecs:StopTask',
        'ecs:DescribeTasks',
        'ecs:DescribeServices',
        'ecs:UpdateService',
      ],
      resources: [
        `arn:aws:ecs:${this.region}:${this.account}:cluster/${projectName}-${environment}`,
        `arn:aws:ecs:${this.region}:${this.account}:task/${projectName}-${environment}/*`,
        `arn:aws:ecs:${this.region}:${this.account}:service/${projectName}-${environment}/*`,
        `arn:aws:ecs:${this.region}:${this.account}:task-definition/${projectName}-${environment}-*`,
      ],
    }));

    // Grant Step Functions permissions to monitor worker executions
    githubOrchestratorRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'states:DescribeExecution',
        'states:ListExecutions',
        'states:StopExecution',
      ],
      resources: [
        `arn:aws:states:${this.region}:${this.account}:stateMachine:${projectName}-${environment}-worker`,
        `arn:aws:states:${this.region}:${this.account}:execution:${projectName}-${environment}-worker:*`,
      ],
    }));

    // Grant IAM PassRole for ECS task execution
    githubOrchestratorRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['iam:PassRole'],
      resources: [
        `arn:aws:iam::${this.account}:role/${projectName}-${environment}-*`,
      ],
    }));

    // Grant Secrets Manager read
    githubOrchestratorRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['secretsmanager:GetSecretValue'],
      resources: [
        `arn:aws:secretsmanager:${this.region}:${this.account}:secret:${projectName}/*`,
      ],
    }));

    // Grant SSM Parameter Store read access (for health monitor to read current issue)
    githubOrchestratorRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['ssm:GetParameter'],
      resources: [
        `arn:aws:ssm:${this.region}:${this.account}:parameter/${projectName}/*`,
      ],
    }));

    // Grant CloudWatch read access (for health monitor to check heartbeat metrics)
    githubOrchestratorRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['cloudwatch:GetMetricStatistics'],
      resources: ['*'],
    }));

    // Note: ECS task roles for orchestrator and worker are defined in EcsClusterStack
    // They are granted secrets, CloudWatch, and S3 permissions there.

    // ========================================================================
    // S3 Bucket + CloudFront - Screenshot storage for agent builds
    // ========================================================================
    const screenshotsBucket = new s3.Bucket(this, 'ScreenshotsBucket', {
      bucketName: `${projectName}-${environment}-screenshots`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // CloudFront distribution for serving screenshots
    const screenshotsDistribution = new cloudfront.Distribution(this, 'ScreenshotsDistribution', {
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(screenshotsBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
      },
      comment: `${projectName} agent screenshots`,
    });

    // Note: S3 write permissions for worker containers are granted in EcsClusterStack

    // ========================================================================
    // S3 Bucket + CloudFront - App Preview hosting for agent builds
    // ========================================================================
    const previewsBucket = new s3.Bucket(this, 'PreviewsBucket', {
      bucketName: `${projectName}-${environment}-previews`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      lifecycleRules: [
        {
          id: 'ExpireOldPreviews',
          enabled: true,
          expiration: cdk.Duration.days(30),
          prefix: 'previews/',
        },
        {
          id: 'AbortIncompleteUploads',
          enabled: true,
          abortIncompleteMultipartUploadAfter: cdk.Duration.days(1),
        },
      ],
    });

    // CloudFront Function for SPA routing (rewrites non-file paths to index.html)
    const spaRoutingFunction = new cloudfront.Function(this, 'SpaRoutingFunction', {
      functionName: `${projectName}-${environment}-spa-routing`,
      code: cloudfront.FunctionCode.fromInline(`
function handler(event) {
  var request = event.request;
  var uri = request.uri;

  // Match /previews/issue-{N}/... pattern
  var match = uri.match(/^\\/previews\\/issue-(\\d+)(\\/.*)?$/);
  if (match) {
    var issueNum = match[1];
    var subPath = match[2] || '/';

    // No file extension = SPA route, serve index.html
    if (!subPath.match(/\\.[a-zA-Z0-9]+$/)) {
      request.uri = '/previews/issue-' + issueNum + '/index.html';
    }
  }
  return request;
}
      `),
      runtime: cloudfront.FunctionRuntime.JS_2_0,
      comment: 'SPA routing for app previews',
    });

    // Custom cache policy for previews (shorter TTL for active development)
    const previewsCachePolicy = new cloudfront.CachePolicy(this, 'PreviewsCachePolicy', {
      cachePolicyName: `${projectName}-${environment}-previews-cache`,
      comment: 'Cache policy for SPA preview deployments',
      defaultTtl: cdk.Duration.hours(1),
      maxTtl: cdk.Duration.days(1),
      minTtl: cdk.Duration.seconds(0),
      enableAcceptEncodingGzip: true,
      enableAcceptEncodingBrotli: true,
      queryStringBehavior: cloudfront.CacheQueryStringBehavior.all(),
    });

    // CloudFront distribution for serving app previews
    const previewsDistribution = new cloudfront.Distribution(this, 'PreviewsDistribution', {
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(previewsBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: previewsCachePolicy,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
        cachedMethods: cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
        functionAssociations: [
          {
            function: spaRoutingFunction,
            eventType: cloudfront.FunctionEventType.VIEWER_REQUEST,
          },
        ],
      },
      comment: `${projectName} app previews`,
    });

    // Note: S3 write permissions for worker containers are granted in EcsClusterStack

    // IAM Role for GitHub Actions Preview Deployment
    const githubPreviewDeployRole = new iam.Role(this, 'GitHubPreviewDeployRole', {
      roleName: `${projectName}-github-preview-deploy`,
      description: 'Role for GitHub Actions to deploy app previews to S3/CloudFront',
      assumedBy: new iam.AccountPrincipal(cdk.Stack.of(this).account),
      maxSessionDuration: cdk.Duration.hours(1),
    });

    githubPreviewDeployRole.assumeRolePolicy?.addStatements(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        principals: [new iam.AccountPrincipal(cdk.Stack.of(this).account)],
        actions: ['sts:TagSession'],
      })
    );

    // S3 permissions for preview deployment
    githubPreviewDeployRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        's3:PutObject',
        's3:DeleteObject',
        's3:ListBucket',
        's3:GetObject',
      ],
      resources: [
        previewsBucket.bucketArn,
        `${previewsBucket.bucketArn}/*`,
      ],
    }));

    // CloudFront invalidation permission for preview deployment
    githubPreviewDeployRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['cloudfront:CreateInvalidation'],
      resources: [
        `arn:aws:cloudfront::${this.account}:distribution/${previewsDistribution.distributionId}`,
      ],
    }));

    // Grant the GitHub Actions deployer user permission to assume the preview deploy role
    // PREREQUISITE: The IAM user 'github-actions-deployer' must be created manually before deployment.
    // Create it via AWS Console or CLI:
    //   aws iam create-user --user-name github-actions-deployer
    //   aws iam create-access-key --user-name github-actions-deployer
    // Store the access key in GitHub Secrets: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
    const githubActionsUser = iam.User.fromUserName(
      this,
      'GitHubActionsUser',
      'github-actions-deployer'
    );

    new iam.Policy(this, 'GitHubActionsUserPreviewDeployPolicy', {
      policyName: 'AllowAssumePreviewDeployRole',
      users: [githubActionsUser],
      statements: [
        new iam.PolicyStatement({
          sid: 'AllowAssumePreviewDeployRole',
          effect: iam.Effect.ALLOW,
          actions: ['sts:AssumeRole', 'sts:TagSession'],
          resources: [githubPreviewDeployRole.roleArn],
        }),
      ],
    });

    // ========================================================================
    // CloudWatch Dashboard - Agent Monitoring for re:Invent Demo
    // ========================================================================
    // Note: Worker logs go to ECS log groups managed by EcsClusterStack
    // Orchestrator: /ecs/{project}-{env}/orchestrator
    // Worker: /ecs/{project}-{env}/worker
    const workerLogGroupName = `/ecs/${projectName}-${environment}/worker`;
    const orchestratorLogGroupName = `/ecs/${projectName}-${environment}/orchestrator`;

    // Dashboard variable for filtering by Issue Number
    // Use fromSearch with explicit search string that includes ALL dimensions
    const issueVariable = new cloudwatch.DashboardVariable({
      id: 'issueNumber',
      type: cloudwatch.VariableType.PROPERTY,
      label: 'Issue Number',
      inputType: cloudwatch.VariableInputType.SELECT,
      value: 'IssueNumber',
      values: cloudwatch.Values.fromSearch(
        '{ClaudeCodeAgent,Environment,IssueNumber} MetricName="APICallCount"',
        'IssueNumber'
      ),
      defaultValue: cloudwatch.DefaultValue.FIRST,
      visible: true,
    });

    const dashboard = new cloudwatch.Dashboard(this, 'AgentDashboard', {
      dashboardName: `${projectName}-${environment}-agent-dashboard`,
      defaultInterval: cdk.Duration.hours(12),
      variables: [issueVariable],
    });

    // Row 1: Hero Metrics (Big Numbers) - Custom Metrics from agent
    dashboard.addWidgets(
      new cloudwatch.SingleValueWidget({
        title: 'API Calls',
        metrics: [new cloudwatch.Metric({
          namespace: 'ClaudeCodeAgent',
          metricName: 'APICallCount',
          dimensionsMap: { Environment: environment, IssueNumber: '${issueNumber}' },
          statistic: 'Maximum',
          period: cdk.Duration.minutes(1),
        })],
        width: 8,
        height: 4,
      }),
      new cloudwatch.SingleValueWidget({
        title: 'Total Commits',
        metrics: [new cloudwatch.Metric({
          namespace: 'ClaudeCodeAgent',
          metricName: 'TotalCommits',
          dimensionsMap: { Environment: environment, IssueNumber: '${issueNumber}' },
          statistic: 'Maximum',
          period: cdk.Duration.minutes(1),
        })],
        width: 8,
        height: 4,
      }),
      new cloudwatch.SingleValueWidget({
        title: 'Cost (cents)',
        metrics: [new cloudwatch.Metric({
          namespace: 'ClaudeCodeAgent',
          metricName: 'TotalCostCents',
          dimensionsMap: { Environment: environment, IssueNumber: '${issueNumber}' },
          statistic: 'Maximum',
          period: cdk.Duration.minutes(1),
        })],
        width: 8,
        height: 4,
      }),
    );

    // Row 2: Token Usage Over Time (Line Graph)
    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Token Usage Over Time',
        left: [
          new cloudwatch.Metric({
            namespace: 'ClaudeCodeAgent',
            metricName: 'InputTokens',
            dimensionsMap: { Environment: environment, IssueNumber: '${issueNumber}' },
            statistic: 'Maximum',
            period: cdk.Duration.minutes(5),
            label: 'Input Tokens',
          }),
          new cloudwatch.Metric({
            namespace: 'ClaudeCodeAgent',
            metricName: 'OutputTokens',
            dimensionsMap: { Environment: environment, IssueNumber: '${issueNumber}' },
            statistic: 'Maximum',
            period: cdk.Duration.minutes(5),
            label: 'Output Tokens',
          }),
        ],
        width: 12,
        height: 6,
      }),
      new cloudwatch.GraphWidget({
        title: 'Session Progress',
        left: [
          new cloudwatch.Metric({
            namespace: 'ClaudeCodeAgent',
            metricName: 'ElapsedHours',
            dimensionsMap: { Environment: environment, IssueNumber: '${issueNumber}' },
            statistic: 'Maximum',
            period: cdk.Duration.minutes(5),
            label: 'Elapsed Hours',
          }),
        ],
        right: [
          new cloudwatch.Metric({
            namespace: 'ClaudeCodeAgent',
            metricName: 'RemainingHours',
            dimensionsMap: { Environment: environment, IssueNumber: '${issueNumber}' },
            statistic: 'Maximum',
            period: cdk.Duration.minutes(5),
            label: 'Remaining Hours',
          }),
        ],
        width: 12,
        height: 6,
      }),
    );

    // Row 3: Git Activity & Screenshots
    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Git Activity',
        left: [
          new cloudwatch.Metric({
            namespace: 'ClaudeCodeAgent',
            metricName: 'CommitsPushed',
            dimensionsMap: { Environment: environment, IssueNumber: '${issueNumber}' },
            statistic: 'Sum',
            period: cdk.Duration.minutes(5),
            label: 'Commits Pushed',
          }),
        ],
        right: [
          new cloudwatch.Metric({
            namespace: 'ClaudeCodeAgent',
            metricName: 'ScreenshotsUploaded',
            dimensionsMap: { Environment: environment, IssueNumber: '${issueNumber}' },
            statistic: 'Sum',
            period: cdk.Duration.minutes(5),
            label: 'Screenshots',
          }),
        ],
        width: 12,
        height: 6,
      }),
      new cloudwatch.GraphWidget({
        title: 'Cost Over Time (cents)',
        left: [
          new cloudwatch.Metric({
            namespace: 'ClaudeCodeAgent',
            metricName: 'TotalCostCents',
            dimensionsMap: { Environment: environment, IssueNumber: '${issueNumber}' },
            statistic: 'Maximum',
            period: cdk.Duration.minutes(5),
            label: 'Cumulative Cost',
          }),
        ],
        width: 12,
        height: 6,
      }),
    );

    // Row 4: Logs Insights - Tool Usage Distribution (Pie Chart)
    // These queries filter by issue number using the [issue:N] tag added to Tool Call logs
    // and the "issue_number": N field in PROGRESS_METRIC/TOKEN_METRIC JSON logs
    dashboard.addWidgets(
      new cloudwatch.LogQueryWidget({
        title: 'Tool Usage Distribution',
        logGroupNames: [workerLogGroupName, orchestratorLogGroupName],
        queryString: `
          fields @message
          | filter @message like /\\[Tool Call\\]/ and @message like /\\[issue:\${issueNumber}\\]/
          | parse @message "[Tool Call] *" as tool_name
          | stats count() as calls by tool_name
          | sort calls desc
          | limit 15
        `,
        view: cloudwatch.LogQueryVisualizationType.PIE,
        width: 12,
        height: 6,
      }),
      new cloudwatch.LogQueryWidget({
        title: 'Activity Timeline (events/min)',
        logGroupNames: [workerLogGroupName, orchestratorLogGroupName],
        queryString: `
          fields @timestamp
          | filter @message like /\\[issue:\${issueNumber}\\]/ or @message like /"issue_number":\\s*\${issueNumber}[,}]/
          | stats count() as activity by bin(1m)
          | sort @timestamp desc
          | limit 60
        `,
        view: cloudwatch.LogQueryVisualizationType.BAR,
        width: 12,
        height: 6,
      }),
    );

    // Row 5: Live Agent Logs
    dashboard.addWidgets(
      new cloudwatch.LogQueryWidget({
        title: 'Recent Agent Activity',
        logGroupNames: [workerLogGroupName, orchestratorLogGroupName],
        queryString: `
          fields @timestamp, @message
          | filter @message like /\\[issue:\${issueNumber}\\]/ or @message like /"issue_number":\\s*\${issueNumber}[,}]/
          | sort @timestamp desc
          | limit 50
        `,
        width: 24,
        height: 8,
      }),
    );

    // ========================================================================
    // CloudWatch Alarms - Critical failure alerting
    // ========================================================================
    // Note: These alarms use CloudWatch Logs-based metrics.
    // For full alerting, configure SNS topic and subscriptions manually.
    // Example: aws sns subscribe --topic-arn <alarm-topic-arn> --protocol email --notification-endpoint your@email.com

    // Alarm: High error rate in worker logs
    const workerErrorMetric = new cloudwatch.Metric({
      namespace: 'AWS/Logs',
      metricName: 'IncomingLogEvents',
      dimensionsMap: {
        LogGroupName: workerLogGroupName,
      },
      statistic: 'Sum',
      period: cdk.Duration.minutes(5),
    });

    // Create a metric filter for ERROR level logs
    // This creates a custom metric that can be alarmed on
    new logs.MetricFilter(this, 'WorkerErrorFilter', {
      logGroup: logs.LogGroup.fromLogGroupName(this, 'WorkerLogGroupRef', workerLogGroupName),
      metricNamespace: 'ClaudeCodeAgent/Errors',
      metricName: 'WorkerErrors',
      filterPattern: logs.FilterPattern.anyTerm('ERROR', 'error', 'Error', 'FAILED', 'Exception'),
      metricValue: '1',
    });

    new cloudwatch.Alarm(this, 'WorkerErrorAlarm', {
      alarmName: `${projectName}-${environment}-worker-errors`,
      alarmDescription: 'Worker container error rate is elevated',
      metric: new cloudwatch.Metric({
        namespace: 'ClaudeCodeAgent/Errors',
        metricName: 'WorkerErrors',
        statistic: 'Sum',
        period: cdk.Duration.minutes(5),
      }),
      threshold: 10,
      evaluationPeriods: 2,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    // Alarm: Heartbeat missing (orchestrator not publishing metrics)
    new cloudwatch.Alarm(this, 'HeartbeatMissingAlarm', {
      alarmName: `${projectName}-${environment}-heartbeat-missing`,
      alarmDescription: 'Orchestrator heartbeat has not been received - orchestrator may be down',
      metric: new cloudwatch.Metric({
        namespace: 'ClaudeCodeAgent',
        metricName: 'Heartbeat',
        dimensionsMap: { Environment: environment },
        statistic: 'Sum',
        period: cdk.Duration.minutes(10),
      }),
      threshold: 1,
      evaluationPeriods: 2,
      comparisonOperator: cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.BREACHING, // Missing data = orchestrator is down
    });

    // ========================================================================
    // Outputs
    // ========================================================================
    new cdk.CfnOutput(this, 'EcrRepositoryUri', {
      value: this.repository.repositoryUri,
      description: 'ECR repository URI for pushing Docker images',
      exportName: `${projectName}-${environment}-ecr-uri`,
    });

    new cdk.CfnOutput(this, 'EfsFileSystemId', {
      value: this.fileSystem.fileSystemId,
      description: 'EFS file system ID',
      exportName: `${projectName}-${environment}-efs-id`,
    });

    new cdk.CfnOutput(this, 'EfsAccessPointId', {
      value: this.accessPoint.accessPointId,
      description: 'EFS access point ID',
      exportName: `${projectName}-${environment}-efs-ap`,
    });

    new cdk.CfnOutput(this, 'LogGroupName', {
      value: logGroup.logGroupName,
      description: 'CloudWatch log group name',
      exportName: `${projectName}-${environment}-logs`,
    });

    new cdk.CfnOutput(this, 'AnthropicApiKeySecretArn', {
      value: anthropicApiKey.secretArn,
      description: 'Anthropic API key secret ARN (set value manually)',
      exportName: `${projectName}-${environment}-api-key-arn`,
    });

    new cdk.CfnOutput(this, 'GitHubOrchestratorRoleArn', {
      value: githubOrchestratorRole.roleArn,
      description: 'IAM role ARN for GitHub Actions orchestrator invocation',
      exportName: `${projectName}-github-orchestrator-role`,
    });

    new cdk.CfnOutput(this, 'VpcId', {
      value: this.vpc.vpcId,
      description: 'VPC ID',
      exportName: `${projectName}-${environment}-vpc-id`,
    });

    new cdk.CfnOutput(this, 'ScreenshotsBucketName', {
      value: screenshotsBucket.bucketName,
      description: 'S3 bucket for agent screenshots',
      exportName: `${projectName}-${environment}-screenshots-bucket`,
    });

    new cdk.CfnOutput(this, 'ScreenshotsCdnDomain', {
      value: screenshotsDistribution.distributionDomainName,
      description: 'CloudFront domain for screenshot URLs',
      exportName: `${projectName}-${environment}-screenshots-cdn`,
    });

    new cdk.CfnOutput(this, 'PreviewsBucketName', {
      value: previewsBucket.bucketName,
      description: 'S3 bucket for app previews',
      exportName: `${projectName}-${environment}-previews-bucket`,
    });

    new cdk.CfnOutput(this, 'PreviewsCdnDomain', {
      value: previewsDistribution.distributionDomainName,
      description: 'CloudFront domain for preview URLs',
      exportName: `${projectName}-${environment}-previews-cdn`,
    });

    new cdk.CfnOutput(this, 'PreviewsDistributionId', {
      value: previewsDistribution.distributionId,
      description: 'CloudFront distribution ID for cache invalidation',
      exportName: `${projectName}-${environment}-previews-distribution-id`,
    });

    new cdk.CfnOutput(this, 'GitHubPreviewDeployRoleArn', {
      value: githubPreviewDeployRole.roleArn,
      description: 'IAM role ARN for GitHub Actions preview deployment',
      exportName: `${projectName}-github-preview-deploy-role`,
    });

    new cdk.CfnOutput(this, 'DashboardUrl', {
      value: `https://${this.region}.console.aws.amazon.com/cloudwatch/home?region=${this.region}#dashboards:name=${projectName}-${environment}-agent-dashboard`,
      description: 'CloudWatch Dashboard URL for agent monitoring',
      exportName: `${projectName}-${environment}-dashboard-url`,
    });

    // ========================================================================
    // X-Ray Resource Policy - For trace delivery (optional observability)
    // ========================================================================
    // CDK doesn't have native support for X-Ray resource policies, so we use
    // AwsCustomResource to call the X-Ray API directly.
    // This policy allows CloudWatch Logs delivery service to send traces to X-Ray.
    new cr.AwsCustomResource(this, 'XRayResourcePolicy', {
      onCreate: {
        service: 'XRay',
        action: 'putResourcePolicy',
        parameters: {
          PolicyName: 'ClaudeCodeAgentTraceAccess',
          PolicyDocument: JSON.stringify({
            Version: '2012-10-17',
            Statement: [{
              Sid: 'AllowLogDeliveryToSendTraces',
              Effect: 'Allow',
              Principal: {
                Service: 'delivery.logs.amazonaws.com'
              },
              Action: 'xray:PutTraceSegments',
              Resource: '*',
              Condition: {
                StringEquals: {
                  'aws:SourceAccount': this.account
                },
                ArnLike: {
                  'aws:SourceArn': `arn:aws:logs:${this.region}:${this.account}:delivery-source:*`
                }
              }
            }]
          })
        },
        physicalResourceId: cr.PhysicalResourceId.of('XRayResourcePolicy'),
      },
      onUpdate: {
        service: 'XRay',
        action: 'putResourcePolicy',
        parameters: {
          PolicyName: 'ClaudeCodeAgentTraceAccess',
          PolicyDocument: JSON.stringify({
            Version: '2012-10-17',
            Statement: [{
              Sid: 'AllowLogDeliveryToSendTraces',
              Effect: 'Allow',
              Principal: {
                Service: 'delivery.logs.amazonaws.com'
              },
              Action: 'xray:PutTraceSegments',
              Resource: '*',
              Condition: {
                StringEquals: {
                  'aws:SourceAccount': this.account
                },
                ArnLike: {
                  'aws:SourceArn': `arn:aws:logs:${this.region}:${this.account}:delivery-source:*`
                }
              }
            }]
          })
        },
        physicalResourceId: cr.PhysicalResourceId.of('XRayResourcePolicy'),
      },
      onDelete: {
        service: 'XRay',
        action: 'deleteResourcePolicy',
        parameters: {
          PolicyName: 'ClaudeCodeAgentTraceAccess',
        },
      },
      policy: cr.AwsCustomResourcePolicy.fromStatements([
        new iam.PolicyStatement({
          actions: ['xray:PutResourcePolicy', 'xray:DeleteResourcePolicy'],
          resources: ['*'],
        }),
      ]),
    });

  }
}
