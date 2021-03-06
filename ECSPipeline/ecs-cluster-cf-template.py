"""Generating CloudFormation template."""

import yaml

from troposphere import (
    Base64,
    Export,
    Join,
    Output,
    Parameter,
    Ref,
    Sub,
    Template,
    ec2,
    FindInMap,
    Split
)

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


# Instantiate the object
t = Template()

t.add_description("ECS Cluster Template")

# Get configuration from YAML
with open('cluster_config.yaml', 'r') as f:
    doc = yaml.load(f)
instanceSize = doc['instanceSize']
desiredCapacity = doc['desiredCapacity']
minCapacity = doc['minCapacity']
maxCapacity = doc['maxCapacity']
ScalingMetric = doc['ScalingMetric']
ScaleUpLevel = doc['ScaleUpLevel']
ScaleDownLevel = doc['ScaleDownLevel']




##############
# Parameters #
##############


t.add_parameter(Parameter(
    "VpcId",
    Type="String",
    Description="VPC"
))

t.add_parameter(Parameter(
    "PublicSubnet",
    Description="PublicSubnet",
    Type="String"
))

t.add_parameter(Parameter(
    "KeyPair",
    Description="Name of an existing EC2 KeyPair to SSH",
    Type="AWS::EC2::KeyPair::KeyName",
    ConstraintDescription="must be the name of an existing EC2 KeyPair.",
))





############
# Mappings #
############


# AMI Maps for EC2 ContainerInstances
t.add_mapping('RegionMap', {
    "us-east-1":      {"AMI": "ami-aff65ad2"},
    "us-west-1":      {"AMI": "ami-69677709"},
    "us-west-2":      {"AMI": "ami-40ddb938"}
})





#############
# Resources #
#############


# Security group to access the cluster. Includes PCAR proxy stuff.
t.add_resource(ec2.SecurityGroup(
    "SecurityGroup",
    GroupDescription="Allow SSH and private network access",
    SecurityGroupIngress=[
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort=0,
            ToPort=65535,
            CidrIp="172.16.0.0/12",
        ),
        # Zscaler ranges
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="22",
            ToPort="22",
            CidrIp="165.225.50.0/23",
        ),
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="22",
            ToPort="22",
            CidrIp="104.129.192.0/23",
        ),
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="80",
            ToPort="80",
            CidrIp="165.225.50.0/23",
        ),
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="80",
            ToPort="80",
            CidrIp="104.129.192.0/23",
        ),
    ],
    VpcId=Ref("VpcId")
))

# The ECS cluster
t.add_resource(Cluster(
    'ECSCluster',
))

# ECS Role
t.add_resource(Role(
    'EcsClusterRole',
    ManagedPolicyArns=[
        'arn:aws:iam::aws:policy/service-role/AmazonEC2RoleforSSM',
        'arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly',
        'arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role',
        'arn:aws:iam::aws:policy/CloudWatchFullAccess'
    ],
    AssumeRolePolicyDocument={
        'Version': '2012-10-17',
        'Statement': [{
            'Action': 'sts:AssumeRole',
            'Principal': {'Service': 'ec2.amazonaws.com'},
            'Effect': 'Allow',
        }]
    }
))

# ECS Instance Profile
t.add_resource(InstanceProfile(
    'EC2InstanceProfile',
    Roles=[Ref('EcsClusterRole')],
))

# ECS Launch Configuration to onboard new EC2 instances
t.add_resource(LaunchConfiguration(
    'ContainerInstances',
    UserData=Base64(Join('', [
        "#!/bin/bash -xe\n",
        "echo ECS_CLUSTER=",
        Ref('ECSCluster'),
        " >> /etc/ecs/ecs.config\n",
        "yum install -y aws-cfn-bootstrap\n",
        "/opt/aws/bin/cfn-signal -e $? ",
        "         --stack ",
        Ref('AWS::StackName'),
        "         --resource ECSAutoScalingGroup ",
        "         --region ",
        Ref('AWS::Region'),
        "\n"])),
    ImageId=FindInMap("RegionMap", Ref("AWS::Region"), "AMI"),
    KeyName=Ref("KeyPair"),
    SecurityGroups=[Ref("SecurityGroup")],
    IamInstanceProfile=Ref('EC2InstanceProfile'),
    InstanceType=instanceSize,
    AssociatePublicIpAddress='true',
))

t.add_resource(AutoScalingGroup(
    'ECSAutoScalingGroup',
    DesiredCapacity=desiredCapacity,
    MinSize=minCapacity,
    MaxSize=maxCapacity,
    VPCZoneIdentifier=Split(",", Ref("PublicSubnet")),
    LaunchConfigurationName=Ref('ContainerInstances'),
))

states = {
    "High": {
        "threshold": ScaleUpLevel,
        "alarmPrefix": "ScaleUpPolicyFor",
        "operator": "GreaterThanThreshold",
        "adjustment": "1"
    },
    "Low": {
        "threshold": ScaleDownLevel,
        "alarmPrefix": "ScaleDownPolicyFor",
        "operator": "LessThanThreshold",
        "adjustment": "-1"
    }
}

for reservation in {ScalingMetric}:
    for state, value in states.items():
        t.add_resource(Alarm(
            "{}ReservationToo{}".format(reservation, state),
            AlarmDescription="Alarm if {} reservation too {}".format(
                reservation,
                state),
            Namespace="AWS/ECS",
            MetricName="{}Reservation".format(reservation),
            Dimensions=[
                MetricDimension(
                    Name="ClusterName",
                    Value=Ref("ECSCluster")
                ),
            ],
            Statistic="Average",
            Period="60",
            EvaluationPeriods="1",
            Threshold=value['threshold'],
            ComparisonOperator=value['operator'],
            AlarmActions=[
                Ref("{}{}".format(value['alarmPrefix'], reservation))]
        ))
        t.add_resource(ScalingPolicy(
            "{}{}".format(value['alarmPrefix'], reservation),
            ScalingAdjustment=value['adjustment'],
            AutoScalingGroupName=Ref("ECSAutoScalingGroup"),
            AdjustmentType="ChangeInCapacity",
        ))


###########
# Outputs #
###########

t.add_output(Output(
    "Cluster",
    Description="ECS Cluster Name",
    Value=Ref("ECSCluster"),
    Export=Export(Sub("${AWS::StackName}-id")),
))

t.add_output(Output(
    "VpcId",
    Description="VpcId",
    Value=Ref("VpcId"),
    Export=Export(Sub("${AWS::StackName}-vpc-id")),
))

t.add_output(Output(
    "PublicSubnet",
    Description="PublicSubnet",
    Value=Ref("PublicSubnet"),
    Export=Export(Sub("${AWS::StackName}-public-subnets")),
))

print(t.to_json())
