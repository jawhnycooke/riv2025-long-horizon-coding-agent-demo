// Copyright 2025-present Anthropic PBC.
// Licensed under Apache 2.0

import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as efs from 'aws-cdk-lib/aws-efs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

export interface EcsClusterStackProps extends cdk.StackProps {
  projectName: string;
  environment: string;
  vpc: ec2.IVpc;
  fileSystem: efs.IFileSystem;
  accessPoint: efs.IAccessPoint;
  repository: ecr.IRepository;
  logRetentionDays: number;
}

/**
 * ECS Cluster Stack for Two-Container Architecture
 *
 * Creates:
 * - ECS Fargate cluster
 * - Orchestrator task definition (long-running service, 2GB/1vCPU)
 * - Worker task definition (on-demand tasks, 8GB/4vCPU)
 * - Security groups for both containers
 * - IAM execution and task roles
 */
export class EcsClusterStack extends cdk.Stack {
  public readonly cluster: ecs.Cluster;
  public readonly orchestratorTaskDef: ecs.FargateTaskDefinition;
  public readonly workerTaskDef: ecs.FargateTaskDefinition;
  public readonly orchestratorContainer: ecs.ContainerDefinition;
  public readonly workerContainer: ecs.ContainerDefinition;
  public readonly orchestratorSecurityGroup: ec2.SecurityGroup;
  public readonly workerSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: EcsClusterStackProps) {
    super(scope, id, props);

    const {
      projectName,
      environment,
      vpc,
      fileSystem,
      accessPoint,
      repository,
      logRetentionDays,
    } = props;

    // ========================================================================
    // ECS Cluster
    // ========================================================================
    this.cluster = new ecs.Cluster(this, 'AgentCluster', {
      clusterName: `${projectName}-${environment}`,
      vpc,
      containerInsights: true,
    });

    // ========================================================================
    // Security Groups
    // ========================================================================
    this.orchestratorSecurityGroup = new ec2.SecurityGroup(this, 'OrchestratorSG', {
      vpc,
      description: 'Security group for orchestrator container',
      allowAllOutbound: true,
    });

    this.workerSecurityGroup = new ec2.SecurityGroup(this, 'WorkerSG', {
      vpc,
      description: 'Security group for worker container',
      allowAllOutbound: true,
    });

    // Allow EFS access from both security groups
    fileSystem.connections.allowDefaultPortFrom(this.orchestratorSecurityGroup);
    fileSystem.connections.allowDefaultPortFrom(this.workerSecurityGroup);

    // ========================================================================
    // CloudWatch Log Groups
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

    const orchestratorLogGroup = new logs.LogGroup(this, 'OrchestratorLogs', {
      logGroupName: `/ecs/${projectName}-${environment}/orchestrator`,
      retention: logRetention,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const workerLogGroup = new logs.LogGroup(this, 'WorkerLogs', {
      logGroupName: `/ecs/${projectName}-${environment}/worker`,
      retention: logRetention,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ========================================================================
    // IAM Roles - Shared Execution Role
    // ========================================================================
    const executionRole = new iam.Role(this, 'TaskExecutionRole', {
      roleName: `${projectName}-${environment}-task-execution`,
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'),
      ],
    });

    // Grant ECR pull permissions
    repository.grantPull(executionRole);

    // Grant secrets read permissions
    executionRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'secretsmanager:GetSecretValue',
      ],
      resources: [
        `arn:aws:secretsmanager:${this.region}:${this.account}:secret:${projectName}/*`,
      ],
    }));

    // ========================================================================
    // Orchestrator Task Definition
    // ========================================================================
    const orchestratorTaskRole = new iam.Role(this, 'OrchestratorTaskRole', {
      roleName: `${projectName}-${environment}-orchestrator-task`,
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
    });

    // Orchestrator needs: Secrets Manager, Step Functions, CloudWatch metrics
    orchestratorTaskRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['secretsmanager:GetSecretValue'],
      resources: [
        `arn:aws:secretsmanager:${this.region}:${this.account}:secret:${projectName}/*`,
      ],
    }));

    orchestratorTaskRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'states:StartExecution',
        'states:DescribeExecution',
        'states:StopExecution',
      ],
      resources: [
        `arn:aws:states:${this.region}:${this.account}:stateMachine:${projectName}-${environment}-worker`,
        `arn:aws:states:${this.region}:${this.account}:execution:${projectName}-${environment}-worker:*`,
      ],
    }));

    orchestratorTaskRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['cloudwatch:PutMetricData'],
      resources: ['*'],
      conditions: {
        StringEquals: {
          'cloudwatch:namespace': 'ClaudeCodeAgent',
        },
      },
    }));

    this.orchestratorTaskDef = new ecs.FargateTaskDefinition(this, 'OrchestratorTaskDef', {
      family: `${projectName}-${environment}-orchestrator`,
      memoryLimitMiB: 2048,
      cpu: 1024,
      executionRole,
      taskRole: orchestratorTaskRole,
    });

    this.orchestratorContainer = this.orchestratorTaskDef.addContainer('orchestrator', {
      containerName: 'orchestrator',
      image: ecs.ContainerImage.fromEcrRepository(repository, 'orchestrator-latest'),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'orchestrator',
        logGroup: orchestratorLogGroup,
      }),
      environment: {
        ENVIRONMENT: environment,
        AWS_REGION: this.region,
        POLL_INTERVAL_SECONDS: '300',
        // Orchestrator-specific environment variables
        // STATE_MACHINE_ARN is set dynamically after Step Functions stack deploys
        // These are placeholders - actual values configured via GitHub Actions or task overrides
        GITHUB_REPOSITORY: '', // Set via task override or GitHub Actions
        AUTHORIZED_APPROVERS: '', // Set via task override or GitHub Actions
      },
      secrets: {
        ANTHROPIC_API_KEY: ecs.Secret.fromSecretsManager(
          secretsmanager.Secret.fromSecretNameV2(this, 'OrchestratorAnthropicKey', `${projectName}/${environment}/anthropic-api-key`)
        ),
        GITHUB_TOKEN: ecs.Secret.fromSecretsManager(
          secretsmanager.Secret.fromSecretNameV2(this, 'OrchestratorGitHubToken', `${projectName}/${environment}/github-token`)
        ),
      },
      healthCheck: {
        command: ['CMD-SHELL', 'python -c "print(1)" || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
    });

    // ========================================================================
    // Worker Task Definition
    // ========================================================================
    const workerTaskRole = new iam.Role(this, 'WorkerTaskRole', {
      roleName: `${projectName}-${environment}-worker-task`,
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
    });

    // Worker needs: Secrets Manager, S3 (screenshots + previews), CloudWatch metrics
    workerTaskRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['secretsmanager:GetSecretValue'],
      resources: [
        `arn:aws:secretsmanager:${this.region}:${this.account}:secret:${projectName}/*`,
      ],
    }));

    workerTaskRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        's3:PutObject',
        's3:GetObject',
        's3:ListBucket',
      ],
      resources: [
        // Screenshots bucket
        `arn:aws:s3:::${projectName}-${environment}-screenshots`,
        `arn:aws:s3:::${projectName}-${environment}-screenshots/*`,
        // Previews bucket (app preview deployments)
        `arn:aws:s3:::${projectName}-${environment}-previews`,
        `arn:aws:s3:::${projectName}-${environment}-previews/*`,
      ],
    }));

    workerTaskRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['cloudwatch:PutMetricData'],
      resources: ['*'],
      conditions: {
        StringEquals: {
          'cloudwatch:namespace': 'ClaudeCodeAgent',
        },
      },
    }));

    this.workerTaskDef = new ecs.FargateTaskDefinition(this, 'WorkerTaskDef', {
      family: `${projectName}-${environment}-worker`,
      memoryLimitMiB: 8192,
      cpu: 4096,
      executionRole,
      taskRole: workerTaskRole,
    });

    // Add EFS volume to worker task
    this.workerTaskDef.addVolume({
      name: 'efs-projects',
      efsVolumeConfiguration: {
        fileSystemId: fileSystem.fileSystemId,
        transitEncryption: 'ENABLED',
        authorizationConfig: {
          accessPointId: accessPoint.accessPointId,
          iam: 'ENABLED',
        },
      },
    });

    // Worker environment variables:
    // - ENVIRONMENT, AWS_REGION, WORKER_MODE: Set here in base config
    // - ISSUE_NUMBER, GITHUB_REPOSITORY, PROVIDER: Injected via Step Functions containerOverrides
    //   (see step-functions-stack.ts lines 95-117)
    // This split allows the state machine to dynamically configure each worker invocation.
    this.workerContainer = this.workerTaskDef.addContainer('worker', {
      containerName: 'worker',
      image: ecs.ContainerImage.fromEcrRepository(repository, 'worker-latest'),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'worker',
        logGroup: workerLogGroup,
      }),
      environment: {
        ENVIRONMENT: environment,
        AWS_REGION: this.region,
        WORKER_MODE: 'true',
        // Additional env vars (ISSUE_NUMBER, GITHUB_REPOSITORY, PROVIDER)
        // are injected by Step Functions via containerOverrides
      },
      secrets: {
        ANTHROPIC_API_KEY: ecs.Secret.fromSecretsManager(
          secretsmanager.Secret.fromSecretNameV2(this, 'WorkerAnthropicKey', `${projectName}/${environment}/anthropic-api-key`)
        ),
        GITHUB_TOKEN: ecs.Secret.fromSecretsManager(
          secretsmanager.Secret.fromSecretNameV2(this, 'WorkerGitHubToken', `${projectName}/${environment}/github-token`)
        ),
      },
    });

    // Mount EFS volume
    this.workerContainer.addMountPoints({
      sourceVolume: 'efs-projects',
      containerPath: '/projects',
      readOnly: false,
    });

    // ========================================================================
    // Outputs
    // ========================================================================
    new cdk.CfnOutput(this, 'ClusterArn', {
      value: this.cluster.clusterArn,
      description: 'ECS Cluster ARN',
      exportName: `${projectName}-${environment}-cluster-arn`,
    });

    new cdk.CfnOutput(this, 'OrchestratorTaskDefArn', {
      value: this.orchestratorTaskDef.taskDefinitionArn,
      description: 'Orchestrator task definition ARN',
      exportName: `${projectName}-${environment}-orchestrator-taskdef`,
    });

    new cdk.CfnOutput(this, 'WorkerTaskDefArn', {
      value: this.workerTaskDef.taskDefinitionArn,
      description: 'Worker task definition ARN',
      exportName: `${projectName}-${environment}-worker-taskdef`,
    });

    new cdk.CfnOutput(this, 'OrchestratorLogGroupName', {
      value: orchestratorLogGroup.logGroupName,
      description: 'Orchestrator CloudWatch log group',
      exportName: `${projectName}-${environment}-orchestrator-logs`,
    });

    new cdk.CfnOutput(this, 'WorkerLogGroupName', {
      value: workerLogGroup.logGroupName,
      description: 'Worker CloudWatch log group',
      exportName: `${projectName}-${environment}-worker-logs`,
    });

    new cdk.CfnOutput(this, 'OrchestratorSecurityGroupId', {
      value: this.orchestratorSecurityGroup.securityGroupId,
      description: 'Orchestrator security group ID',
      exportName: `${projectName}-${environment}-orchestrator-sg`,
    });

    new cdk.CfnOutput(this, 'WorkerSecurityGroupId', {
      value: this.workerSecurityGroup.securityGroupId,
      description: 'Worker security group ID',
      exportName: `${projectName}-${environment}-worker-sg`,
    });
  }
}
