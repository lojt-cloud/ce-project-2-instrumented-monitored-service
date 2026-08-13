# Deployment

## Prerequisites

AWS CLI installed and configured locally with permissions to create EC2 instances, IAM roles, SNS topics, and CloudWatch dashboards and alarms. An SSH key pair. `jq` and `envsubst` installed locally (`gettext-base` package provides `envsubst`).

All AWS control-plane steps below run from your local machine. Anything touching the running app runs over SSH on the instance, marked accordingly.

## 1. Launch the EC2 instance and IAM role
 
```bash

#create a keypair 
export AWS_REGION=us-east-1
KEY_NAME="your-key-name"
INSTANCE_TYPE="t3.micro"
APP_PORT=8080

aws ec2 create-key-pair \
  --key-name "$KEY_NAME" --query 'KeyMaterial' --output text \
  --region "$AWS_REGION" > "${KEY_NAME}.pem"
chmod 400 "${KEY_NAME}.pem"

# create IAM role 
aws iam create-role \
  --role-name AuthServiceEC2Role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}]
  }'

# attach policy to role 
aws iam attach-role-policy \
  --role-name AuthServiceEC2Role \
  --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy
aws iam create-instance-profile --instance-profile-name AuthServiceEC2Profile
aws iam add-role-to-instance-profile \
  --instance-profile-name AuthServiceEC2Profile --role-name AuthServiceEC2Role
sleep 10

# create a security group, allow SSH and the app port from your IP only 
MY_IP="$(curl -s https://checkip.amazonaws.com)/32"
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text --region "$AWS_REGION")
SG_ID=$(aws ec2 create-security-group \
  --group-name auth-service-sg --description "SSH and app access for the auth service demo" \
  --vpc-id "$VPC_ID" --query 'GroupId' --output text --region "$AWS_REGION")
aws ec2 authorize-security-group-ingress \
  --group-id "$SG_ID" --protocol tcp --port 22 --cidr "$MY_IP" --region "$AWS_REGION"
aws ec2 authorize-security-group-ingress \
  --group-id "$SG_ID" --protocol tcp --port "$APP_PORT" --cidr "$MY_IP" --region "$AWS_REGION"

# look up the latest Amazon Linux 2023 AMI, never hardcoded 
AMI_ID=$(aws ssm get-parameters \
  --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameters[0].Value' --output text --region "$AWS_REGION")

#run the EC2 instance
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI_ID" --instance-type "$INSTANCE_TYPE" --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" --iam-instance-profile Name=AuthServiceEC2Profile \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=auth-service-demo}]' \
  --query 'Instances[0].InstanceId' --output text --region "$AWS_REGION")
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$AWS_REGION"
PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text --region "$AWS_REGION")
echo "Public IP: $PUBLIC_IP"

```

## 2. Connect and pull the code

Over SSH:

```bash

ssh -i "${KEY_NAME}.pem" ec2-user@"$PUBLIC_IP"
sudo dnf install -y git python3-pip
git clone https://github.com/<your-username>/ce-project-2-instrumented-monitored-service.git
cd ce-project-2-instrumented-monitored-service

```

## 3. Deploy the app

Over SSH, from the repo root:

```bash

bash app/deploy.sh
curl http://localhost:8080/health

```

Should return `{"status":"ok"}`.

## 4. Install and configure the CloudWatch agent

Over SSH:

```bash

sudo dnf install -y amazon-cloudwatch-agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 \
  -c file:$HOME/ce-project-2-instrumented-monitored-service/config/cloudwatch-agent-config.json -s
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a status

```

Should show `"status": "running"`.

## 5. Create SNS topics

Locally:

```bash

export AWS_REGION=us-east-1
EMAIL="your-email@example.com"

# create the two topics
WARNING_TOPIC_ARN=$(aws sns create-topic --name auth-service-warning \
  --query 'TopicArn' --output text --region "$AWS_REGION")
CRITICAL_TOPIC_ARN=$(aws sns create-topic --name auth-service-critical \
  --query 'TopicArn' --output text --region "$AWS_REGION")

# subscribe your email to both 
aws sns subscribe --topic-arn "$WARNING_TOPIC_ARN" --protocol email \
  --notification-endpoint "$EMAIL" --region "$AWS_REGION"
aws sns subscribe --topic-arn "$CRITICAL_TOPIC_ARN" --protocol email \
  --notification-endpoint "$EMAIL" --region "$AWS_REGION"

```

Confirm both subscriptions from the email links sent, then verify:

```bash

aws sns list-subscriptions-by-topic --topic-arn "$WARNING_TOPIC_ARN" --region "$AWS_REGION"
aws sns list-subscriptions-by-topic --topic-arn "$CRITICAL_TOPIC_ARN" --region "$AWS_REGION"

```

`SubscriptionArn` should be a real ARN, not `PendingConfirmation`.

## 6. Apply the dashboard and alarms

Locally:

```bash

export SNS_WARNING_TOPIC_ARN="$WARNING_TOPIC_ARN"
export SNS_CRITICAL_TOPIC_ARN="$CRITICAL_TOPIC_ARN"
export INSTANCE_ID="$INSTANCE_ID"

# apply the alarms, one at a time since put-metric-alarm only accepts a single alarm per call
envsubst < config/dashboard.json > /tmp/dashboard.rendered.json
aws cloudwatch put-dashboard \
  --dashboard-name AuthServiceDashboard \
  --dashboard-body file:///tmp/dashboard.rendered.json --region "$AWS_REGION"

envsubst < config/alarms.json > /tmp/alarms.rendered.json
jq -c '.[]' /tmp/alarms.rendered.json | while read -r alarm; do
  echo "$alarm" > /tmp/single-alarm.json
  aws cloudwatch put-metric-alarm --cli-input-json file:///tmp/single-alarm.json --region "$AWS_REGION"
done

```

## 7. Verify end to end

```bash

aws logs tail /authservice/app --region "$AWS_REGION"
aws cloudwatch list-metrics --namespace AuthService --region "$AWS_REGION"
aws cloudwatch list-metrics --namespace CWAgent --region "$AWS_REGION"
aws cloudwatch describe-alarms --alarm-name-prefix AuthService --region "$AWS_REGION" \
  --query 'MetricAlarms[].[AlarmName,StateValue]' --output table

```

For redeploying after a code change, see docs/runbook.md.