# Project Documentation

## Quick Start

- **How to Run**: [Setup and Installation Guide](how_to_run.md)
- **Frontend**: [Streamlit UI](streamlit_ui.md)
- **Backend**: [Strands Agent API](strands_agent_api.md)

## Components Overview

This project consists of two main components that work together to provide an AI agent interface:

- **Streamlit UI**: A web-based frontend that provides an interactive chat interface for users to communicate with AI agents
- **Strands Agent API**: A backend service that handles agent logic, message processing, and maintains conversation state

## Architecture

![Architecture Diagram](assets/overview.svg)

The system follows a client-server architecture where the Streamlit frontend communicates with the agent API backend to process user requests and maintain conversation sessions.