import json
import boto3
import os
from io import BytesIO
import time

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

    # print full event for debugging
    # print(f"Full event: {json.dumps(event, indent=2)}")

    # Check remaining time
    print(f"Lambda timeout: {context.get_remaining_time_in_millis() / 1000} seconds remaining")
    processed_count = 0

    for idx, sqs_record in enumerate(event['Records']):
        print(f"\n--- Processing SQS record {idx + 1}/{len(event['Records'])} ---")

        s3_event = json.loads(sqs_record['body'])

        for s3_record in s3_event['Records']:
            bucket_name = s3_record['s3']['bucket']['name']
            object_key = s3_record['s3']['object']['key']
            event_name = s3_record.get('eventName', 'Unknown')

            print(f"Event: {event_name}")
            print(f"File: s3://{bucket_name}/{object_key}")

            # Skip delete events
            if 'Delete' in event_name:
                print(f"Skipping delete event")
                continue

            print(f"Processing file: s3://{bucket_name}/{object_key}")

            try:
                # Get file extension
                file_extension = os.path.splitext(object_key)[1]

                # Skip unsupported file types
                if file_extension.lower() not in ['.txt', '.md', '.docx', '.pdf']:
                    print(f"Skipping unsupported file type: {file_extension}")
                    continue

                # Skip folders
                if object_key.endswith('/'):
                    print(f"Skipping folder")
                    continue

                # Read file from S3
                print(f"Reading from S3...")
                response = s3_client.get_object(
                    Bucket=bucket_name,
                    Key=object_key
                )

                file_content = response['Body'].read()
                # print(f"File size: {len(file_content)} bytes")
                print(f"** Read {len(file_content)} bytes")

                # Skip empty files
                if len(file_content) == 0:
                    print(f"Skipping empty file")
                    continue

                # Extract text
                print(f"Extracting text from {file_extension} file...")
                text = extract_text(file_content, file_extension)
                print(f"** Extracted {len(text)} characters")
                print(f"Preview: {text[:200]}...")

                if not text or len(text.strip()) == 0:
                    print(f"No text extracted, skipping")
                    continue

                # Chunk text
                print(f"Chunking text...")
                chunks = chunk_text(text, chunk_size=1000, overlap=200)
                print(f"** Created {len(chunks)} chunks")

                # Prepare vectors for Pinecone
                print(f"Preparing vectors...")
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

                print(f"✓ Prepared {len(vectors)} vectors")

                # Upsert to Pinecone
                print(f"Uploading {len(vectors)} vectors to Pinecone...")
                try:
                    pc_index.upsert(vectors=vectors)

                    print(f"** Uploaded to Pinecone")
                except Exception as pinecone_error:
                    print(f"ERROR uploading to Pinecone: {str(pinecone_error)}")
                    import traceback
                    traceback.print_exc()
                    raise

                processed_count += 1

            except Exception as e:
                print(f"Error processing file {object_key}: {str(e)}")
                import traceback
                traceback.print_exc()
                raise

            print(f"** Record processed")

        print(f"\n=== Lambda completed ===")

    return {
        'statusCode': 200,
        'body': json.dumps(f'Successfully processed {processed_count} files')
    }
