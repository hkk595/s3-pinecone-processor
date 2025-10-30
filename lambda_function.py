import json
import boto3
import os
from io import BytesIO

# Add try-except for imports
try:
    from openai import OpenAI
    from pinecone import Pinecone
    from docx import Document
    from pypdf import PdfReader
    print("All imports successful!")
except Exception as e:
    print(f"Import error: {e}")
    raise

# Initialize AWS client
s3_client = boto3.client('s3')

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Initialize Pinecone client
pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
pc_index = pc.Index(os.getenv('PINECONE_INDEX_NAME'))
pc_namespace = os.getenv('PINECONE_NAMESPACE', '__default__')


def extract_text_from_txt(file_content):
    """Extract text from .txt or .md files"""
    try:
        return file_content.decode('utf-8')
    except UnicodeDecodeError:
        return file_content.decode('latin-1')


def extract_text_from_docx(file_content):
    """Extract text from .docx files"""
    doc = Document(BytesIO(file_content))
    text_parts = []

    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            text_parts.append(paragraph.text)

    return '\n'.join(text_parts)


def extract_text_from_pdf(file_content):
    """Extract text from .pdf files"""
    pdf_reader = PdfReader(BytesIO(file_content))
    text_parts = []

    for page in pdf_reader.pages:
        text = page.extract_text()
        if text.strip():
            text_parts.append(text)

    return '\n'.join(text_parts)


def extract_text(file_content, file_extension):
    """Extract text based on file extension"""
    extractors = {
        '.txt': extract_text_from_txt,
        '.md': extract_text_from_txt,
        '.docx': extract_text_from_docx,
        '.pdf': extract_text_from_pdf
    }

    extractor = extractors.get(file_extension.lower())
    if not extractor:
        raise ValueError(f"Unsupported file type: {file_extension}")

    return extractor(file_content)


def chunk_text(text, chunk_size=1000, overlap=200):
    """Split text into chunks with overlap"""
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size
        chunk = text[start:end]

        if chunk.strip():
            chunks.append(chunk)

        start += chunk_size - overlap

    return chunks


def get_embedding(text):
    """Get embedding from OpenAI"""
    response = openai_client.embeddings.create(
        input=text,
        model="text-embedding-3-large",  # or text-embedding-3-small,
        dimensions=1024
    )
    return response.data[0].embedding


def lambda_handler(event, context):
    print(f"Received {len(event['Records'])} messages from SQS")

    processed_count = 0

    for sqs_record in event['Records']:
        s3_event = json.loads(sqs_record['body'])

        for s3_record in s3_event['Records']:
            bucket_name = s3_record['s3']['bucket']['name']
            object_key = s3_record['s3']['object']['key']

            print(f"Processing file: s3://{bucket_name}/{object_key}")

            try:
                # Get file extension
                file_extension = os.path.splitext(object_key)[1]

                if file_extension.lower() not in ['.txt', '.md', '.docx', '.pdf']:
                    print(f"Skipping unsupported file type: {file_extension}")
                    continue

                # Read file from S3
                response = s3_client.get_object(
                    Bucket=bucket_name,
                    Key=object_key
                )

                file_content = response['Body'].read()
                print(f"File size: {len(file_content)} bytes")

                # Extract text
                print(f"Extracting text from {file_extension} file...")
                text = extract_text(file_content, file_extension)
                print(f"Extracted text length: {len(text)} characters")
                print(f"Preview: {text[:200]}...")

                # Chunk text
                chunks = chunk_text(text, chunk_size=1000, overlap=200)
                print(f"Split into {len(chunks)} chunks")

                # Prepare vectors for Pinecone
                vectors = []
                for i, chunk in enumerate(chunks):
                    vector_id = f"{object_key}_chunk_{i}"

                    # Create an embedding
                    embedding = get_embedding(chunk)

                    vectors.append({
                        'id': vector_id,
                        'values': embedding,
                        'metadata': {
                            'source': f"s3://{bucket_name}/{object_key}",
                            'chunk_index': i,
                            'text': chunk[:1000],  # Store first 1000 chars in metadata
                            'file_type': file_extension,
                            'total_chunks': len(chunks)
                        }
                    })

                # Upsert to Pinecone
                print(f"Uploading {len(vectors)} vectors to Pinecone...")
                pc_index.upsert(vectors=vectors)
                print(f"Successfully uploaded to Pinecone!")

                processed_count += 1

            except Exception as e:
                print(f"Error processing file {object_key}: {str(e)}")
                import traceback
                traceback.print_exc()
                raise

    return {
        'statusCode': 200,
        'body': json.dumps(f'Successfully processed {processed_count} files')
    }
