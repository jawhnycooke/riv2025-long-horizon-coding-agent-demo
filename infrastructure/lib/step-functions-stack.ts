// Copyright 2025-present Anthropic PBC.
// Licensed under Apache 2.0

import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Construct } from 'constructs';

export interface StepFunctionsStackProps extends cdk.StackProps {
  projectName: string;
  environment: string;
  cluster: ecs.ICluster;
  workerTaskDef: ecs.FargateTaskDefinition;
  workerContainer: ecs.ContainerDefinition;
  workerSecurityGroup: ec2.ISecurityGroup;
  vpc: ec2.IVpc;
  logRetentionDays: number;
}

/**
 * Step Functions Stack for Worker Invocation
 *
 * Creates a state machine that:
 * 1. Receives issue_number from orchestrator
 * 2. Runs worker container via ECS RunTask
 * 3. Waits for completion (RUN_JOB pattern)
 * 4. Returns success/failure status
 *
 * Error handling:
 * - Automatic retries for transient failures
 * - Catch blocks for permanent failures
 * - 24-hour timeout for long-running builds
 */
export class StepFunctionsStack extends cdk.Stack {
  public readonly stateMachine: sfn.StateMachine;

  constructor(scope: Construct, id: string, props: StepFunctionsStackProps) {
    super(scope, id, props);

    const {
      projectName,
      environment,
      cluster,
      workerTaskDef,
      workerContainer,
      workerSecurityGroup,
      vpc,
      logRetentionDays,
    } = props;

    // ========================================================================
    // CloudWatch Log Group for Step Functions
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

    const sfnLogGroup = new logs.LogGroup(this, 'StateMachineLogs', {
      logGroupName: `/aws/stepfunctions/${projectName}-${environment}-worker`,
      retention: logRetention,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ========================================================================
    // State Machine Definition
    // ========================================================================

    // Step 1: Prepare - Extract input parameters
    const prepareState = new sfn.Pass(this, 'Prepare', {
      comment: 'Extract input parameters for worker',
      parameters: {
        'issue_number.$': '$.issue_number',
        'github_repo.$': '$.github_repo',
        'provider.$': '$.provider',
        'environment.$': '$.environment',
        'started_at.$': '$$.State.EnteredTime',
      },
      resultPath: '$.prepared',
    });

    // Step 2: Run Worker - ECS RunTask with container overrides
    const runWorkerTask = new tasks.EcsRunTask(this, 'RunWorker', {
      comment: 'Run worker container to build the GitHub issue',
      integrationPattern: sfn.IntegrationPattern.RUN_JOB, // Wait for completion
      cluster,
      taskDefinition: workerTaskDef,
      launchTarget: new tasks.EcsFargateLaunchTarget({
        platformVersion: ecs.FargatePlatformVersion.LATEST,
      }),
      securityGroups: [workerSecurityGroup],
      assignPublicIp: true,
      subnets: { subnetType: ec2.SubnetType.PUBLIC },
      containerOverrides: [
        {
          containerDefinition: workerContainer,
          environment: [
            {
              name: 'ISSUE_NUMBER',
              value: sfn.JsonPath.stringAt('$.issue_number'),
            },
            {
              name: 'GITHUB_REPOSITORY',
              value: sfn.JsonPath.stringAt('$.github_repo'),
            },
            {
              name: 'PROVIDER',
              value: sfn.JsonPath.stringAt('$.provider'),
            },
            {
              name: 'ENVIRONMENT',
              value: sfn.JsonPath.stringAt('$.environment'),
            },
          ],
        },
      ],
      resultPath: '$.ecs_result',
    });

    // Configure retries for transient failures
    runWorkerTask.addRetry({
      errors: ['States.TaskFailed'],
      interval: cdk.Duration.seconds(30),
      maxAttempts: 2,
      backoffRate: 2,
    });

    // Step 3: Success - Format successful result
    const successState = new sfn.Pass(this, 'Success', {
      comment: 'Worker completed successfully',
      parameters: {
        'status': 'SUCCEEDED',
        'issue_number.$': '$.prepared.issue_number',
        'github_repo.$': '$.prepared.github_repo',
        'started_at.$': '$.prepared.started_at',
        'completed_at.$': '$$.State.EnteredTime',
      },
    });

    // Step 4: Handle Error - Format error result
    const handleErrorState = new sfn.Pass(this, 'HandleError', {
      comment: 'Worker failed - capture error details',
      parameters: {
        'status': 'FAILED',
        'issue_number.$': '$.prepared.issue_number',
        'github_repo.$': '$.prepared.github_repo',
        'started_at.$': '$.prepared.started_at',
        'failed_at.$': '$$.State.EnteredTime',
        'error.$': '$.error.Error',
        'cause.$': '$.error.Cause',
      },
    });

    // Add catch for permanent failures
    runWorkerTask.addCatch(handleErrorState, {
      errors: ['States.ALL'],
      resultPath: '$.error',
    });

    // Chain the states
    const definition = prepareState
      .next(runWorkerTask)
      .next(successState);

    // ========================================================================
    // State Machine
    // ========================================================================
    this.stateMachine = new sfn.StateMachine(this, 'WorkerStateMachine', {
      stateMachineName: `${projectName}-${environment}-worker`,
      definition,
      timeout: cdk.Duration.hours(24), // Long-running builds
      tracingEnabled: true,
      logs: {
        destination: sfnLogGroup,
        level: sfn.LogLevel.ALL,
        includeExecutionData: true,
      },
    });

    // ========================================================================
    // IAM Permissions for State Machine
    // ========================================================================
    // Grant ECS RunTask permissions
    this.stateMachine.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'ecs:RunTask',
        'ecs:StopTask',
        'ecs:DescribeTasks',
      ],
      resources: [
        workerTaskDef.taskDefinitionArn,
        `arn:aws:ecs:${this.region}:${this.account}:task/${cluster.clusterName}/*`,
      ],
    }));

    // Grant IAM PassRole for task execution role
    this.stateMachine.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['iam:PassRole'],
      resources: [
        workerTaskDef.executionRole!.roleArn,
        workerTaskDef.taskRole.roleArn,
      ],
    }));

    // Grant CloudWatch Events permissions for task state changes
    // Step Functions uses a managed rule to track ECS task completion.
    // The rule name pattern is: StepFunctionsGetEventsForECSTaskRule
    // We grant wildcard to handle any variation CDK might create.
    this.stateMachine.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'events:PutTargets',
        'events:PutRule',
        'events:DescribeRule',
      ],
      resources: [
        `arn:aws:events:${this.region}:${this.account}:rule/StepFunctions*`,
      ],
    }));

    // ========================================================================
    // Outputs
    // ========================================================================
    new cdk.CfnOutput(this, 'StateMachineArn', {
      value: this.stateMachine.stateMachineArn,
      description: 'Worker state machine ARN (for orchestrator)',
      exportName: `${projectName}-${environment}-worker-sfn-arn`,
    });

    new cdk.CfnOutput(this, 'StateMachineName', {
      value: this.stateMachine.stateMachineName!,
      description: 'Worker state machine name',
      exportName: `${projectName}-${environment}-worker-sfn-name`,
    });

    new cdk.CfnOutput(this, 'StateMachineConsoleUrl', {
      value: `https://${this.region}.console.aws.amazon.com/states/home?region=${this.region}#/statemachines/view/${encodeURIComponent(this.stateMachine.stateMachineArn)}`,
      description: 'Step Functions console URL',
      exportName: `${projectName}-${environment}-worker-sfn-console`,
    });
  }
}
