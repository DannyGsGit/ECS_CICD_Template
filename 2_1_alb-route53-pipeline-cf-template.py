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

from troposphere.iam import Role

from troposphere.iam import Policy as IAMPolicy

from troposphere.s3 import Bucket, VersioningConfiguration




t = Template()

t.add_description("ALB and Route53 Pipeline")


##############
# Parameters #
##############


t.add_parameter(Parameter(
    "RepoName",
    Type="String",
    Default="alb-route53-cf",
    Description="Name of the CodeCommit repository to source"
))



t.add_parameter(Parameter(
    "Route53DomainName",
    Type="String",
    Default="data-muffin.com",
    Description="Domain name registered in Route53"
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
    EnvironmentVariables=[],
)



# buildspec = """version: 0.1
# phases:
#   pre_build:
#     commands:
#       - aws codepipeline get-pipeline-state --name "${CODEBUILD_INITIATOR##*/}" --query stageStates[?actionStates[0].latestExecution.externalExecutionId==\`$CODEBUILD_BUILD_ID\`].latestExecution.pipelineExecutionId --output=text > /tmp/execution_id.txt
#       - aws codepipeline get-pipeline-execution --pipeline-name "${CODEBUILD_INITIATOR##*/}" --pipeline-execution-id $(cat /tmp/execution_id.txt) --query 'pipelineExecution.artifactRevisions[0].revisionId' --output=text > /tmp/tag.txt
#       - printf "%s:%s" "$REPOSITORY_URI" "$(cat /tmp/tag.txt)" > /tmp/build_tag.txt
#       - printf '{"tag":"%s"}' "$(cat /tmp/tag.txt)" > /tmp/build.json
#       - $(aws ecr get-login --no-include-email)
#   build:
#     commands:
#       - docker build -t "$(cat /tmp/build_tag.txt)" .
#   post_build:
#     commands:
#       - echo "$(cat /tmp/execution_id.txt)"
#       - echo "$(cat /tmp/tag.txt)"
#       - echo "$(cat /tmp/build_tag.txt)"
#       - echo "$(cat /tmp/build.json)"
#       - docker push "$(cat /tmp/build_tag.txt)"
#       - aws ecr batch-get-image --repository-name $REPOSITORY_NAME --image-ids imageTag="$(cat /tmp/tag.txt)" --query 'images[].imageManifest' --output text | tee /tmp/latest_manifest.json
#       - aws ecr put-image --repository-name $REPOSITORY_NAME --image-tag latest --image-manifest "$(cat /tmp/latest_manifest.json)"
# artifacts:
#   files: /tmp/build.json
#   discard-paths: yes
# """

buildspec = """version: 0.1
phases:
  pre_build:
    commands:
      - pip install troposphere
      - pip install pyyaml
  build:
    commands:
      - echo "Starting python execution"
      - python alb-route53-cf-template.py > /tmp/alb-route53-cf.template
  post_build:
    commands:
      - echo "Completed CFN template creation."
artifacts:
  files: /tmp/alb-route53-cf.template
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
            PolicyName="NetworkCodePipeline",
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
    "CloudFormationNetworkRole",
    RoleName=Join(
            "-",
            [Select(0, Split("-", Ref("AWS::StackName"))),
                "CloudFormationNetworkRole"]
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
            PolicyName="CloudFormationNetworkPolicy",
            PolicyDocument={
                "Statement": [
                    {"Effect": "Allow", "Action": "cloudformation:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "ecr:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "ecs:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "iam:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "ec2:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "elasticloadbalancing:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "route53:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "codecommit:*", "Resource": "*"},
                ],
            }
        ),
    ]
))

t.add_resource(Pipeline(
    "NetworkPipeline",
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
                        "StackName": "ALB-Route53-Resources",
                        "Capabilities": "CAPABILITY_NAMED_IAM",
                        "TemplatePath": "BuildOutput::alb-route53-cf.template",
                        "RoleArn": GetAtt("CloudFormationNetworkRole", "Arn")
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
