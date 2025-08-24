#!/bin/bash

# EC2 Deployment Script
# Run this script on your EC2 instance to set up the application

set -e

echo "🚀 Setting up Gemini Clip Extractor on EC2..."

# Update system
echo "📦 Updating system packages..."
sudo yum update -y

# Install Git if not present
if ! command -v git &> /dev/null; then
    echo "📥 Installing Git..."
    sudo yum install -y git
fi

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "🐳 Installing Docker..."
    sudo yum install -y docker
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -a -G docker $USER
    echo "⚠️  Please logout and login again for Docker permissions to take effect"
fi

# Install Docker Compose if not present
if ! command -v docker-compose &> /dev/null; then
    echo "🔧 Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.21.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Create application directory
APP_DIR="$HOME/gemini-app"
mkdir -p $APP_DIR
cd $APP_DIR

echo "📁 Application directory: $APP_DIR"

# Clone repository (you'll need to replace with your actual repo URL)
REPO_URL="https://github.com/YOUR_USERNAME/gemini-clip-extractor.git"
echo "📥 Cloning repository..."
if [ -d ".git" ]; then
    git pull origin main
else
    git clone $REPO_URL .
fi

# Create .env file
echo "🔐 Creating environment configuration..."
cat > .env << EOF
GEMINI_API_KEY=your_gemini_api_key_here
GRADIO_SERVER_NAME=0.0.0.0
GRADIO_SERVER_PORT=7860
EOF

echo "⚠️  IMPORTANT: Edit .env file with your actual Gemini API key:"
echo "   nano .env"
echo ""

# Create systemd service for auto-start
echo "🔄 Creating systemd service..."
sudo tee /etc/systemd/system/gemini-app.service > /dev/null << EOF
[Unit]
Description=Gemini Clip Extractor
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable the service
sudo systemctl daemon-reload
sudo systemctl enable gemini-app.service

echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Edit the .env file with your Gemini API key:"
echo "   nano .env"
echo ""
echo "2. Update the repository URL in this script:"
echo "   nano deploy-ec2.sh"
echo ""
echo "3. Start the application:"
echo "   docker-compose up -d"
echo ""
echo "4. Check if it's running:"
echo "   docker ps"
echo ""
echo "5. Access your app at: http://$(curl -s ifconfig.me):7860"
echo ""
echo "🔄 To auto-start on boot:"
echo "   sudo systemctl start gemini-app"
