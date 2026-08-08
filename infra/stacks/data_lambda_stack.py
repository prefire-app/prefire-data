"""prefire-data Lambda stack: container-image Lambda + HTTP API + S3 reference."""

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    Stack,
)
from aws_cdk import (
    aws_apigatewayv2 as apigwv2,
)
from aws_cdk import (
    aws_apigatewayv2_integrations as apigwv2_integrations,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as _lambda,
)
from aws_cdk import (
    aws_s3 as s3,
)
from constructs import Construct

DATA_BUCKET_NAME = "prefire-data"
WHP_COG_KEY = "whp/whp2023_cls_conus.tif"


class DataLambdaStack(Stack):
    """Provisions the prefire-data Lambda, HTTP API, and S3 bucket reference."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        bucket = s3.Bucket.from_bucket_name(self, "DataBucket", DATA_BUCKET_NAME)
        repo_root = Path(__file__).resolve().parents[2]

        self.fn = _lambda.DockerImageFunction(
            self,
            "DataFn",
            function_name=f"prefire-data-{env_name}",
            code=_lambda.DockerImageCode.from_image_asset(str(repo_root)),
            architecture=_lambda.Architecture.ARM_64,
            memory_size=1024,
            timeout=Duration.seconds(30),
            environment={
                "WHP_COG_URI": f"s3://{DATA_BUCKET_NAME}/{WHP_COG_KEY}",
                "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
                "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
                "VSI_CACHE": "TRUE",
                "VSI_CACHE_SIZE": "536870912",
            },
        )

        self.fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[bucket.arn_for_objects("*")],
            )
        )

        # Provisioned concurrency keeps one warm execution so /county calls
        # from the API stack don't pay a multi-second cold start.
        data_alias = _lambda.Alias(
            self,
            "DataAlias",
            alias_name="live",
            version=self.fn.current_version,
            provisioned_concurrent_executions=1,
        )

        http_api = apigwv2.HttpApi(
            self,
            "DataHttpApi",
            api_name=f"prefire-data-{env_name}",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[apigwv2.CorsHttpMethod.GET, apigwv2.CorsHttpMethod.OPTIONS],
                allow_headers=["*"],
            ),
        )
        http_api.add_routes(
            path="/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=apigwv2_integrations.HttpLambdaIntegration("DataFnIntegration", data_alias),
        )

        cdk.CfnOutput(self, "DataApiEndpoint", value=http_api.api_endpoint)
        cdk.CfnOutput(self, "DataFunctionArn", value=self.fn.function_arn)
