FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30" "sqlmodel>=0.0.22" "httpx>=0.27" "pydantic-settings>=2.4" "garminconnect>=0.3.5" "mcp>=2.3" "anthropic>=2.7"
COPY app ./app
ENV DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
