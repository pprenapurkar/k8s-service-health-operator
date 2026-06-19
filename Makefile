# Service Health Operator — common tasks
.PHONY: test setup run deploy break spike oom clean

test:           ## run unit tests (no cluster needed)
	./.venv/bin/python -m pytest

setup:          ## cluster + prometheus + crd + rbac + target + guard
	./scripts/setup.sh

run:            ## run the operator out-of-cluster (dev mode)
	PYTHONPATH=. ./.venv/bin/kopf run operator_app/main.py --verbose

deploy:         ## build image, load into kind, run in-cluster
	./scripts/deploy-incluster.sh

break:          ## force a crash loop on demo-app
	./scripts/break-crashloop.sh

spike:          ## spike CPU inside a demo-app pod
	./scripts/spike-cpu.sh

oom:            ## trigger an OOMKill on a demo-app pod
	./scripts/oom.sh

clean:          ## delete the kind cluster
	kind delete cluster --name operator-lab
