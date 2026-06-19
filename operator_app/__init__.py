"""Service Health Operator package.

A custom Kubernetes operator (Python + kopf) that watches Prometheus metrics
and pod health, then automatically restarts stuck/OOMKilled pods, garbage-
collects dead pods, surfaces preventable issues, and scales deployments
within declared bounds. Intent is expressed via a ServiceGuard custom resource.

NOTE ON THE PACKAGE NAME
------------------------
The build guides name this package ``operator``.  Python ships a *built-in*
``operator`` module that is imported at interpreter startup, so a local package
called ``operator`` is permanently shadowed by the stdlib and
``from operator import k8s`` raises ImportError.  We therefore name the package
``operator_app`` (the only change required to make the guide's code actually
run).  Everything else follows the guides line for line.
"""
