#!/bin/bash

# --- VARIABLES CONFIGURATION ---

# AWS
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID=""
REPO_NAME="lambda-s3-processor"
IMAGE_TAG="v0.10"
LAMBDA_FUNCTION_NAME="doc-pinecone-handler"

# Construct the full ECR repository URI
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_REPO_URI="${ECR_REGISTRY}/${REPO_NAME}"

# OpenAI
OPENAI_API_KEY=""

# Pinecone
PINECONE_API_KEY=""
PINECONE_INDEX_NAME="company-doc"

# Docker
PLATFORM="linux/amd64"

# --- END OF CONFIGURATION ---

echo "1. Logging in to AWS ECR at ${ECR_REGISTRY}..."
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin ${ECR_REGISTRY}
echo "Login Succeeded."

echo "2. Building the Docker image for platform ${PLATFORM}..."
#docker buildx build --platform ${PLATFORM} -t ${REPO_NAME}:${IMAGE_TAG} .
docker build --platform ${PLATFORM} -t ${REPO_NAME}:${IMAGE_TAG} .
echo "Build complete."

echo "3. Tagging the image for ECR as ${ECR_REPO_URI}:${IMAGE_TAG}..."
docker tag ${REPO_NAME}:${IMAGE_TAG} ${ECR_REPO_URI}:${IMAGE_TAG}
echo "Tagging complete."

echo "4. Pushing the image to ECR..."
docker push ${ECR_REPO_URI}:${IMAGE_TAG}
echo "Successfully pushed ${ECR_REPO_URI}:${IMAGE_TAG}"

echo "5. Updating Lambda function..."
aws lambda update-function-code \
    --function-name ${LAMBDA_FUNCTION_NAME} \
    --image-uri ${ECR_REPO_URI}:${IMAGE_TAG}

echo "Waiting for update..."
aws lambda wait function-updated --function-name ${LAMBDA_FUNCTION_NAME}

echo "Setting environment variables..."
aws lambda update-function-configuration \
    --function-name ${LAMBDA_FUNCTION_NAME} \
    --environment "Variables={PINECONE_API_KEY=${PINECONE_API_KEY},PINECONE_INDEX_NAME=${PINECONE_INDEX_NAME},OPENAI_API_KEY=${OPENAI_API_KEY}}" \
    --timeout 300 \
    --memory-size 1024

echo "Lambda function update complete."
