// Copyright 2025-present Anthropic PBC.
// Licensed under Apache 2.0

import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export interface DemoViewerStackProps extends cdk.StackProps {
  projectName: string;
  environment: string;
}

/**
 * Demo Viewer Stack - Read-Only Access for Demos
 *
 * Creates IAM resources for demo viewing without SSO access.
 * This allows laptops/devices without AWS SSO to view:
 * - CloudWatch dashboards
 * - Step Functions executions
 * - ECS task logs
 */
export class DemoViewerStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: DemoViewerStackProps) {
    super(scope, id, props);

    const { projectName, environment } = props;

    // ========================================================================
    // Demo Viewer IAM Role
    // ========================================================================
    const demoViewerRole = new iam.Role(this, 'DemoViewerRole', {
      roleName: `${projectName}-${environment}-demo-viewer`,
      description: 'Read-only role for viewing agent demo dashboards and logs',
      assumedBy: new iam.AccountPrincipal(cdk.Stack.of(this).account),
      maxSessionDuration: cdk.Duration.hours(4),
    });

    // CloudWatch read-only access
    demoViewerRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'cloudwatch:GetDashboard',
        'cloudwatch:GetMetricData',
        'cloudwatch:GetMetricStatistics',
        'cloudwatch:ListDashboards',
        'cloudwatch:ListMetrics',
        'logs:DescribeLogGroups',
        'logs:DescribeLogStreams',
        'logs:GetLogEvents',
        'logs:FilterLogEvents',
        'logs:StartQuery',
        'logs:StopQuery',
        'logs:GetQueryResults',
      ],
      resources: ['*'],
    }));

    // Step Functions read-only access
    demoViewerRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'states:DescribeStateMachine',
        'states:DescribeExecution',
        'states:GetExecutionHistory',
        'states:ListExecutions',
        'states:ListStateMachines',
      ],
      resources: [
        `arn:aws:states:${this.region}:${this.account}:stateMachine:${projectName}-*`,
        `arn:aws:states:${this.region}:${this.account}:execution:${projectName}-*:*`,
      ],
    }));

    // ECS read-only access
    demoViewerRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'ecs:DescribeClusters',
        'ecs:DescribeServices',
        'ecs:DescribeTasks',
        'ecs:DescribeTaskDefinition',
        'ecs:ListClusters',
        'ecs:ListServices',
        'ecs:ListTasks',
        'ecs:ListTaskDefinitions',
      ],
      resources: ['*'],
    }));

    // ========================================================================
    // Outputs
    // ========================================================================
    new cdk.CfnOutput(this, 'DemoViewerRoleArn', {
      value: demoViewerRole.roleArn,
      description: 'Demo viewer IAM role ARN',
      exportName: `${projectName}-${environment}-demo-viewer-role`,
    });
  }
}
