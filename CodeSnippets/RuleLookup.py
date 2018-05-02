import boto3


elb = boto3.client('elbv2', region_name='us-west-1')


stagingLB = 'arn:aws:elasticloadbalancing:us-west-1:262328827817:loadbalancer/app/ECS-L-stagL-1VEGSN39B6RRW/522b9920b1f0f144'
prodLB = 'arn:aws:elasticloadbalancing:us-west-1:262328827817:loadbalancer/app/ECS-L-prodL-U38Z64IP7I63/3b57de56078bd806'

ALB_ARNs = [stagingLB, prodLB]
Listener_ARNs = []

# Get list of ELBs
for LB in ALB_ARNs:
    # Get the LB's listener list
    response = elb.describe_listeners(
        LoadBalancerArn=LB,
    )['Listeners']

    # For each listener, get the ARN
    for Listener in response:
        print(Listener['LoadBalancerArn'])
        print("===================================")
        Listener_ARNs.append(Listener['ListenerArn'])



# List of rules in listeners

# List of used priorities
priorities = []

for Listener in Listener_ARNs:
    response = elb.describe_rules(
        ListenerArn= Listener
    )['Rules']
    # print(response)
    # print("///////////////////////////////////////////")

    for rule in response:
        priorities.append(rule['Priority'])

print("Priorities:")
print(priorities)

pty = 1
match = True
while match == True:
    if str(pty) in priorities:
        pty += 1
        match = True
    else:
        match = False

print(pty)
