# Dockerfile -- packages the operator into a small image.
FROM python:3.11-slim
WORKDIR /app
# Put the project root on the path so `from operator_app import ...` resolves
# (kopf only adds the handler file's own directory to sys.path).
ENV PYTHONPATH=/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY operator_app/ ./operator_app/
RUN useradd --create-home appuser
USER appuser
# kopf runs the operator; --standalone avoids needing leader-election RBAC.
CMD ["kopf", "run", "operator_app/main.py", "--standalone", "--all-namespaces"]
