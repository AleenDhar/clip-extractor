# 🎬 Gemini Clip Extractor - Dockerized AWS Deployment

A Gradio-based application that uses Google's Gemini AI to analyze YouTube videos and extract marketing clips automatically. This project includes full Docker containerization and automated AWS deployment via GitHub Actions.

## 🚀 Features

- **AI-Powered Analysis**: Uses Gemini 2.5 Flash to identify compelling video segments
- **Automated Clip Extraction**: Downloads and creates clips using yt-dlp and ffmpeg
- **Docker Support**: Fully containerized for consistent deployment
- **AWS Integration**: Automated deployment to AWS ECS with CI/CD
- **Secure Configuration**: Environment-based API key management

## 📋 Prerequisites

- Docker and Docker Compose
- AWS CLI configured
- GitHub account for CI/CD
- Google Gemini API key

## 🏗️ Local Development

### 1. Clone and Setup
```bash
git clone <your-repo>
cd gemini_app
cp .env.example .env
# Edit .env with your actual API keys
```

### 2. Run with Docker Compose
```bash
docker-compose up --build
```

The application will be available at `http://localhost:7860`

### 3. Run without Docker
```bash
pip install -r requirements.txt
python app.py
```

## ☁️ AWS Deployment Setup

### 1. Initial AWS Infrastructure Setup
```bash
# Make the setup script executable
chmod +x aws-setup.sh

# Run the AWS setup script
./aws-setup.sh
```

This script creates:
- ECR repository for Docker images
- ECS cluster and task definitions
- VPC with public subnets
- Security groups and IAM roles
- CloudWatch log groups
- Secrets Manager for API keys

### 2. Configure Secrets

Update your Gemini API key in AWS Secrets Manager:
```bash
aws secretsmanager update-secret \
    --secret-id gemini-api-key \
    --secret-string '{"GEMINI_API_KEY":"your-actual-gemini-api-key"}'
```

### 3. GitHub Secrets Configuration

Add these secrets to your GitHub repository:
- `AWS_ACCESS_KEY_ID`: Your AWS access key
- `AWS_SECRET_ACCESS_KEY`: Your AWS secret key

Go to: Repository Settings → Secrets and variables → Actions → New repository secret

### 4. Deploy

Push your code to the `main` or `master` branch to trigger automatic deployment:
```bash
git add .
git commit -m "Initial deployment"
git push origin main
```

## 🔄 CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/deploy.yml`) automatically:

1. **Builds** Docker image on every push to main/master
2. **Pushes** image to Amazon ECR
3. **Updates** ECS task definition with new image
4. **Deploys** to ECS cluster with zero-downtime

## 📁 Project Structure

```
gemini_app/
├── app.py                 # Main Gradio application
├── Dockerfile            # Docker container configuration
├── docker-compose.yml    # Local development setup
├── requirements.txt      # Python dependencies
├── task-definition.json  # ECS task configuration
├── aws-setup.sh         # AWS infrastructure setup script
├── .github/
│   └── workflows/
│       └── deploy.yml   # CI/CD pipeline
├── .env.example         # Environment variables template
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## 🛠️ Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Google Gemini API key | Yes |
| `GRADIO_SERVER_NAME` | Server host (0.0.0.0 for Docker) | No |
| `GRADIO_SERVER_PORT` | Server port (default: 7860) | No |

### AWS Resources Created

- **ECS Cluster**: `gemini-app-cluster`
- **ECS Service**: `gemini-app-service`
- **ECR Repository**: `gemini-clip-extractor`
- **VPC**: `gemini-app-vpc`
- **Security Group**: `gemini-app-sg`
- **Secrets**: `gemini-api-key`

## 🔧 Troubleshooting

### Common Issues

1. **Docker build fails**: Ensure all dependencies are in `requirements.txt`
2. **AWS deployment fails**: Check IAM permissions and secrets configuration
3. **API key errors**: Verify Gemini API key in Secrets Manager
4. **Network issues**: Check security group rules allow port 7860

### Logs and Monitoring

- **Application logs**: CloudWatch `/ecs/gemini-app`
- **ECS service**: AWS Console → ECS → Clusters → gemini-app-cluster
- **GitHub Actions**: Repository → Actions tab

### Manual Deployment

If automatic deployment fails, you can deploy manually:
```bash
# Build and push image
docker build -t your-account.dkr.ecr.us-east-1.amazonaws.com/gemini-clip-extractor:latest .
docker push your-account.dkr.ecr.us-east-1.amazonaws.com/gemini-clip-extractor:latest

# Update ECS service
aws ecs update-service \
    --cluster gemini-app-cluster \
    --service gemini-app-service \
    --force-new-deployment
```

## 🔒 Security Best Practices

- ✅ API keys stored in AWS Secrets Manager
- ✅ Environment variables for configuration
- ✅ IAM roles with minimal permissions
- ✅ VPC with security groups
- ✅ Container health checks
- ✅ Encrypted secrets in GitHub

## 📊 Monitoring and Scaling

The deployment includes:
- Health checks for container monitoring
- CloudWatch logging for debugging
- Auto-scaling capabilities via ECS
- Load balancer ready configuration

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally with Docker
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

---

**Need help?** Check the troubleshooting section or create an issue in the repository.
