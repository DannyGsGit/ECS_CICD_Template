# Deployment Template
This collection of templates is used to deploy services on AWS ECS.

# Process

## 1- Deploy Cluster
Deploy two ECS clusters using the CFN template generated by *1_ecs-cluster-cf-template.py*.
When creating the clusters, provide names in the format **staging-cluster** and **production-cluster**.

## 2- Deploy ALBs
ALBs are the load balancers for the ECS clusters. The ALBs contain routing rules for the services we will deploy, therefore will see stack updates when new services are created. Out of the box, ALBs include *helloworld* and *goodbyeworld* service paths. Due to limitations with CloudFormation exports, this is currently managed with two templates.
The stacks must be deployed with stack names of format **staging-alb** and **production-alb**.

## 3- Provision App Repository
Provision a CodeCommit repo with the name of the app. In the folder, place the *ecs-service-cf.template* template in the ./templates directory and a Dockerfile in the root.

## 4- Service Template
Deploy the *deploy-service-cf.template*. This will launch a CodePipeline to orchestrate CodeBuild and deployment via nested CloudFormations.

It is recommended to name the stack with format **appname-codepipeline**, and list the name of your CodeCommit repo as the input parameter.



# Plan/ To Do:

- [x] Implement path-based routing pipe with simple appname by linking Services to ALB Paths
- [ ] Update ALB template for host-based routing connected to Route53
- [ ] Lock down security group on Route53/ALB
- [ ] Shorten prod/staging names
- [ ] CodePipeline for ALBs
- [ ] Scaling rules for containers
- [ ] Get Scout2 working
- [ ] Get CloudWatch dashboards coded
