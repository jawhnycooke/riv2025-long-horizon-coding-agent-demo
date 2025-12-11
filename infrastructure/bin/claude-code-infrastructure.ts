#!/usr/bin/env node
// Copyright 2025-present Anthropic PBC.
// Licensed under Apache 2.0

import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { ClaudeCodeStack } from '../lib/claude-code-stack';
import { DemoViewerStack } from '../lib/demo-viewer-stack';
import { EcsClusterStack } from '../lib/ecs-cluster-stack';
import { StepFunctionsStack } from '../lib/step-functions-stack';

const app = new cdk.App();

// Get configuration from context or environment
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT || process.env.AWS_ACCOUNT_ID,
  region: process.env.CDK_DEFAULT_REGION || process.env.AWS_REGION || 'us-west-2',
};

const projectName = app.node.tryGetContext('projectName') || 'claude-code';
const environment = app.node.tryGetContext('environment') || 'reinvent';
const logRetentionDays = parseInt(app.node.tryGetContext('logRetentionDays') || '7');

// ============================================================================
// Core Infrastructure Stack (VPC, ECR, EFS, Secrets, S3, CloudFront)
// ============================================================================
const coreStack = new ClaudeCodeStack(app, `${projectName}-${environment}`, {
  env,
  description: 'Claude Code Agent - Core infrastructure (VPC, ECR, EFS, Secrets)',
  projectName,
  environment,
  logRetentionDays,
  tags: {
    Project: projectName,
    Environment: environment,
    ManagedBy: 'CDK',
  },
});

// ============================================================================
// ECS Cluster Stack (Orchestrator + Worker Task Definitions)
// ============================================================================
const ecsStack = new EcsClusterStack(app, `${projectName}-${environment}-ecs`, {
  env,
  description: 'Claude Code Agent - ECS cluster and task definitions',
  projectName,
  environment,
  vpc: coreStack.vpc,
  fileSystem: coreStack.fileSystem,
  accessPoint: coreStack.accessPoint,
  repository: coreStack.repository,
  logRetentionDays,
  tags: {
    Project: projectName,
    Environment: environment,
    ManagedBy: 'CDK',
  },
});

// ECS stack depends on core infrastructure
ecsStack.addDependency(coreStack);

// ============================================================================
// Step Functions Stack (Worker Invocation State Machine)
// ============================================================================
const sfnStack = new StepFunctionsStack(app, `${projectName}-${environment}-sfn`, {
  env,
  description: 'Claude Code Agent - Step Functions for worker invocation',
  projectName,
  environment,
  cluster: ecsStack.cluster,
  workerTaskDef: ecsStack.workerTaskDef,
  workerContainer: ecsStack.workerContainer,
  workerSecurityGroup: ecsStack.workerSecurityGroup,
  vpc: coreStack.vpc,
  logRetentionDays,
  tags: {
    Project: projectName,
    Environment: environment,
    ManagedBy: 'CDK',
  },
});

// Step Functions stack depends on ECS stack
sfnStack.addDependency(ecsStack);

// ============================================================================
// Demo Viewer Stack (Read-Only Access for Demos)
// ============================================================================
new DemoViewerStack(app, `${projectName}-demo-viewer`, {
  env,
  description: 'Read-only demo viewer access for Claude Code Agent',
  projectName,
  environment,
  tags: {
    Project: projectName,
    Environment: environment,
    ManagedBy: 'CDK',
  },
});
