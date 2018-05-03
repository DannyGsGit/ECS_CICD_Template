"""Generating CloudFormation template."""
""" Stack name must be of format staging-appname-service"""

import yaml

from troposphere.ecs import (
    TaskDefinition,
    ContainerDefinition
)

from troposphere import ecs

from awacs.aws import (
    Allow,
    Statement,
    Principal,
    Policy
)
from troposphere.iam import Role

from troposphere import (
    Parameter,
    Ref,
    Template,
    Join,
    ImportValue,
    Select,
    Split,
)

from awacs.sts import AssumeRole


# Get configuration from YAML
with open('service_config.yaml', 'r') as f:
    doc = yaml.load(f)
TaskCPU = doc['TaskCPU']
TaskMemory = doc['TaskMemory']


t = Template()

t.add_description("ECS service")


t.add_parameter(Parameter(
    "Tag",
    Type="String",
    Default="latest",
    Description="Tag to deploy"
))

# t.add_parameter(Parameter(
#     "TaskCPU",
#     Type="Number",
#     Default=256,
#     Description="Task CPU Allocation (1024 = 1 core)"
# ))
#
# t.add_parameter(Parameter(
#     "TaskMemory",
#     Type="Number",
#     Default=32,
#     Description="Task Memory Allocation (MiB)"
# ))


# First, we define an ECS task

t.add_resource(TaskDefinition(
    "task",
    ContainerDefinitions=[
        ContainerDefinition(
            Image=Join("", [
                Ref("AWS::AccountId"),
                ".dkr.ecr.",
                Ref("AWS::Region"),
                ".amazonaws.com",
                "/",
                Select(1, Split("-", Ref("AWS::StackName"))),
                ":",
                Ref("Tag")]),
            Memory=TaskMemory,
            Cpu=TaskCPU,
            Name=Select(1, Split("-", Ref("AWS::StackName"))),
            PortMappings=[ecs.PortMapping(
                ContainerPort=3000)]
        )
    ],
))




# Then a service

t.add_resource(Role(
    "ServiceRole",
    AssumeRolePolicyDocument=Policy(
        Statement=[
            Statement(
                Effect=Allow,
                Action=[AssumeRole],
                Principal=Principal("Service", ["ecs.amazonaws.com"])
            )
        ]
    ),
    Path="/",
    ManagedPolicyArns=[
        'arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceRole']
))

t.add_resource(ecs.Service(
    "service",
    Cluster=ImportValue(
        Join(
            "-",
            [Select(0, Split("-", Ref("AWS::StackName"))),
                "cluster-id"]
        )
    ),
    DesiredCount=1,
    TaskDefinition=Ref("task"),
    LoadBalancers=[ecs.LoadBalancer(
        ContainerName=Select(1, Split("-", Ref("AWS::StackName"))),
        ContainerPort=3000,
        TargetGroupArn=ImportValue(
            Join(
                "-",
                [Select(0, Split("-", Ref("AWS::StackName"))),
                Select(1, Split("-", Ref("AWS::StackName"))),
                    "tg"]
            ),
        ),
    )],
    Role=Ref("ServiceRole")
))

print(t.to_json())
