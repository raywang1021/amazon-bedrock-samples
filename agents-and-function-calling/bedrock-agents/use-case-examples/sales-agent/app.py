from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    CfnOutput,
    aws_opensearchserverless as aws_opss,
    aws_personalize as personalize
)
import aws_cdk as cdk
import json
from constructs import Construct
from cdklabs.generative_ai_cdk_constructs import (
    bedrock
)

class SalesAgentStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 Bucket for related data
        _data_bucket = s3.Bucket(
            self, "data-bucket",
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            encryption=s3.BucketEncryption.S3_MANAGED
        )

        # Create DynamoDB table for item data
        _item_table = dynamodb.Table(
            self, "item-table",
            partition_key=dynamodb.Attribute(
                name="ITEM_ID",
                type=dynamodb.AttributeType.STRING
            ),
            import_source=dynamodb.ImportSourceSpecification(
                input_format=dynamodb.InputFormat.csv(),
                bucket=_data_bucket,
                key_prefix="DynamoDB/items.csv"
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Create DynamoDB table for user data
        _user_table = dynamodb.Table(
            self, "user-table",
            partition_key=dynamodb.Attribute(
                name="USER_ID",
                type=dynamodb.AttributeType.NUMBER
            ),
            import_source=dynamodb.ImportSourceSpecification(
                input_format=dynamodb.InputFormat.csv(),
                bucket=_data_bucket,
                key_prefix="DynamoDB/users.csv"
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Create OpenSearch Serverless collection
        collection_name = "sales_agent_collection"



        # Create OpenSearch Collection
        cfn_collection = aws_opss.CfnCollection(self, "OpssSearchCollection",
            name=collection_name,
            description="Collection for OpenSearch Serverless",
            type="SEARCH"
        )


        # Create Personalize
        personalize_dataset_group = personalize.CfnDatasetGroup(
            self,
            'PersonalizeDatasetGroup',
            domain='ECOMMERCE',
            name='retail-dataset',
        )

        personalize_schema_interaction = personalize.CfnSchema(
            self,
            'PersonalizeSchemaInteraction',
            domain='ECOMMERCE',
            schema='{\n  "type": "record",\n  "name": "Interactions",\n  "namespace": "com.amazonaws.personalize.schema",\n  "fields": [\n    {\n      "name": "USER_ID",\n      "type": "string"\n    },\n    {\n      "name": "ITEM_ID",\n      "type": "string"\n    },\n    {\n      "name": "TIMESTAMP",\n      "type": "long"\n    },\n    {\n      "name": "EVENT_TYPE",\n      "type": "string"\n    },\n    {\n        "name":"DISCOUNT",\n        "type": "string"\n    }\n  ],\n  "version": "1.0"\n}',
            name='interaction',
        )

        personalize_schema_item = personalize.CfnSchema(
            self,
            'PersonalizeSchemaItem',
            domain='ECOMMERCE',
            schema='{\n  "type": "record",\n  "name": "Items",\n  "namespace": "com.amazonaws.personalize.schema",\n  "fields": [\n    {\n      "name": "ITEM_ID",\n      "type": "string"\n    },\n    {\n      "name": "PRICE",\n      "type": "float"\n    },\n    {\n      "name": "CATEGORY_L1",\n      "type": "string",\n      "categorical": true\n    },\n    {\n      "name": "CATEGORY_L2",\n      "type": "string",\n      "categorical": true\n    },\n    {\n      "name": "GENDER",\n      "type": "string",\n      "categorical": true\n    }\n  ],\n  "version": "1.0"\n}',
            name='item',
        )

        personalize_schema_user = personalize.CfnSchema(
            self,
            'PersonalizeSchemaUser',
            domain='ECOMMERCE',
            schema='{\n  "type": "record",\n  "name": "Users",\n  "namespace": "com.amazonaws.personalize.schema",\n  "fields": [\n    {\n      "name": "USER_ID",\n      "type": "string"\n    },\n    {\n        "name": "GENDER",\n        "type": "string"\n    },\n    {\n        "name": "AGE",\n        "type": "int"\n    }\n  ],\n  "version": "1.0"\n}',
            name='user',
        )

        # Personalize L1
        personalize_dataset_interactions = personalize.CfnDataset(
            self,
            'PersonalizeDatasetInteractions',
            dataset_type='Interactions',
            dataset_group_arn=personalize_dataset_group.attr_dataset_group_arn,
            schema_arn=personalize_schema_interaction.attr_schema_arn,
            name='interaction',
        )

        personalize_dataset_items = personalize.CfnDataset(
            self,
            'PersonalizeDatasetItems',
            dataset_type='Items',
            dataset_group_arn=personalize_dataset_group.attr_dataset_group_arn,
            schema_arn=personalize_schema_item.attr_schema_arn,
            name='item',
        )

        personalize_dataset_users = personalize.CfnDataset(
            self,
            'PersonalizeDatasetUsers',
            dataset_type='Users',
            dataset_group_arn=personalize_dataset_group.attr_dataset_group_arn,
            schema_arn=personalize_schema_user.attr_schema_arn,
            name='user',
        )


        # Create the IAM role for the Lambda function
        bedrock_agent_lambda_role = iam.Role(self, "bedrock_agent_lambda_role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role with full access to S3, DynamoDB and OpenSearch"
        )
        bedrock_agent_lambda_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess"))
        bedrock_agent_lambda_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonDynamoDBFullAccess"))
        bedrock_agent_lambda_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonOpenSearchServiceFullAccess"))
        bedrock_agent_lambda_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"))
        bedrock_agent_lambda_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonPersonalizeFullAccess"))

        lambda_layer = lambda_.LayerVersion(self, 'LineGptLayer',
            code=lambda_.Code.from_asset('lambda/layer/opensearch-layer.zip'),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_9],
            description="Bedrock Agent Layer"
        )

        # Lambda function for Agent Group
        agent_function = lambda_.Function(self, "sales-agent-function",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda/function/"),
            layers=[lambda_layer],
            timeout=Duration.seconds(600),
            role=bedrock_agent_lambda_role,
            environment={
                "aos_endpoint": cfn_collection.attr_collection_endpoint
            }
        )

        # Define the Bedrock Agent action group
        _action_group = bedrock.AgentActionGroup(self,
                    "sales-agent-action-group",
                    action_group_name="sales-agent-action-group",
                    action_group_executor=bedrock.ActionGroupExecutor(
                        lambda_=agent_function
                    ),
                    action_group_state="ENABLED",
                    api_schema=bedrock.ApiSchema.from_asset("data/agent-schema/openapi.json")
        )

        # Create Bedrock Agent
        agent = bedrock.Agent(
            self,
            "Agent",
            foundation_model=bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V1_0,
            instruction="""You are a professional sales expert which can help customer on:
            1. Allows searching for products based on a specified condition, which defines customer requirements for the product.
            2. Compares products based on user input, which includes user ID, product search condition, and user preferences.""",
        )