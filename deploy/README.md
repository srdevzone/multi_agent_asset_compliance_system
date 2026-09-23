# Deployment Configurations

This folder contains the configuration files required to deploy the Asset Compliance AI microservice. You can choose the deployment strategy that best fits your enterprise infrastructure.

## Option 1: Docker / Single EC2 Server (Recommended for traditional servers)

Located in `deploy/docker-ec2/`

Use this if you want to run the system continuously on a standard virtual machine (like AWS EC2, DigitalOcean Droplet, etc.).

**How to deploy:**
1. Ensure Docker and Docker Compose are installed on your server.
2. Clone this repository to your server.
3. Ensure your `.env` file is present in the root of the project.
4. From the root of the project, run:
   ```bash
   docker-compose -f deploy/docker-ec2/docker-compose.yml up -d --build
   ```

## Option 2: AWS Serverless Application Model (SAM)

Located in `deploy/aws-sam/`

Use this if you want to deploy the system as a truly serverless AWS Lambda microservice. This is highly scalable and cost-effective if you have sparse usage.

**Prerequisites:**
- AWS CLI installed and configured
- AWS SAM CLI installed
- SSM parameters configured (see SSM Bootstrap step below)

**How to deploy:**

1. **Bootstrap SSM Parameters** (first-time setup only):
   
   The Lambda functions read secrets from AWS Systems Manager Parameter Store. Before deploying, you must create these parameters:
   
   ```bash
   # Run the SSM bootstrap script from the project root
   make ssm-bootstrap
   ```
   
   Or manually create the required parameters in SSM Parameter Store:
   - `/asset-compliance/{env}/pinecone_api_key`
   - `/asset-compliance/{env}/openai_api_key`
   - `/asset-compliance/{env}/anthropic_api_key`
   - `/asset-compliance/{env}/image_agent_provider`
   - `/asset-compliance/{env}/image_agent_model`
   - (and other agent provider/model parameters)
   
   See `infra/ssm_bootstrap.sh` for the full list of required parameters.

2. **Build the SAM application:**
   ```bash
   sam build --template-file deploy/aws-sam/template.yaml --use-container
   ```

3. **Deploy the application:**
   ```bash
   sam deploy --config-file deploy/aws-sam/samconfig.toml --config-env default
   ```
