"""Generating CloudFormation template."""

from troposphere import elasticloadbalancingv2 as elb

from troposphere import route53

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
    ec2,
    FindInMap
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

if EnvironmentType == "production":
    URLPathMod = ""
else:
    URLPathMod = "{}.".format(EnvironmentType)

t.add_parameter(Parameter(
    "DomainName",
    Type="String",
    Default="data-muffin.com",
    Description="Domain name registered in Route53"
))



t.add_mapping('RegionZIDMap', {
    "us-east-1":      {"ZoneID": "Z35SXDOTRQ7X7K"},
    "us-west-1":      {"ZoneID": "Z368ELLRRE2KJ0"},
    "us-west-2":      {"ZoneID": "Z1H1FL5HABSF5"}
})



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
ALBResource = t.add_resource(elb.LoadBalancer(
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


# t.add_resource(route53.AliasTarget(
#     "AliasTargetString",
#     DNSName=GetAtt("LoadBalancer", "DNSName"),
#     HostedZoneId=FindInMap("RegionZIDMap", Ref("AWS::Region"), "ZoneID")
# ))

for s in services:
    priority = services.index(s) + 1

    t.add_resource(elb.ListenerRule(
            "{}ListenerRule".format(s),
            ListenerArn=Ref("Listener"),
            Conditions=[elb.Condition(
                Field="host-header",
                Values=[Join("", [s, ".", URLPathMod, Ref("DomainName")])]
                )],
            Actions=[elb.Action(
                Type="forward",
                TargetGroupArn=Ref("{}{}TargetGroup".format(EnvironmentType, s))
            )],
            Priority=priority
        ))


#################### Add environment to logical description ##########################
    t.add_resource(route53.RecordSetType(
        "{}DNSRecord".format(s),
        HostedZoneName=Join("", [Ref("DomainName"), "."]),
        Name=Join("", [s, ".", URLPathMod, Ref("DomainName"), "."]),
        Type="A",
        AliasTarget=route53.AliasTarget(
            FindInMap("RegionZIDMap", Ref("AWS::Region"), "ZoneID"),
            GetAtt("LoadBalancer", "DNSName")
        )
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
        Value=Join("", [s, ".", URLPathMod, Ref("DomainName")])
    ))

t.add_output(Output(
    "LBDNS",
    Description="Load Balancer DNS",
    Value= GetAtt("LoadBalancer", "DNSName")
))

t.add_output(Output(
    "LBZoneID",
    Description="Load Balancer Zone ID",
    Value= FindInMap("RegionZIDMap", Ref("AWS::Region"), "ZoneID")
    #Value=GetAtt("LoadBalancer", "CanonicalHostedZoneNameID")
))


print(t.to_json())
