
# Step 1: ECR

In the first step, we will create an ECR repository and send a sample container to it.

To generate the CFN template from the python script, run the following:
```
python ecr-repository-cf-template.py > ecr-repository-cf.template
```

Then deploy to CFN:
```
aws cloudformation create-stack \
      --stack-name helloworld-ecr \
      --capabilities CAPABILITY_IAM \
      --template-body file://ecr-repository-cf.template \
      --parameters \
        ParameterKey=RepoName,ParameterValue=helloworld
```

Re-tag an image to send to ECR. In this case, a sample helloworld container.
```
docker tag helloworld:latest 637589118214.dkr.ecr.us-west-2.amazonaws.com/helloworld:latest
```

Get credentials
```
eval $(aws ecr get-login --no-include-email | sed 's|https://||')
```

Push the container to ECR.
```
docker push 637589118214.dkr.ecr.us-west-2.amazonaws.com/helloworld:latest

```

# Step 2: ECS Cluster

Convert python Template
```
python ecs-cluster-cf-template.py > ecs-cluster-cf.template
```

```
aws cloudformation create-stack \
      --stack-name staging-cluster \
      --capabilities CAPABILITY_IAM \
      --template-body file://ecs-cluster-cf.template \
      --parameters \
        ParameterKey=VpcId,ParameterValue=vpc-7eae6607 \
        ParameterKey=PublicSubnet,ParameterValue=subnet-f2959c94\\,subnet-24361e6c
```

# Step 3: ECS Application Load Balancer (ALB)

```
python helloworld-ecs-alb-cf-template.py > helloworld-ecs-alb-cf.template

aws cloudformation create-stack \
      --stack-name staging-alb \
      --capabilities CAPABILITY_IAM \
      --template-body file://helloworld-ecs-alb-cf.template
```
