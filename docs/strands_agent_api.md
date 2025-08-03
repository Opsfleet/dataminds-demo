# Strands Agent API Documentation

## 1. Strands Agent

### Introduction

This API is built using the [Strands Agents Framework](https://strandsagents.com/latest/), an open source SDK that takes a model-driven approach to building and running AI agents in just a few lines of code.

**What is Strands Agents?**

Strands Agents is an open source SDK developed by AWS that simplifies agent development by embracing the capabilities of state-of-the-art models to plan, chain thoughts, call tools, and reflect. Unlike frameworks that require developers to define complex workflows, Strands allows developers to simply define a prompt and a list of tools in code to build an agent.

**Core Philosophy:**

Like the two strands of DNA, Strands connects two core pieces of the agent together: the model and the tools. The framework uses the advanced reasoning capabilities of models to plan the agent's next steps and execute tools automatically.

**Key Capabilities:**

- **Model-driven approach**: Leverages advanced model reasoning for planning and tool execution
- **Production proven**: Used by multiple AWS teams including Amazon Q Developer, AWS Glue, and VPC Reachability Analyzer
- **Scales from simple to complex**: From local development to production deployment
- **Model agnostic**: Supports models from Amazon Bedrock, Anthropic, Ollama, Meta, and other providers through LiteLLM
- **Highly customizable**: Customize tool selection, context management, session state storage, and build multi-agent applications

The framework excels at handling tool capabilities, conversation management, session persistence, and provides seamless integration with various model providers, making it ideal for enterprise-grade AI applications.


### Implementation of Stands Agent in this repo:

### A. Bedrock Model

The agent uses AWS Bedrock models for language processing capabilities.

```python
from strands.models import BedrockModel

# Initialize Bedrock model
bedrock_model = BedrockModel(
    model_id=MODEL_ID,
    region_name=AWS_REGION,
    temperature=model_temperature
)
```

### B. System Prompt

The system prompt defines the agent's behavior and capabilities.

```python
# Read and initialize system prompt
system_prompt_path = 'src/agent/prompts/system_prompt.md'
with open(system_prompt_path, 'r', encoding='utf-8') as sys_f:
    system_prompt = sys_f.read()
```

### C. Session Manager

Session manager handles conversation persistence across interactions.

```python
from strands.session.file_session_manager import FileSessionManager

# Initialize session manager
session_manager = FileSessionManager(
    session_id=session_id,
    storage_dir=session_storage_dir
)
```

### D. Conversation Manager

Conversation manager handles runtime conversation flow and context management.

```python
from strands.agent.conversation_manager import SlidingWindowConversationManager

# Initialize conversation manager
conversation_manager = SlidingWindowConversationManager(
    window_size=30,  # Maximum number of messages to keep
    should_truncate_results=True  # Enable truncating tool results when too large
)
```

### E. Tools

Tools provide the agent with external capabilities like knowledge base retrieval.

```python
from strands_tools import retrieve

# Initialize tools
tools = [retrieve]
```

### F. Putting It All Together

Final agent initialization combining all components.

```python
from strands import Agent

# Initialize the complete agent
agent = Agent(
    model=bedrock_model,
    system_prompt=system_prompt,
    conversation_manager=conversation_manager,
    callback_handler=None,
    tools=tools
)
```

---------------------------------


## 2. FastAPI

### 1. Health Method

Simple health check endpoint to verify agent status.

```python
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "agent_initialized": agent is not None,
        "message": "Strands Agent is running."
    }
```

### 2. Stream Chat Method

The main chat endpoint using Server-Sent Events (SSE) for real-time streaming.

**What is SSE?**
Server-Sent Events (SSE) is a web standard that allows a server to push data to a client in real-time. Unlike WebSockets, SSE is unidirectional (server to client) and works over HTTP, making it perfect for streaming agent responses.

**How it works:**
- Client sends a POST request with a chat message
- Server opens an SSE stream and processes the message through the agent
- Agent responses and tool usage are streamed back in real-time
- Each event contains structured data about messages or tool execution

### 3. Agent Stream and SSE Serialization

The core streaming logic that processes agent responses and serializes them for SSE delivery.

```python
@app.post("/stream_chat")
async def chat_endpoint(request: ChatRequest):
    async def stream_response():
        # Stream agent responses
        async for event in agent.stream_async(message):
            
            # Handle message events
            if "data" in event:
                sse_event = SSEMessageEvent(
                    event="message",
                    data=SSEMessageData(
                        event_loop_cycle_id=str(event['event_loop_cycle_id']),
                        message=event['data']
                    )
                )
                yield sse_event.serialize()
            
            # Handle tool usage events
            elif "current_tool_use" in event:
                tool_input_str = event['current_tool_use']['input']
                
                try:
                    tool_input_dict = json.loads(tool_input_str)
                    tool_input_dict['state'] = 'done'
                except Exception:
                    tool_input_dict = {'state': 'in-progress'}
                
                sse_event = SSEToolEvent(
                    event="tool",
                    data=SSEToolData(
                        event_loop_cycle_id=str(event['event_loop_cycle_id']),
                        tool_name=event['current_tool_use']['name'],
                        toolUseId=event['current_tool_use']['toolUseId'],
                        tool_input=tool_input_dict
                    )
                )
                yield sse_event.serialize()
    
    return StreamingResponse(stream_response(), media_type="text/event-stream")
```

The SSE serialization ensures that both message content and tool execution details are properly formatted and streamed to the client in real-time, providing full transparency into the agent's processing workflow.