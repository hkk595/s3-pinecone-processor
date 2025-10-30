FROM public.ecr.aws/lambda/python:3.12

# Copy requirements.txt
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install the specified packages
RUN pip install -r requirements.txt

# Copy function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}

#ENTRYPOINT ["/lambda-entrypoint.sh"]

# Set the handler
CMD [ "lambda_function.lambda_handler" ]
