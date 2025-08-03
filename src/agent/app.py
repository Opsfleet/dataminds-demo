


## Strands Imports
from strands import Agent, tool 
from strands.models import BedrockModel
from strands_tools import retrieve
from strands.session.file_session_manager import FileSessionManager
from strands.agent.conversation_manager import SlidingWindowConversationManager
from mcp import stdio_client, StdioServerParameters
from strands.tools.mcp import MCPClient
## aws imports
import boto3

## api imports
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse 
from pydantic import BaseModel, Field
from typing import Optional, Dict, List,Any
from uuid import UUID
import json

## additional imports
import time,logging
import signal

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



## env variables
from dotenv import load_dotenv
import os

load_dotenv()

MODEL_ID = os.getenv("MODEL_ID")
AWS_REGION = os.getenv("AWS_REGION")
KNOWLEDGE_BASE_ID = os.getenv("KNOWLEDGE_BASE_ID")


## SETTING UP CONFIGS
model_temperature = 0.2
system_prompt_path = 'src/agent/prompts/system_prompt.md'
session_id="test_3",
session_storage_dir="sessions/admin" 

# restricted list of mcp tools to use for demo purposes. some tools such as delete_page has been excluded.
mcp_enabled_tools='confluence_search,confluence_get_page,confluence_get_page_children,confluence_get_comments,confluence_create_page,confluence_update_page'

## STRANDS AGENT INITIATION

## SET UP LLM 
bedrock_model = BedrockModel(
        model_id=MODEL_ID,
        region_name=AWS_REGION,
        temperature=model_temperature
    )

## SET UP SYSTEM PROMPT
with open(system_prompt_path,'r',encoding='utf-8') as sys_f:
    system_prompt = sys_f.read()

## SETUP TOOLS

## SETUP KNOWLEDGE BASE RETRIEVE TOOL
tools = [retrieve]


## SETUP CONFLUENCE MCP TOOLS 


# Comment out this part if you do not want to use Confluence MCP  


CONFLUENCE_URL =os.getenv('CONFLUENCE_URL')

CONFLUENCE_USERNAME = os.getenv('CONFLUENCE_USERNAME')
CONFLUENCE_TOKEN = os.getenv('CONFLUENCE_TOKEN')
CONFLUENCE_SPACE_KEY = os.getenv('CONFLUENCE_SPACE_KEY')


confluence_mcp_client = MCPClient(lambda: stdio_client(
    StdioServerParameters(
        command="uvx",
        args=[
            "mcp-atlassian",
            f"--confluence-url={CONFLUENCE_URL}",
            f"--confluence-username={CONFLUENCE_USERNAME}",
            f"--confluence-token={CONFLUENCE_TOKEN}",
            f"--confluence-spaces-filter={CONFLUENCE_SPACE_KEY}",
            f"--enabled-tools={mcp_enabled_tools}"
        ]
    )
))

confluence_mcp_client.__enter__()
confluence_mcp_tools = confluence_mcp_client.list_tools_sync()
tools = tools + [confluence_mcp_tools]

# confluence mcp integration ends here.

## SET UP SESSION MANAGER FOR PERSISTING CONVERSATION HISTORY
session_manager = FileSessionManager(
    session_id=session_id,
    storage_dir=session_storage_dir
)

## SET UP CONVERSATION MANAGER FOR MANAGING CONVERSATION ON RUNTIME
conversation_manager = SlidingWindowConversationManager(
    window_size=30,  # Maximum number of messages to keep
    should_truncate_results=True, # Enable truncating the tool result when a message is too large for the model's context window 
)

## INITIALIZING STRANDS AGENT
agent = Agent(
    model=bedrock_model,
    system_prompt=system_prompt,
    # session_manager=session_manager,
    conversation_manager=conversation_manager,
    callback_handler= None,
    tools = tools
            )


### FASTAPI PART
app = FastAPI(
    title="DEMO AGENT API",
    description="DEMO AGENT API WITH ACCESS TO BEDROCK KNOWLEDGE BASE AND CONFLUENCE MCP USING CLAUDE SONNET 4",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

## INPUT STRUCTURE OF CHAT METHOD
class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    query: str = Field(..., description="User's question/message", min_length=1)
    session_id: str = Field(default="test", description="Session identifier")



## OUTPUT RESPONSE SERIALIZATION FOR STREAMING CHAT ENDPOINT
class SSEMessageData(BaseModel):
    event_loop_cycle_id: str
    message: str
    

class SSEToolData(BaseModel):
    event_loop_cycle_id: str
    tool_name: str
    toolUseId: str
    tool_input: Dict = Field(default_factory=lambda: {'state': 'in-progress'})

    

class SSEMessageEvent(BaseModel):
    event: str
    data: SSEMessageData
    
    def serialize(self):
        return f"event: {self.event}\ndata: {json.dumps(self.data.dict())}\n\n"

class SSEToolEvent(BaseModel):
    event: str
    data: SSEToolData
    
    def serialize(self):
        return f"event: {self.event}\ndata: {json.dumps(self.data.dict())}\n\n"


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "agent_initialized": agent is not None,
        "message": "Strands Agent is running."
    }





@app.post("/stream_chat") 

async def chat_endpoint(request: ChatRequest): 
    message = request.query
    session_id = request.session_id
    """
    Chat with the context-managed agent.
    
    The agent maintains separate conversation contexts for each user and session,
    with intelligent summarization when context windows fill up.
    
    Both user_id and session_id are required in the request.

    this is a streaming endpoint
    """
    async def stream_response(): 

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Agent not initialized"
            )
        
       
        logger.info(f"Processing chat request for session: {session_id}")
        logger.info(f"Using agent for processing")

        async for event in agent.stream_async(message): 
            
            if "data" in event: 
                sse_event = SSEMessageEvent(
                    event="message", 
                    data = SSEMessageData(
                    event_loop_cycle_id = str(event['event_loop_cycle_id']),
                    message=event['data']
                ))
                yield sse_event.serialize()
                
            elif "current_tool_use" in event: 
                tool_input_str = event['current_tool_use']['input']
                logger.info(f"tool_input_str = {tool_input_str}")
                
                try:
                    # Use json.loads() to parse JSON string to dictionary
                    tool_input_dict = json.loads(tool_input_str)
                    tool_input_dict['state'] = 'done'
                except Exception as e:
                    # logger.error(f"Could not convert string || {tool_input_str} || to json.\n Error: {e}")
                    tool_input_dict = {'state': 'in-progress'}

                sse_event = SSEToolEvent    (
                    event = "tool",
                    data = SSEToolData(
                    event_loop_cycle_id= str(event['event_loop_cycle_id']),
                    tool_name = event['current_tool_use']['name'],
                    toolUseId = event['current_tool_use']['toolUseId'],
                    tool_input = tool_input_dict
                    
                                        )     
                                            )
                yield sse_event.serialize()

    return StreamingResponse(stream_response(), media_type="text/event-stream") 



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    ) 

