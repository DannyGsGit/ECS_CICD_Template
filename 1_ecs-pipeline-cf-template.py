"""Generating CloudFormation template."""


"""This template deploys ALBs, Target Groups and Route53 configuration in a
CodePipeline. The template picks up the list of services from a YAML stored in
a target CodeCommit repo."""

from awacs.aws import (
    Allow,
    Policy,
    Principal,
    Statement
)

from troposphere.ecr import Repository

from awacs.sts import AssumeRole

from troposphere import (
    Join,
    Ref,
    Sub,
    Template,
    Parameter,
    Select,
    Split,
    GetAtt,
    Output,
    Export
)

from troposphere.codebuild import (
    Artifacts,
    Environment,
    Project,
    Source
)

from troposphere.codepipeline import (
    Actions,
    ActionTypeID,
    ArtifactStore,
    InputArtifacts,
    OutputArtifacts,
    Pipeline,
    Stages
)

from troposphere.iam import Policy as IAMPolicy

from troposphere.s3 import Bucket, VersioningConfiguration

from troposphere.autoscaling import (
    AutoScalingGroup,
    LaunchConfiguration,
    ScalingPolicy
)

from troposphere.cloudwatch import (
    Alarm,
    MetricDimension
)

from troposphere.ecs import Cluster

from troposphere.iam import (
    InstanceProfile,
    Role
)







t = Template()

t.add_description("ALB and Route53 Pipeline")


##############
# Parameters #
##############

t.add_parameter(Parameter(
    "RepoName",
    Type="String",
    Description="CodeCommit Repo containing ECS template"
))

t.add_parameter(Parameter(
    "StageVpcId",
    Type="AWS::EC2::VPC::Id",
    Description="Staging VPC (format: vpc-263e8d41)"
))

t.add_parameter(Parameter(
    "StagePublicSubnet",
    Description="Staging PublicSubnet (format: subnet-2480c343,subnet-7a8a1621)",
    Type="List<AWS::EC2::Subnet::Id>"
))

t.add_parameter(Parameter(
    "ProdVpcId",
    Type="AWS::EC2::VPC::Id",
    Description="Prod VPC"
))

t.add_parameter(Parameter(
    "ProdPublicSubnet",
    Description="Prod PublicSubnet",
    Type="List<AWS::EC2::Subnet::Id>"
))

t.add_parameter(Parameter(
    "KeyPair",
    Description="Name of an existing EC2 KeyPair to SSH",
    Type="AWS::EC2::KeyPair::KeyName",
    ConstraintDescription="must be the name of an existing EC2 KeyPair.",
))

#############
# Resources #
#############




#### CodeBuild ####

t.add_resource(Role(
    "ServiceRole",
    AssumeRolePolicyDocument=Policy(
        Statement=[
            Statement(
                Effect=Allow,
                Action=[AssumeRole],
                Principal=Principal("Service", ["codebuild.amazonaws.com"])
            )
        ]
    ),
    Path="/",
    ManagedPolicyArns=[
        'arn:aws:iam::aws:policy/AWSCodePipelineReadOnlyAccess',
        'arn:aws:iam::aws:policy/AWSCodeBuildDeveloperAccess',
        'arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser',
        'arn:aws:iam::aws:policy/AmazonS3FullAccess',
        'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess'
    ]
))

environment = Environment(
    ComputeType='BUILD_GENERAL1_SMALL',
    Image='aws/codebuild/python:3.5.2',
    Type='LINUX_CONTAINER',
    EnvironmentVariables=[
        {'Name': 'StageVpcId', 'Value': Ref("StageVpcId")},
        {'Name': 'StagePublicSubnet', 'Value': Join(',', Ref("StagePublicSubnet"))},
        {'Name': 'ProdVpcId', 'Value': Ref("ProdVpcId")},
        {'Name': 'ProdPublicSubnet', 'Value': Join(',', Ref("StagePublicSubnet"))},
        {'Name': 'KeyPair', 'Value': Ref("KeyPair")}
    ],
)





buildspec = """version: 0.1
phases:
  pre_build:
    commands:
      - pip install troposphere
      - pip install pyyaml
  build:
    commands:
      - echo "Starting python execution"
      - python ecs-cluster-cf-template.py > /tmp/ecs-cluster-cf.template
      - printf '{"StageVpcId":"%s"}' "$StageVpcId" > /tmp/StageVpcId.json
      - printf '{"StagePublicSubnet":"%s"}' "$StagePublicSubnet" > /tmp/StagePublicSubnet.json
      - printf '{"ProdVpcId":"%s"}' "$ProdVpcId" > /tmp/ProdVpcId.json
      - printf '{"ProdPublicSubnet":"%s"}' "$ProdPublicSubnet" > /tmp/ProdPublicSubnet.json
      - printf '{"KeyPair":"%s"}' "$KeyPair" > /tmp/KeyPair.json
  post_build:
    commands:
      - echo "Completed CFN template creation."
      - echo "$(cat /tmp/StagePublicSubnet.json)"
artifacts:
  files: /tmp/*
  discard-paths: yes
"""


t.add_resource(Project(
    "CodeBuild",
    Name=Join(
            "-",
            [Select(0, Split("-", Ref("AWS::StackName"))),
                "codebuild"]
        ),
    Environment=environment,
    ServiceRole=Ref("ServiceRole"),
    Source=Source(
        Type="CODEPIPELINE",
        BuildSpec=buildspec
    ),
    Artifacts=Artifacts(
        Type="CODEPIPELINE",
        Name="output"
    ),
))






#### CodePipeline ####
t.add_resource(Bucket(
    "S3Bucket",
    VersioningConfiguration=VersioningConfiguration(
        Status="Enabled",
    )
))

t.add_resource(Role(
    "PipelineRole",
    AssumeRolePolicyDocument=Policy(
        Statement=[
            Statement(
                Effect=Allow,
                Action=[AssumeRole],
                Principal=Principal("Service", ["codepipeline.amazonaws.com"])
            )
        ]
    ),
    Path="/",
    Policies=[
        IAMPolicy(
            PolicyName="ClusterCodePipeline",
            PolicyDocument={
                "Statement": [
                    {"Effect": "Allow", "Action": "cloudformation:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "codebuild:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "codepipeline:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "ecr:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "ecs:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "iam:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "s3:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "codecommit:*", "Resource": "*"},
                ],
            }
        ),
    ]
))

t.add_resource(Role(
    "CloudFormationClusterRole",
    RoleName=Join(
            "-",
            [Select(0, Split("-", Ref("AWS::StackName"))),
                "CloudFormationClusterRole"]
        ),
    Path="/",
    AssumeRolePolicyDocument=Policy(
        Statement=[
            Statement(
                Effect=Allow,
                Action=[AssumeRole],
                Principal=Principal(
                    "Service", ["cloudformation.amazonaws.com"])
            ),
        ]
    ),
    Policies=[
        IAMPolicy(
            PolicyName="CloudFormationClusterPolicy",
            PolicyDocument={
                "Statement": [
                    {"Effect": "Allow", "Action": "cloudformation:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "ecr:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "ecs:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "iam:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "ec2:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "autoscaling:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "elasticloadbalancing:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "route53:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "codecommit:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "cloudwatch:*", "Resource": "*"},
                ],
            }
        ),
    ]
))

t.add_resource(Pipeline(
    "ClusterPipeline",
    RoleArn=GetAtt("PipelineRole", "Arn"),
    ArtifactStore=ArtifactStore(
        Type="S3",
        Location=Ref("S3Bucket")
    ),
    Stages=[
        Stages(
            Name="Source",
            Actions=[
                Actions(
                    Name="Source",
                    ActionTypeId=ActionTypeID(
                        Category="Source",
                        Owner="AWS",
                        Version="1",
                        Provider="CodeCommit"
                    ),
                    Configuration={
                        "BranchName": "master",
                        "RepositoryName": Ref("RepoName")
                    },
                    OutputArtifacts=[
                        OutputArtifacts(
                            Name="App"
                        )
                    ],
                )
            ]
        ),
        Stages(
            Name="Build",
            Actions=[
                Actions(
                    Name="Container",
                    ActionTypeId=ActionTypeID(
                        Category="Build",
                        Owner="AWS",
                        Version="1",
                        Provider="CodeBuild"
                    ),
                    Configuration={
                        "ProjectName":Join(
                                "-",
                                [Select(0, Split("-", Ref("AWS::StackName"))),
                                    "codebuild"]
                            ),
                    },
                    InputArtifacts=[
                        InputArtifacts(
                            Name="App"
                        )
                    ],
                    OutputArtifacts=[
                        OutputArtifacts(
                            Name="BuildOutput"
                        )
                    ],
                )
            ]
        ),
        Stages(
            Name="Staging",
            Actions=[
                Actions(
                    Name="Deploy",
                    ActionTypeId=ActionTypeID(
                        Category="Deploy",
                        Owner="AWS",
                        Version="1",
                        Provider="CloudFormation"
                    ),
                    Configuration={
                        "ChangeSetName": "Deploy",
                        "ActionMode": "CREATE_UPDATE",
                        "StackName": "stag-cluster",
                        "Capabilities": "CAPABILITY_NAMED_IAM",
                        "TemplatePath": "BuildOutput::ecs-cluster-cf.template",
                        "RoleArn": GetAtt("CloudFormationClusterRole", "Arn"),
                        "ParameterOverrides": """{"VpcId" : { "Fn::GetParam" : [ "BuildOutput", "StageVpcId.json", "StageVpcId" ] },
                        "PublicSubnet" : { "Fn::GetParam" : [ "BuildOutput", "StagePublicSubnet.json", "StagePublicSubnet" ] },
                        "KeyPair" : { "Fn::GetParam" : [ "BuildOutput", "KeyPair.json", "KeyPair" ] } }"""
                    },
                    InputArtifacts=[
                        InputArtifacts(
                            Name="App",
                        ),
                        InputArtifacts(
                            Name="BuildOutput"
                        )
                    ],
                )
            ]
        ),
        Stages(
            Name="Deploy",
            Actions=[
                Actions(
                    Name="Deploy",
                    ActionTypeId=ActionTypeID(
                        Category="Deploy",
                        Owner="AWS",
                        Version="1",
                        Provider="CloudFormation"
                    ),
                    Configuration={
                        "ChangeSetName": "Deploy",
                        "ActionMode": "CREATE_UPDATE",
                        "StackName": "prod-cluster",
                        "Capabilities": "CAPABILITY_NAMED_IAM",
                        "TemplatePath": "BuildOutput::ecs-cluster-cf.template",
                        "RoleArn": GetAtt("CloudFormationClusterRole", "Arn"),
                        "ParameterOverrides": """{"VpcId" : { "Fn::GetParam" : [ "BuildOutput", "ProdVpcId.json", "ProdVpcId" ] } ,
                        "PublicSubnet" : { "Fn::GetParam" : [ "BuildOutput", "ProdPublicSubnet.json", "ProdPublicSubnet" ] },
                        "KeyPair" : { "Fn::GetParam" : [ "BuildOutput", "KeyPair.json", "KeyPair" ] } }"""
                    },
                    InputArtifacts=[
                        InputArtifacts(
                            Name="App",
                        ),
                        InputArtifacts(
                            Name="BuildOutput"
                        )
                    ],
                )
            ]
        )
    ],
))





###########
# Outputs #
###########

t.add_output(Output(
    "CodebuildName",
    Description="Codebuild Name",
    Value=Join(
            "-",
            [Select(0, Split("-", Ref("AWS::StackName"))),
                "codebuild"]
        )
))



print(t.to_json())
