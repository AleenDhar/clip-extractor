#!/bin/bash

# AWS ECS Setup Script for Gemini Clip Extractor
# Run this script to set up AWS infrastructure

set -e

# Configuration
AWS_REGION="us-east-1"
CLUSTER_NAME="gemini-app-cluster"
SERVICE_NAME="gemini-app-service"
TASK_DEFINITION="gemini-app-task"
ECR_REPOSITORY="gemini-clip-extractor"
VPC_NAME="gemini-app-vpc"
SUBNET_NAME="gemini-app-subnet"
SECURITY_GROUP_NAME="gemini-app-sg"

echo "🚀 Setting up AWS infrastructure for Gemini Clip Extractor..."

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account ID: $ACCOUNT_ID"

# 1. Create ECR Repository
echo "📦 Creating ECR repository..."
aws ecr create-repository \
    --repository-name $ECR_REPOSITORY \
    --region $AWS_REGION \
    --image-scanning-configuration scanOnPush=true || echo "Repository may already exist"

# 2. Create ECS Cluster
echo "🏗️ Creating ECS cluster..."
aws ecs create-cluster \
    --cluster-name $CLUSTER_NAME \
    --capacity-providers FARGATE \
    --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1 \
    --region $AWS_REGION || echo "Cluster may already exist"

# 3. Create VPC and networking (if not exists)
echo "🌐 Setting up VPC and networking..."
VPC_ID=$(aws ec2 create-vpc \
    --cidr-block 10.0.0.0/16 \
    --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=$VPC_NAME}]" \
    --query 'Vpc.VpcId' \
    --output text \
    --region $AWS_REGION 2>/dev/null || aws ec2 describe-vpcs --filters "Name=tag:Name,Values=$VPC_NAME" --query 'Vpcs[0].VpcId' --output text)

echo "VPC ID: $VPC_ID"

# Create Internet Gateway
IGW_ID=$(aws ec2 create-internet-gateway \
    --tag-specifications "ResourceType=internet-gateway,Tags=[{Key=Name,Value=$VPC_NAME-igw}]" \
    --query 'InternetGateway.InternetGatewayId' \
    --output text \
    --region $AWS_REGION 2>/dev/null || aws ec2 describe-internet-gateways --filters "Name=tag:Name,Values=$VPC_NAME-igw" --query 'InternetGateways[0].InternetGatewayId' --output text)

# Attach IGW to VPC
aws ec2 attach-internet-gateway \
    --internet-gateway-id $IGW_ID \
    --vpc-id $VPC_ID \
    --region $AWS_REGION 2>/dev/null || echo "IGW already attached"

# Create public subnets
SUBNET1_ID=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.1.0/24 \
    --availability-zone ${AWS_REGION}a \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=$SUBNET_NAME-1}]" \
    --query 'Subnet.SubnetId' \
    --output text \
    --region $AWS_REGION 2>/dev/null || aws ec2 describe-subnets --filters "Name=tag:Name,Values=$SUBNET_NAME-1" --query 'Subnets[0].SubnetId' --output text)

SUBNET2_ID=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.2.0/24 \
    --availability-zone ${AWS_REGION}b \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=$SUBNET_NAME-2}]" \
    --query 'Subnet.SubnetId' \
    --output text \
    --region $AWS_REGION 2>/dev/null || aws ec2 describe-subnets --filters "Name=tag:Name,Values=$SUBNET_NAME-2" --query 'Subnets[0].SubnetId' --output text)

echo "Subnet 1 ID: $SUBNET1_ID"
echo "Subnet 2 ID: $SUBNET2_ID"

# Create route table and routes
ROUTE_TABLE_ID=$(aws ec2 create-route-table \
    --vpc-id $VPC_ID \
    --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=$VPC_NAME-rt}]" \
    --query 'RouteTable.RouteTableId' \
    --output text \
    --region $AWS_REGION 2>/dev/null || aws ec2 describe-route-tables --filters "Name=tag:Name,Values=$VPC_NAME-rt" --query 'RouteTables[0].RouteTableId' --output text)

aws ec2 create-route \
    --route-table-id $ROUTE_TABLE_ID \
    --destination-cidr-block 0.0.0.0/0 \
    --gateway-id $IGW_ID \
    --region $AWS_REGION 2>/dev/null || echo "Route already exists"

# Associate subnets with route table
aws ec2 associate-route-table \
    --subnet-id $SUBNET1_ID \
    --route-table-id $ROUTE_TABLE_ID \
    --region $AWS_REGION 2>/dev/null || echo "Subnet 1 already associated"

aws ec2 associate-route-table \
    --subnet-id $SUBNET2_ID \
    --route-table-id $ROUTE_TABLE_ID \
    --region $AWS_REGION 2>/dev/null || echo "Subnet 2 already associated"

# 4. Create Security Group
echo "🔒 Creating security group..."
SECURITY_GROUP_ID=$(aws ec2 create-security-group \
    --group-name $SECURITY_GROUP_NAME \
    --description "Security group for Gemini app" \
    --vpc-id $VPC_ID \
    --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=$SECURITY_GROUP_NAME}]" \
    --query 'GroupId' \
    --output text \
    --region $AWS_REGION 2>/dev/null || aws ec2 describe-security-groups --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" --query 'SecurityGroups[0].GroupId' --output text)

echo "Security Group ID: $SECURITY_GROUP_ID"

# Add inbound rules
aws ec2 authorize-security-group-ingress \
    --group-id $SECURITY_GROUP_ID \
    --protocol tcp \
    --port 7860 \
    --cidr 0.0.0.0/0 \
    --region $AWS_REGION 2>/dev/null || echo "Ingress rule already exists"

aws ec2 authorize-security-group-ingress \
    --group-id $SECURITY_GROUP_ID \
    --protocol tcp \
    --port 80 \
    --cidr 0.0.0.0/0 \
    --region $AWS_REGION 2>/dev/null || echo "HTTP ingress rule already exists"

# 5. Create IAM roles
echo "👤 Creating IAM roles..."

# ECS Task Execution Role
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
    --role-name ecsTaskExecutionRole \
    --assume-role-policy-document file://trust-policy.json \
    --region $AWS_REGION 2>/dev/null || echo "Execution role already exists"

aws iam attach-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy \
    --region $AWS_REGION 2>/dev/null || echo "Policy already attached"

# ECS Task Role
aws iam create-role \
    --role-name ecsTaskRole \
    --assume-role-policy-document file://trust-policy.json \
    --region $AWS_REGION 2>/dev/null || echo "Task role already exists"

# 6. Create CloudWatch Log Group
echo "📊 Creating CloudWatch log group..."
aws logs create-log-group \
    --log-group-name /ecs/gemini-app \
    --region $AWS_REGION 2>/dev/null || echo "Log group already exists"

# 7. Create Secrets Manager secret for API key
echo "🔐 Creating Secrets Manager secret..."
aws secretsmanager create-secret \
    --name gemini-api-key \
    --description "Gemini API Key for clip extractor" \
    --secret-string '{"GEMINI_API_KEY":"YOUR_API_KEY_HERE"}' \
    --region $AWS_REGION 2>/dev/null || echo "Secret already exists"

# 8. Update task definition with actual values
echo "📝 Updating task definition..."
sed -i "s/YOUR_ACCOUNT_ID/$ACCOUNT_ID/g" task-definition.json

echo "✅ AWS infrastructure setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Update the Gemini API key in AWS Secrets Manager:"
echo "   aws secretsmanager update-secret --secret-id gemini-api-key --secret-string '{\"GEMINI_API_KEY\":\"your-actual-api-key\"}'"
echo ""
echo "2. Set up GitHub secrets:"
echo "   - AWS_ACCESS_KEY_ID"
echo "   - AWS_SECRET_ACCESS_KEY"
echo ""
echo "3. Push your code to trigger the deployment pipeline"
echo ""
echo "🌐 Infrastructure details:"
echo "   VPC ID: $VPC_ID"
echo "   Subnet 1: $SUBNET1_ID"
echo "   Subnet 2: $SUBNET2_ID"
echo "   Security Group: $SECURITY_GROUP_ID"
echo "   ECR Repository: $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY"

# Cleanup
rm -f trust-policy.json
