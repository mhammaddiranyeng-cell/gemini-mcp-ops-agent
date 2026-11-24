FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server ./server
COPY agent ./agent
CMD ["python", "-m", "agent.ops_agent"]
