# sudo docker build -f ./ThingsBoard_Collector_Module/Docker/Dockerfiles/thingsboard_collector.dockerfile -t thingsboard_collector_robust6g:latest .

FROM python:3.12-slim

WORKDIR /app

# Dependencies
RUN pip install --no-cache-dir \
    flask==3.1.0 \
    requests==2.32.3 \
    confluent-kafka==2.7.0

# App files
COPY ThingsBoard_Collector_Module/Scripts/thingsboard_api.py /app/thingsboard_api.py
COPY ThingsBoard_Collector_Module/Scripts/api_server.py /app/api_server.py
COPY ThingsBoard_Collector_Module/Scripts/utils.py /app/utils.py

# Create non-root user for security
RUN useradd -m -u 1000 tbcollector && \
    chown -R tbcollector:tbcollector /app

USER tbcollector

# API port exposed
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:5000/health', timeout=2).raise_for_status()"

ENTRYPOINT ["python3", "/app/api_server.py"]