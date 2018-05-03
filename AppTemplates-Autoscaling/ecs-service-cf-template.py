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
    Policy,
    Principal,
    Statement
)

from troposphere.iam import (
    InstanceProfile,
    Role
)

from troposphere.iam import Policy as IAMPolicy

from troposphere import (
    Parameter,
    Ref,
    Template,
    Join,
    ImportValue,
    GetAtt,
    Select,
    Split,
)

from troposphere.applicationautoscaling import (
    ScalableTarget,
    StepAdjustment,
    StepScalingPolicyConfiguration,
    ScalingPolicy,
)

from awacs.sts import AssumeRole

from troposphere.cloudwatch import (
    Alarm,
    MetricDimension
)


# Get configuration from YAML
with open('service_config.yaml', 'r') as f:
    doc = yaml.load(f)
TaskCPU = doc['TaskCPU']
TaskMemory = doc['TaskMemory']
DesiredTaskCapacity = doc['DesiredTaskCapacity']
MinTaskCapacity = doc['MinTaskCapacity']
MaxTaskCapacity = doc['MaxTaskCapacity']


t = Template()

t.add_description("ECS service")


t.add_parameter(Parameter(
    "Tag",
    Type="String",
    Default="latest",
    Description="Tag to deploy"
))

# c5b1dc0a50a8c10a18750dc7f6246e9d1c6aa568

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

ecsservice = t.add_resource(ecs.Service(
    "service",
    Cluster=ImportValue(Join("-",
            [Select(0, Split("-", Ref("AWS::StackName"))),
            "cluster-id"])),
    DesiredCount=DesiredTaskCapacity,
    TaskDefinition=Ref("task"),
    LoadBalancers=[ecs.LoadBalancer(
        ContainerName=Select(1, Split("-", Ref("AWS::StackName"))),
        ContainerPort=3000,
        TargetGroupArn=ImportValue(
            Join("-",
                [Select(0, Split("-", Ref("AWS::StackName"))),
                Select(1, Split("-", Ref("AWS::StackName"))),
                "tg"]),
        ),
    )],
    Role=Ref("ServiceRole")
))


# Configure application scaling
## Start with application autoscaling role
appscalingrole = t.add_resource(Role(
    "ApplicationScalingRole",
    AssumeRolePolicyDocument=Policy(
        Statement=[
            Statement(
                Effect=Allow,
                Action=[AssumeRole],
                Principal=Principal("Service", ["application-autoscaling.amazonaws.com"])
            )
        ]
    ),
    Path="/",
    Policies=[
        IAMPolicy(
            PolicyName=Join("-",
                [Select(0, Split("-", Ref("AWS::StackName"))),
                Select(1, Split("-", Ref("AWS::StackName"))),
                "ScalingRole"]),
            PolicyDocument={
                "Statement": [
                    {"Effect": "Allow", "Action": "ecs:UpdateService", "Resource": "*"},
                    {"Effect": "Allow", "Action": "ecs:DescribeServices", "Resource": "*"},
                    {"Effect": "Allow", "Action": "application-autoscaling:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "cloudwatch:DescribeAlarms", "Resource": "*"},
                    {"Effect": "Allow", "Action": "cloudwatch:GetMetricStatistics", "Resource": "*"},
                ],
            }
        ),
    ]
))



# Set the target
t.add_resource(ScalableTarget(
    "scalableTarget",
    MaxCapacity=MaxTaskCapacity,
    MinCapacity=MinTaskCapacity,
    ResourceId=Join("/",
        ["service",
        ImportValue(Join("-", [Select(0, Split("-", Ref("AWS::StackName"))), "cluster-id"])),
        GetAtt(ecsservice, "Name")]),
    RoleARN=GetAtt(appscalingrole, "Arn"),
    ScalableDimension='ecs:service:DesiredCount',
    ServiceNamespace='ecs',
))


# Set scaling policies
states = {
    "High": {
        "threshold": "75",
        "alarmPrefix": "ScaleUpPolicyFor",
        "operator": "GreaterThanOrEqualToThreshold",
        "adjustment": "1"
    },
    "Low": {
        "threshold": "40",
        "alarmPrefix": "ScaleDownPolicyFor",
        "operator": "LessThanOrEqualToThreshold",
        "adjustment": "-1"
    }
}

for utilization in {"CPU"}:
    for state, value in states.items():
        t.add_resource(Alarm(
            "{}UtilizationToo{}".format(utilization, state),
            AlarmDescription="Alarm if {} utilization too {}".format(
                utilization,
                state),
            Namespace="AWS/ECS",
            MetricName="{}Utilization".format(utilization),
            Dimensions=[
                MetricDimension(
                    Name="ServiceName",
                    Value=Ref("service")
                ),
                MetricDimension(
                    Name="ClusterName",
                    Value=ImportValue(Join("-",
                            [Select(0, Split("-", Ref("AWS::StackName"))),
                            "cluster-id"]))
                ),
            ],
            Statistic="Average",
            Period="60",
            EvaluationPeriods="1",
            Threshold=value['threshold'],
            ComparisonOperator=value['operator'],
            AlarmActions=[
                Ref("{}{}".format(value['alarmPrefix'], utilization))]
        ))

        if state == "Low":
            t.add_resource(ScalingPolicy(
                "{}{}".format(value['alarmPrefix'], utilization),
                PolicyName="{}{}".format(value['alarmPrefix'], utilization),
                PolicyType='StepScaling',
                ScalingTargetId=Ref("scalableTarget"),
                StepScalingPolicyConfiguration=StepScalingPolicyConfiguration(
                    AdjustmentType='ChangeInCapacity',
                    Cooldown=60,
                    MetricAggregationType='Average',
                    StepAdjustments=[
                        StepAdjustment(
                            MetricIntervalUpperBound=0,
                            ScalingAdjustment=value['adjustment'],
                        ),
                    ],
                ),
            ))
        if state == "High":
            t.add_resource(ScalingPolicy(
                "{}{}".format(value['alarmPrefix'], utilization),
                PolicyName="{}{}".format(value['alarmPrefix'], utilization),
                PolicyType='StepScaling',
                ScalingTargetId=Ref("scalableTarget"),
                StepScalingPolicyConfiguration=StepScalingPolicyConfiguration(
                    AdjustmentType='ChangeInCapacity',
                    Cooldown=60,
                    MetricAggregationType='Average',
                    StepAdjustments=[
                        StepAdjustment(
                            MetricIntervalLowerBound=0,
                            ScalingAdjustment=value['adjustment'],
                        ),
                    ],
                ),
            ))


print(t.to_json())
