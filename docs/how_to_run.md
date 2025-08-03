# How to Run

## Prerequisites

### 1. Environment Configuration
Copy `sample.env` to `.env`:
```bash
cp sample.env .env
```

### 2. Bedrock Model Access
Get access to AWS Bedrock models by following the [AWS Bedrock Getting Started Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/getting-started.html).

You'll need access to either:
- Nova Pro model
- Sonnet 4 model

### 3. Bedrock Knowledge Base Setup
Set up your knowledge base following the [AWS Bedrock Knowledge Base Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-create.html).

After creating your knowledge base and syncing your data sources, add your `knowledge_base_id` to the `.env` file:
```
KNOWLEDGE_BASE_ID="your-knowledge-base-id"
```

Make sure `AWS_REGION_NAME` matches the region where your knowledge base is located:
```
AWS_REGION_NAME="region-where-bedrock-knowledge-base-is-created"
```

### 4. Install UV
Install UV package manager by following the [UV Installation Guide](https://docs.astral.sh/uv/getting-started/installation/).

## Setup and Run

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Activate virtual environment:**
   ```bash
   source .venv/bin/activate
   ```

3. **Set AWS profile in terminal:**
   Configure your AWS credentials/profile

4. **Run the agent backend:**
   ```bash
   python src/agent/app.py
   ```

5. **open another terminal, activate venv and run the frontend:**
   ```bash
   source .venv/bin/activate
   streamlit run src/ui/app.py
   ```

The application will be available at the URL shown in the Streamlit output (typically `http://localhost:8501`).