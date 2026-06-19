FROM python:3.11-slim
WORKDIR /app
ENV PYTHONPATH=/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY operator_app/ ./operator_app/
RUN useradd --create-home appuser
USER appuser
CMD ["kopf", "run", "operator_app/main.py", "--standalone", "--all-namespaces"]
