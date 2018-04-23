"""Generating CloudFormation template."""

from troposphere import (
    Export,
    Join,
    Output,
    Parameter,
    Ref,
    Template
)
from troposphere.ecr import Repository

# Troposphere templates must start by defining a template instance
t = Template()

# Add a description for the repository
t.add_description("Effective DevOps in AWS: ECR Repository")

# Make the repo name a parameter
t.add_parameter(Parameter(
    "RepoName",
    Type="String",
    Description="Name of the ECR repository to create"
))

# Create the resource
t.add_resource(Repository(
    "Repository",
    RepositoryName=Ref("RepoName")
))

# Define the stack output
t.add_output(Output(
    "Repository",
    Description="ECR repository",
    Value=Ref("RepoName"),
    Export=Export(Join("-", [Ref("RepoName"), "repo"])),
))

print(t.to_json())
