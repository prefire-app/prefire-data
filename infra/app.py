#!/usr/bin/env python3
"""CDK app entry point for prefire-data infrastructure."""

import aws_cdk as cdk
from stacks.data_lambda_stack import DataLambdaStack

app = cdk.App()
env_name = app.node.try_get_context("env") or "dev"

DataLambdaStack(
    app,
    f"PrefireData-{env_name}",
    env_name=env_name,
)

app.synth()
