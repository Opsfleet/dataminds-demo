


## Strands Imports



import boto3
## env variables
from dotenv import load_dotenv
import os

load_dotenv()


AWS_REGION_NAME = os.getenv("AWS_REGION_NAME")
KNOWLEDGE_BASE_ID = os.getenv("KNOWLEDGE_BASE_ID")


print(KNOWLEDGE_BASE_ID)
print(AWS_REGION_NAME)

bedrock_agent_runtime_client = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION_NAME)

response = bedrock_agent_runtime_client.retrieve(
            retrievalQuery={"text": "ARMO"}, knowledgeBaseId=KNOWLEDGE_BASE_ID)


print(response)