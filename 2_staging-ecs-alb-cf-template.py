"""Generating CloudFormation template."""

from troposphere import elasticloadbalancingv2 as elb

from troposphere import (
    Export,
    GetAtt,
    ImportValue,
    Join,
    Output,
    Ref,
    Select,
    Split,
    Parameter,
    Sub,
    Template,
    ec2
)

t = Template()

t.add_description("Multi-path ALB for the ECS Cluster")

"""
This template creates an ALB that can provide path forwarding
to multiple services on an ECS cluster.
"""

# Define a list of services, in order of priority, to be routed by the ALB:
services = ["helloworld", "goodbyeworld"]
EnvironmentType = "staging"

# Define a Security group with Port 80, this is the port the LB will listen on
t.add_resource(ec2.SecurityGroup(
    "LoadBalancerSecurityGroup",
    GroupDescription="Web load balancer security group.",
    VpcId=ImportValue(
        Join(
            "-",
            [Select(0, Split("-", Ref("AWS::StackName"))),
                "cluster-vpc-id"]
        )
    ),
    SecurityGroupIngress=[
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="80",
            ToPort="80",
            CidrIp="0.0.0.0/0",
        ),
    ],
))




# Add the LB using our SG and user-defined subnets
t.add_resource(elb.LoadBalancer(
    "LoadBalancer",
    Scheme="internet-facing",
    Subnets=Split(
        ',',
        ImportValue(
            Join("-",
                 [Select(0, Split("-", Ref("AWS::StackName"))),
                  "cluster-public-subnets"]
                 )
        )
    ),
    SecurityGroups=[Ref("LoadBalancerSecurityGroup")],
))




# Run a for-loop to create target groups for each service
for s in services:
    t.add_resource(elb.TargetGroup(
        #"TargetGroup",
        "{}{}TargetGroup".format(EnvironmentType, s),
        Name=Join("-", [EnvironmentType, s, "TG"]),
        DependsOn='LoadBalancer',
        HealthCheckIntervalSeconds="20",
        HealthCheckProtocol="HTTP",
        HealthCheckTimeoutSeconds="15",
        HealthyThresholdCount="5",
        HealthCheckPath="/{}".format(s),
        Matcher=elb.Matcher(
            HttpCode="200"),
        Port=3000,
        Protocol="HTTP",
        UnhealthyThresholdCount="3",
        VpcId=ImportValue(
            Join(
                "-",
                [Select(0, Split("-", Ref("AWS::StackName"))),
                    "cluster-vpc-id"]
            )
        ),
    ))




t.add_resource(elb.Listener(
    "Listener",
    Port="80",
    Protocol="HTTP",
    LoadBalancerArn=Ref("LoadBalancer"),
    DefaultActions=[elb.Action(
        Type="forward",
        TargetGroupArn=Ref("{}{}TargetGroup".format(EnvironmentType, services[0]))
    )]
))


for s in services:
    priority = services.index(s) + 1

    t.add_resource(elb.ListenerRule(
            "{}ListenerRule".format(s),
            ListenerArn=Ref("Listener"),
            Conditions=[elb.Condition(
                Field="path-pattern",
                Values=["/{}-{}".format(EnvironmentType, s)])],
            Actions=[elb.Action(
                Type="forward",
                TargetGroupArn=Ref("{}{}TargetGroup".format(EnvironmentType, s))
            )],
            Priority=priority
        ))



# Outputs

for s in services:
    t.add_output(Output(
        "{}{}TargetGroup".format(EnvironmentType, s),
        Description="Target group for {} {}".format(EnvironmentType, s),
        Value=Ref("{}{}TargetGroup".format(EnvironmentType, s)),
        Export=Export(Sub("{}-{}-tg".format(EnvironmentType, s)))
    ))


    t.add_output(Output(
        "{}URL".format(s),
        Description="Loadbalancer URL for {}".format(s),
        Value=Join("", ["http://", GetAtt("LoadBalancer", "DNSName"), "/", EnvironmentType, "-", s])
    ))



print(t.to_json())
