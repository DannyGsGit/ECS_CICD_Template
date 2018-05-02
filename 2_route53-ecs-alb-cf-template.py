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
services = ["helloworld", "goodbyeworld", "nicksapp", "newapp"]
Environments = ["stag", "prod"]



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


# Create a set of resources for each environment
for e in Environments:

    # Define a Security group with Port 80, this is the port the LB will listen on
    t.add_resource(ec2.SecurityGroup(
        "{}ELBSecurityGroup".format(e),
        GroupDescription="Web load balancer security group.",
        VpcId=ImportValue(
            Join(
                "-",
                [e, "cluster-vpc-id"]
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
        "{}LoadBalancer".format(e),
        Scheme="internet-facing",
        Subnets=Split(
            ',',
            ImportValue(
                Join("-", [e, "cluster-public-subnets"])
            )
        ),
        SecurityGroups=[Ref("{}ELBSecurityGroup".format(e))],
    ))




    # Run a for-loop to create target groups for each service
    for s in services:
        t.add_resource(elb.TargetGroup(
            #"TargetGroup",
            "{}{}TargetGroup".format(e, s),
            Name=Join("-", [e, s, "TG"]),
            DependsOn="{}LoadBalancer".format(e),
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
                Join("-", [e, "cluster-vpc-id"])
            ),
        ))





    t.add_resource(elb.Listener(
        "{}Listener".format(e),
        Port="80",
        Protocol="HTTP",
        LoadBalancerArn=Ref("{}LoadBalancer".format(e)),
        DefaultActions=[elb.Action(
            Type="forward",
            TargetGroupArn=Ref("{}{}TargetGroup".format(e, services[0]))
        )]
    ))




    for s in services:
        # Set an integer for the rule priority. This assumes the list of
        # services is ordered by priority.
        priority = services.index(s) + 1

        # Set a URL extension for non-prod environments
        if e == "prod":
            URLPathMod = ""
        else:
            URLPathMod = "{}.".format(e)

        t.add_resource(elb.ListenerRule(
                "{}{}ListenerRule".format(e, s),
                ListenerArn=Ref("{}Listener".format(e)),
                Conditions=[elb.Condition(
                    Field="host-header",
                    Values=[Join("", [s, ".", URLPathMod, Ref("DomainName")])]
                    )],
                Actions=[elb.Action(
                    Type="forward",
                    TargetGroupArn=Ref("{}{}TargetGroup".format(e, s))
                )],
                Priority=priority
            ))


        t.add_resource(route53.RecordSetType(
            "{}{}DNSRecord".format(e, s),
            HostedZoneName=Join("", [Ref("DomainName"), "."]),
            Name=Join("", [s, ".", URLPathMod, Ref("DomainName"), "."]),
            Type="A",
            AliasTarget=route53.AliasTarget(
                FindInMap("RegionZIDMap", Ref("AWS::Region"), "ZoneID"),
                GetAtt("{}LoadBalancer".format(e), "DNSName")
            )
        ))



    # Outputs

    for s in services:
        t.add_output(Output(
            "{}{}TargetGroup".format(e, s),
            Description="Target group for {} {}".format(e, s),
            Value=Ref("{}{}TargetGroup".format(e, s)),
            Export=Export(Sub("{}-{}-tg".format(e, s)))
        ))


        t.add_output(Output(
            "{}{}URL".format(e, s),
            Description="Loadbalancer URL for {} in {}".format(s, e),
            Value=Join("", ["http://", s, ".", URLPathMod, Ref("DomainName")])
        ))



print(t.to_json())
