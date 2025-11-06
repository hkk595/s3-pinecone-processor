#!/bin/bash

# Configuration
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="986822852724"
REPO_NAME="lambda-s3-processor"
IMAGE_TAG="v0.10"
LAMBDA_FUNCTION_NAME="doc-pinecone-handler"

# Your Pinecone credentials
# PINECONE_API_KEY=""
# PINECONE_INDEX_NAME="company-doc"
# OPENAI_API_KEY=""

echo "Building and pushing Docker image..."
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# docker buildx build \
#     --platform linux/amd64 \
#     -t ${REPO_NAME}:${IMAGE_TAG} \
#     .

docker build -t ${REPO_NAME}:${IMAGE_TAG} .

docker tag ${REPO_NAME}:${IMAGE_TAG} \
    ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}:${IMAGE_TAG}

docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}:${IMAGE_TAG}

#echo "Updating Lambda function..."
#aws lambda update-function-code \
#    --function-name ${LAMBDA_FUNCTION_NAME} \
#    --image-uri ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}:${IMAGE_TAG}
#
#echo "Waiting for update..."
#aws lambda wait function-updated --function-name ${LAMBDA_FUNCTION_NAME}
#
#echo "Setting environment variables..."
#aws lambda update-function-configuration \
#    --function-name ${LAMBDA_FUNCTION_NAME} \
#    --environment "Variables={PINECONE_API_KEY=${PINECONE_API_KEY},PINECONE_INDEX_NAME=${PINECONE_INDEX_NAME},OPENAI_API_KEY=${OPENAI_API_KEY}}" \
#    --timeout 300 \
#    --memory-size 1024
#
#echo "Done!"
