# Notification Service Kubernetes manifests

This directory is a production-oriented Kustomize base for the FastAPI API and
Celery worker. PostgreSQL, Redis, SMTP, TLS certificate management, the ingress
controller, and Metrics Server are expected to be managed outside this base.

## Files

- `deployment.yaml`: three-instance FastAPI API with rolling updates and probes.
- `celery-worker-deployment.yaml`: Celery delivery workers.
- `celery-beat-deployment.yaml`: optional; not deployed until a periodic schedule exists.
- `migration-job.yaml`: one-shot `alembic upgrade head` job.
- `secret.example.yaml`: credential shape only; never store real values here.
- `networkpolicy.yaml`: baseline ingress/egress policy; replace public CIDRs with provider CIDRs.

No in-cluster Redis is included. Production should use a managed or separately
operated Redis service and supply its TLS URL through the Secret.

## Before deployment

1. Replace example domains, email addresses, ingress class, and TLS secret name.
2. Publish the image to your registry and override `images.newName/newTag`.
3. Create `notification-service-secrets` with your secret-management platform.
4. Restrict NetworkPolicy egress CIDRs to your PostgreSQL, Redis, SMTP, and HTTPS providers.
5. Install Metrics Server for the HPAs and an NGINX ingress controller (or adapt annotations).

## Render and validate

```sh
kubectl kustomize notification-service/k8s
kubectl apply --dry-run=server -k notification-service/k8s
```

Run migrations before rolling out the API and worker:

```sh
kubectl apply -f notification-service/k8s/migration-job.yaml
kubectl wait --for=condition=complete job/notification-migrate -n marketplace --timeout=10m
kubectl apply -k notification-service/k8s
```

Kubernetes Jobs are immutable in several fields. For repeated manual migration
runs, delete the completed Job or give each release a unique Job name through
your delivery pipeline.

For production releases, use immutable image digests or version tags instead of
`latest` and let the delivery system sequence migration completion before the
Deployments are updated.
