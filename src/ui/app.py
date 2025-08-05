import streamlit as st
import json
import requests
from typing import Dict, List, Any, Generator
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
import os

os.environ['STREAMLIT_SERVER_REQUEST_TIMEOUT'] = '120'


# Page configuration
st.set_page_config(
    page_title="Agent Chat Interface",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for minimal styling
st.markdown("""
<style>
    .main > div {
        padding-top: 2rem;
    }
    .stTextInput > div > div > input {
        background-color: #f8f9fa;
        border-radius: 0.5rem;
    }
    .chat-message {
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0.5rem;
        background-color: #f8f9fa;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .tool-box {
        padding: 0.8rem;
        margin: 0.3rem 0;
        border-radius: 0.3rem;
        border-left: 4px solid #007bff;
        background-color: #e3f2fd;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }
    .tool-progress {
        display: inline-block;
        margin-left: 0.5rem;
    }
    .conversation-container {
        max-height: 70vh;
        overflow-y: auto;
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #fafafa;
    }
    .loading-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(255, 255, 255, 0.8);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 9999;
        backdrop-filter: blur(2px);
    }
    .loading-content {
        background: white;
        padding: 2rem;
        border-radius: 1rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        text-align: center;
        min-width: 200px;
    }
    .spinner {
        border: 4px solid #f3f3f3;
        border-top: 4px solid #007bff;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        animation: spin 1s linear infinite;
        margin: 0 auto 1rem auto;
    }
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
</style>
""", unsafe_allow_html=True)

def initialize_session_state():
    """Initialize session state variables for conversation management"""
    if 'conversation_history' not in st.session_state:
        st.session_state.conversation_history = []
    if 'messages' not in st.session_state:
        st.session_state.messages = {}  # event_loop_cycle_id -> message_text
    if 'tools' not in st.session_state:
        st.session_state.tools = {}  # toolUseId -> tool_state
    if 'message_order' not in st.session_state:
        st.session_state.message_order = []  # ordered event_loop_cycle_ids
    if 'conversation_elements' not in st.session_state:
        st.session_state.conversation_elements = []  # ordered list of messages and tools
    if 'connection_status' not in st.session_state:
        st.session_state.connection_status = 'disconnected'
    if 'last_error' not in st.session_state:
        st.session_state.last_error = None
    if 'streaming_active' not in st.session_state:
        st.session_state.streaming_active = False

def add_conversation_element(element_type: str, element_id: str, position: int = None):
    """Add element to conversation flow in chronological order"""
    # Use high precision timestamp to avoid collisions
    timestamp = time.time_ns() / 1_000_000_000  # Convert nanoseconds to seconds with decimal precision
    
    element = {
        'type': element_type,  # 'message' or 'tool'
        'id': element_id,      # event_loop_cycle_id or toolUseId
        'timestamp': timestamp
    }
    
    if position is not None:
        st.session_state.conversation_elements.insert(position, element)
    else:
        st.session_state.conversation_elements.append(element)

def get_conversation_flow():
    """Get ordered conversation elements for display"""
    flow = []
    
    # Process conversation elements in chronological order
    for element in st.session_state.conversation_elements:
        if element['type'] == 'message':
            cycle_id = element['id']
            if cycle_id in st.session_state.messages:
                flow.append({
                    'type': 'message',
                    'cycle_id': cycle_id,
                    'content': st.session_state.messages[cycle_id],
                    'timestamp': element['timestamp']
                })
        elif element['type'] == 'tool':
            tool_id = element['id']
            if tool_id in st.session_state.tools:
                flow.append({
                    'type': 'tool',
                    'tool_data': st.session_state.tools[tool_id],
                    'timestamp': element['timestamp']
                })
    
    return flow

def main():
    """Main application function"""
    st.title("🤖 Agent Chat Interface")
    
    # Initialize session state
    initialize_session_state()
    
    # Display connection status at top
    display_connection_status()
    
    # Create conversation container with fixed height
    conversation_container = st.container()
    
    with conversation_container:
        st.markdown("---")
        display_conversation()
    
    # Chat input at bottom - fixed position
    st.markdown("---")
    with st.container():
        user_input = st.text_area(
            "Ask the agent anything...",
            placeholder="Type your message here...\nUse Enter for new lines, click Send to submit",
            key="user_input",
            height=100,
            max_chars=2000
        )
        
        col1, col2 = st.columns([1, 4])
        with col1:
            send_button = st.button("Send", type="primary")
        
        # Only send when Send button is clicked
        if send_button and user_input and user_input.strip():
            handle_user_input(user_input.strip())
            st.rerun()

def handle_user_input(user_input: str):
    """Handle user input and initiate chat with agent"""
    # Add user message to conversation
    st.session_state.conversation_history.append({
        'type': 'user',
        'content': user_input,
        'timestamp': time.time()
    })
    
    # Note: Input will be cleared automatically on rerun
    
    # Show loading state
    st.session_state.conversation_history.append({
        'type': 'loading',
        'content': 'Invoking agent...',
        'timestamp': time.time()
    })
    
    # Start streaming response in background
    st.session_state.streaming_active = True
    try:
        update_connection_status('connecting')
        stream_agent_response(user_input)
        update_connection_status('connected')
    except Exception as e:
        handle_connection_error(e)
    finally:
        st.session_state.streaming_active = False

def stream_agent_response(user_input: str):
    """Stream response from the agent's /stream_chat endpoint"""
    # Prepare request payload
    payload = {
        "query": user_input,
        "session_id": "streamlit_session"
    }
    
    # Make streaming request to agent
    try:
        response = requests.post(
            "http://localhost:8000/stream_chat",
            json=payload,
            stream=True,
            headers={"Accept": "text/event-stream"},
            timeout=30
        )
        response.raise_for_status()
        
        # Create placeholder for real-time updates
        streaming_placeholder = st.empty()
        
        # Process streaming response with periodic UI updates
        event_count = 0
        first_event_received = False
        
        for event_data in parse_sse_stream(response):
            # Remove loading state only when first event arrives
            if not first_event_received:
                if st.session_state.conversation_history and st.session_state.conversation_history[-1]['type'] == 'loading':
                    st.session_state.conversation_history.pop()
                first_event_received = True
            
            process_sse_event(event_data)
            event_count += 1
            
            # Update UI every few events for better performance
            if event_count % 3 == 0:
                with streaming_placeholder.container():
                    display_streaming_updates()
        
        # Final update to show complete response
        streaming_placeholder.empty()
            
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error: {e}")
        raise e

def display_streaming_updates():
    """Display current streaming state for real-time updates"""
    # Show only the latest streaming content to avoid duplicates
    conversation_flow = get_conversation_flow()
    
    # Show only the most recent elements that are actively being updated
    recent_elements = conversation_flow[-2:] if conversation_flow else []
    
    for element in recent_elements:
        if element['type'] == 'message':
            display_message_block(element['cycle_id'], element['content'])
        elif element['type'] == 'tool':
            display_tool_box(element['tool_data'])

def parse_sse_stream(response) -> Generator[Dict[str, Any], None, None]:
    """Parse Server-Sent Events stream"""
    buffer = ""
    
    for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
        if chunk:
            buffer += chunk
            
            # Process complete events (separated by double newlines)
            while "\n\n" in buffer:
                event_block, buffer = buffer.split("\n\n", 1)
                
                if event_block.strip():
                    event_data = parse_sse_event(event_block)
                    if event_data:
                        yield event_data

def parse_sse_event(event_block: str) -> Dict[str, Any]:
    """Parse individual SSE event block"""
    try:
        lines = event_block.strip().split('\n')
        event_type = None
        data = None
        
        for line in lines:
            if line.startswith('event: '):
                event_type = line[7:].strip()
            elif line.startswith('data: '):
                data_str = line[6:].strip()
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError as e:
                    logging.error(f"JSON decode error: {e}, data: {data_str}")
                    return None
        
        if event_type and data:
            return {
                'event': event_type,
                'data': data
            }
            
    except Exception as e:
        logging.error(f"Error parsing SSE event: {e}")
        return None
    
    return None

def process_sse_event(event_data: Dict[str, Any]):
    """Process parsed SSE event and update UI state"""
    try:
        event_type = event_data['event']
        data = event_data['data']
        
        if event_type == 'message':
            process_message_event(data)
        elif event_type == 'tool':
            process_tool_event(data)
        else:
            logging.warning(f"Unknown event type: {event_type}")
            
    except Exception as e:
        logging.error(f"Error processing SSE event: {e}")

def process_message_event(data: Dict[str, Any]):
    """Process message event and update conversation state"""
    try:
        event_loop_cycle_id = data['event_loop_cycle_id']
        message_chunk = data['message']
        
        # Initialize message block if new cycle
        if event_loop_cycle_id not in st.session_state.messages:
            st.session_state.messages[event_loop_cycle_id] = ""
            st.session_state.message_order.append(event_loop_cycle_id)
            # Add to conversation flow
            add_conversation_element('message', event_loop_cycle_id)
        
        # Append message chunk
        st.session_state.messages[event_loop_cycle_id] += message_chunk
        
    except Exception as e:
        logging.error(f"Error processing message event: {e}")

def process_tool_event(data: Dict[str, Any]):
    """Process tool event and update tool state"""
    try:
        event_loop_cycle_id = data['event_loop_cycle_id']
        tool_name = data['tool_name']
        tool_use_id = data['toolUseId']
        tool_input = data['tool_input']
        
        # Add to conversation flow if new tool
        if tool_use_id not in st.session_state.tools:
            add_conversation_element('tool', tool_use_id)
        
        # Initialize or update tool state
        st.session_state.tools[tool_use_id] = {
            'event_loop_cycle_id': event_loop_cycle_id,
            'tool_name': tool_name,
            'toolUseId': tool_use_id,
            'tool_input': tool_input,
            'state': tool_input.get('state', 'unknown')
        }
        
    except Exception as e:
        logging.error(f"Error processing tool event: {e}")

def display_conversation():
    """Display the conversation history in chronological order"""
    # Get all conversation elements in chronological order
    all_elements = get_chronological_conversation()
    
    if not all_elements:
        st.info("Start a conversation by typing a message below.")
        return
    
    # Display all elements in chronological order
    for element in all_elements:
        if element['type'] == 'user':
            display_user_message(element['content'])
        elif element['type'] == 'loading':
            display_loading_overlay(element['content'])
        elif element['type'] == 'error':
            display_error_message(element['content'])
        elif element['type'] == 'agent_message':
            display_message_block(element['cycle_id'], element['content'])
        elif element['type'] == 'tool':
            display_tool_box(element['tool_data'])

def get_chronological_conversation():
    """Get all conversation elements in chronological order"""
    all_elements = []
    
    # Add user messages and system messages from conversation_history
    for item in st.session_state.conversation_history:
        all_elements.append(item)
    
    # Add agent messages and tools from conversation_elements
    conversation_flow = get_conversation_flow()
    for element in conversation_flow:
        if element['type'] == 'message':
            all_elements.append({
                'type': 'agent_message',
                'cycle_id': element['cycle_id'],
                'content': element['content'],
                'timestamp': element['timestamp']
            })
        elif element['type'] == 'tool':
            all_elements.append({
                'type': 'tool',
                'tool_data': element['tool_data'],
                'timestamp': element['timestamp']
            })
    
    # Sort all elements by timestamp to maintain chronological order
    all_elements.sort(key=lambda x: x['timestamp'])
    
    return all_elements

def display_user_message(content: str):
    """Display user message with markdown support"""
    # Create a container with user message styling
    with st.container():
        st.markdown("""
        <div style="background-color: #e3f2fd; padding: 1rem; margin: 0.5rem 0; border-radius: 0.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <strong>You:</strong>
        </div>
        """, unsafe_allow_html=True)
        
        # Display the content as markdown in a separate container with user styling
        st.markdown(f"""
        <div style="background-color: #e3f2fd; padding: 0 1rem 1rem 1rem; margin: -0.5rem 0.5rem 0.5rem 0.5rem; border-radius: 0 0 0.5rem 0.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
        </div>
        """, unsafe_allow_html=True)
        
        # Use Streamlit's markdown to render the content properly
        with st.container():
            # Add some padding and styling for the markdown content
            st.markdown(f"""
            <div style="background-color: #e3f2fd; padding: 0 1rem 1rem 1rem; margin: -1rem 0.5rem 0.5rem 0.5rem; border-radius: 0 0 0.5rem 0.5rem;">
            """, unsafe_allow_html=True)
            
            # Render the user input as markdown
            st.markdown(content)
            
            st.markdown("</div>", unsafe_allow_html=True)

def display_loading_overlay(content: str):
    """Display loading overlay with transparency and spinner"""
    st.markdown(f"""
    <div class="loading-overlay">
        <div class="loading-content">
            <div class="spinner"></div>
            <h3>{content}</h3>
            <p>Please wait while the agent processes your request...</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

def display_error_message(content: str):
    """Display error message"""
    st.markdown(f"""
    <div class="chat-message" style="background-color: #ffebee; border-left: 4px solid #f44336;">
        <strong>❌ Error:</strong> {content}
    </div>
    """, unsafe_allow_html=True)

def display_message_block(cycle_id: str, content: str):
    """Display agent message block grouped by event_loop_cycle_id"""
    if content.strip():  # Only display if there's actual content
        st.markdown(f"""
        <div class="chat-message" style="background-color: #f1f8e9;">
            {content}
        </div>
        """, unsafe_allow_html=True)

def display_tool_box(tool_data: Dict[str, Any]):
    """Display tool usage box with state indicators and expandable details"""
    tool_name = tool_data['tool_name']
    tool_use_id = tool_data['toolUseId']
    state = tool_data['state']
    tool_input = tool_data['tool_input']
    
    # Get appropriate icon for tool
    icon = get_tool_icon(tool_name)
    
    # Get state indicator
    state_indicator = get_state_indicator(state)
    
    # Create tool box HTML
    tool_box_html = f"""
    <div class="tool-box">
        <div style="display: flex; align-items: center;">
            <span style="font-size: 1.2em; margin-right: 0.5em;">{icon}</span>
            <strong>{tool_name}</strong>
            <span class="tool-progress">{state_indicator}</span>
        </div>
    </div>
    """
    
    st.markdown(tool_box_html, unsafe_allow_html=True)
    
    # Add expandable section for completed tools
    if state == "done" and tool_input:
        display_expandable_tool_input(tool_use_id, tool_input)

def display_expandable_tool_input(tool_use_id: str, tool_input: Dict[str, Any]):
    """Display expandable tool input details for completed tools"""
    # Filter out the 'state' field from display
    filtered_input = {k: v for k, v in tool_input.items() if k != 'state'}
    
    if filtered_input:
        # Create unique key for expander
        expander_key = f"tool_details_{tool_use_id}"
        
        with st.expander("🔍 View Tool Details", expanded=False):
            # Display tool input as formatted JSON
            st.json(filtered_input)

def get_tool_icon(tool_name: str) -> str:
    """Get appropriate icon for tool type"""
    if tool_name == "retrieve":
        return "🔍"
    else:
        return "🔧"

def get_state_indicator(state: str) -> str:
    """Get state indicator for tool"""
    if state == "in-progress":
        return "⏳ In Progress..."
    elif state == "done":
        return "✅ Done"
    elif state == "error":
        return "❌ Error"
    else:
        return "❓ Unknown"

def display_connection_status():
    """Display connection status and error information"""
    if st.session_state.last_error:
        st.error(f"Connection Error: {st.session_state.last_error}")
        if st.button("Clear Error"):
            st.session_state.last_error = None
            st.rerun()
    
    # Show connection status in sidebar or as small indicator
    status_color = {
        'connected': '🟢',
        'connecting': '🟡', 
        'disconnected': '🔴',
        'error': '❌'
    }.get(st.session_state.connection_status, '❓')
    
    st.caption(f"{status_color} Status: {st.session_state.connection_status.title()}")

def update_connection_status(status: str, error: str = None):
    """Update connection status and error state"""
    st.session_state.connection_status = status
    if error:
        st.session_state.last_error = error
        logging.error(f"Connection error: {error}")

def handle_connection_error(error: Exception):
    """Handle connection errors with proper fallback"""
    error_msg = str(error)
    update_connection_status('error', error_msg)
    
    # Remove loading state on error
    if (st.session_state.conversation_history and 
        st.session_state.conversation_history[-1]['type'] == 'loading'):
        st.session_state.conversation_history.pop()
    
    # Add error message to conversation
    st.session_state.conversation_history.append({
        'type': 'error',
        'content': f"Failed to connect to agent: {error_msg}",
        'timestamp': time.time()
    })

if __name__ == "__main__":
    main()