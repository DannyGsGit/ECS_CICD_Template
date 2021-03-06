"""Generating CloudFormation template."""

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


"""
This template consolidates the following components:
* 3-ECR creation
* 4-Codebuild
* 6-Codepipeline

The template assumes that a compatible ECS service definition
template (step 5) is included in the ./templates path of the
Git repo to be deployed.

For good naming practice, the stack name should be of format:
appname-codepipeline
"""

t = Template()

t.add_description("New Service CICD Pipeline")


##############
# Parameters #
##############

t.add_parameter(Parameter(
    "RepoName",
    Type="String",
    Description="Name of the CodeCommit repository to source"
))


#############
# Resources #
#############


### ECR ####
# Create the resource
t.add_resource(Repository(
    "Repository",
    RepositoryName=Select(0, Split("-", Ref("AWS::StackName")))
))

# Define the stack output
t.add_output(Output(
    "Repository",
    Description="ECR repository",
    Value=Select(0, Split("-", Ref("AWS::StackName"))),
    Export=Export(Join("-", [Ref("RepoName"), "repo"])),
))



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






# Cloudformation Codebuild Definition
environment_cfn = Environment(
    ComputeType='BUILD_GENERAL1_SMALL',
    Image='aws/codebuild/docker:1.12.1',
    Type='LINUX_CONTAINER',
    EnvironmentVariables=[],
)



buildspec_cfn = """version: 0.1
phases:
  pre_build:
    commands:
      - pip install troposphere
      - pip install pyyaml
      - pip install awacs
  build:
    commands:
      - echo "Starting python execution"
      - python ecs-service-cf-template.py > /tmp/ecs-service-cf.template
  post_build:
    commands:
      - echo "Completed CFN template creation."
artifacts:
  files: /tmp/ecs-service-cf.template
  discard-paths: yes
"""

t.add_resource(Project(
    "CodeBuildCFN",
    Name=Join(
            "-",
            [Select(0, Split("-", Ref("AWS::StackName"))),
            "cfn",
            "codebuild"]
        ),
    Environment=environment_cfn,
    ServiceRole=Ref("ServiceRole"),
    Source=Source(
        Type="CODEPIPELINE",
        BuildSpec=buildspec_cfn
    ),
    Artifacts=Artifacts(
        Type="CODEPIPELINE",
        Name="output"
    ),
))



# Docker Codebuild Definition
environment_docker = Environment(
    ComputeType='BUILD_GENERAL1_SMALL',
    Image='aws/codebuild/docker:1.12.1',
    Type='LINUX_CONTAINER',
    EnvironmentVariables=[
        {'Name': 'REPOSITORY_NAME', 'Value': Select(0, Split("-", Ref("AWS::StackName")))},
        {'Name': 'REPOSITORY_URI',
            'Value': Join("", [
                Ref("AWS::AccountId"),
                ".dkr.ecr.",
                Ref("AWS::Region"),
                ".amazonaws.com",
                "/",
                Select(0, Split("-", Ref("AWS::StackName")))])}
    ],
)



buildspec_docker = """version: 0.1
phases:
  pre_build:
    commands:
      - aws codepipeline get-pipeline-state --name "${CODEBUILD_INITIATOR##*/}" --query stageStates[?actionStates[0].latestExecution.externalExecutionId==\`$CODEBUILD_BUILD_ID\`].latestExecution.pipelineExecutionId --output=text > /tmp/execution_id.txt
      - aws codepipeline get-pipeline-execution --pipeline-name "${CODEBUILD_INITIATOR##*/}" --pipeline-execution-id $(cat /tmp/execution_id.txt) --query 'pipelineExecution.artifactRevisions[0].revisionId' --output=text > /tmp/tag.txt
      - printf "%s:%s" "$REPOSITORY_URI" "$(cat /tmp/tag.txt)" > /tmp/build_tag.txt
      - printf '{"tag":"%s"}' "$(cat /tmp/tag.txt)" > /tmp/build.json
      - $(aws ecr get-login --no-include-email)
  build:
    commands:
      - docker build -t "$(cat /tmp/build_tag.txt)" .
  post_build:
    commands:
      - echo "$(cat /tmp/execution_id.txt)"
      - echo "$(cat /tmp/tag.txt)"
      - echo "$(cat /tmp/build_tag.txt)"
      - echo "$(cat /tmp/build.json)"
      - docker push "$(cat /tmp/build_tag.txt)"
      - aws ecr batch-get-image --repository-name $REPOSITORY_NAME --image-ids imageTag="$(cat /tmp/tag.txt)" --query 'images[].imageManifest' --output text | tee /tmp/latest_manifest.json
      - aws ecr put-image --repository-name $REPOSITORY_NAME --image-tag latest --image-manifest "$(cat /tmp/latest_manifest.json)"
artifacts:
  files: /tmp/*
  discard-paths: yes
"""

t.add_resource(Project(
    "CodeBuildDocker",
    Name=Join(
            "-",
            [Select(0, Split("-", Ref("AWS::StackName"))),
            "docker",
            "codebuild"]
        ),
    Environment=environment_docker,
    ServiceRole=Ref("ServiceRole"),
    Source=Source(
        Type="CODEPIPELINE",
        BuildSpec=buildspec_docker
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
            PolicyName="ECSCodePipeline",
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
    "CloudFormationECSRole",
    RoleName=Join(
            "-",
            [Select(0, Split("-", Ref("AWS::StackName"))),
                "CloudFormationECSRole"]
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
            PolicyName="CloudFormationECSPolicy",
            PolicyDocument={
                "Statement": [
                    {"Effect": "Allow", "Action": "cloudformation:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "ecr:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "ecs:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "iam:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "codecommit:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "application-autoscaling:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "cloudwatch:*", "Resource": "*"},
                ],
            }
        ),
    ]
))

t.add_resource(Pipeline(
    "ECSCICDPipeline",
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
            Name="CFNBuild",
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
                                "cfn",
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
                            Name="CFNBuildOutput"
                        )
                    ],
                )
            ]
        ),
        Stages(
            Name="DockerBuild",
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
                                "docker",
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
                            Name="DockerBuildOutput"
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
                        "StackName": Join(
                                "-",
                                ["stag",
                                Select(0, Split("-", Ref("AWS::StackName"))),
                                "service"]
                        ),
                        "Capabilities": "CAPABILITY_NAMED_IAM",
                        "TemplatePath": "CFNBuildOutput::ecs-service-cf.template",
                        "RoleArn": GetAtt("CloudFormationECSRole", "Arn"),
                        "ParameterOverrides": """{"Tag" : { "Fn::GetParam" : [ "DockerBuildOutput", "build.json", "tag" ] } }"""
                    },
                    InputArtifacts=[
                        InputArtifacts(
                            Name="App",
                        ),
                        InputArtifacts(
                            Name="CFNBuildOutput"
                        ),
                        InputArtifacts(
                            Name="DockerBuildOutput"
                        )
                    ],
                )
            ]
        ),
        Stages(
            Name="Approval",
            Actions=[
                Actions(
                    Name="Approval",
                    ActionTypeId=ActionTypeID(
                        Category="Approval",
                        Owner="AWS",
                        Version="1",
                        Provider="Manual"
                    ),
                    Configuration={},
                    InputArtifacts=[],
                )
            ]
        ),
        Stages(
            Name="Production",
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
                        "StackName": Join(
                                "-",
                                ["prod",
                                Select(0, Split("-", Ref("AWS::StackName"))),
                                "service"]
                        ),
                        "Capabilities": "CAPABILITY_NAMED_IAM",
                        "TemplatePath": "CFNBuildOutput::ecs-service-cf.template",
                        "RoleArn": GetAtt("CloudFormationECSRole", "Arn"),
                        "ParameterOverrides": """{"Tag" : { "Fn::GetParam" : [ "DockerBuildOutput", "build.json", "tag" ] } }"""
                    },
                    InputArtifacts=[
                        InputArtifacts(
                            Name="App",
                        ),
                        InputArtifacts(
                            Name="CFNBuildOutput"
                        ),
                        InputArtifacts(
                            Name="DockerBuildOutput"
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
