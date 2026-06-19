"""Service Health Operator package.

A custom Kubernetes operator (Python + kopf) that watches Prometheus metrics
and pod health, then automatically restarts stuck/OOMKilled pods, garbage-
collects dead pods, surfaces preventable issues, and scales deployments
within declared bounds. Intent is expressed via a ServiceGuard custom resource.

"""
