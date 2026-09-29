# AS Platform Container Image

Build the platform image from the repository root:

```sh
docker build -t as-platform:dev -f deploy/docker/Dockerfile .
```

The image installs only the `as-platform` workspace member and its runtime dependencies. It runs as UID and GID `10001`, matching the Helm pod security context, and starts the process through `python -m as_platform`.

## Helm relationship

The image is an input to the Helm chart; it is not a second production deployment form. Helm remains the only production deployment form under ADR-0013. The files under `deploy/compose/` are for local development only.

Publish an image to the customer-internal registry with an immutable tag, then set the matching Helm values. For example, an image tagged as `registry.example.com/3rdparty-as:0.1.0` corresponds to:

```yaml
image:
  repository: registry.example.com/3rdparty-as
  tag: 0.1.0
```

An empty `image.tag` makes the chart use its `appVersion`; setting the tag explicitly avoids ambiguity during upgrades and rollbacks.

## Current runtime scope

This image currently runs only the signal-aware process shell. It does not bind a SIP stack and cannot process calls yet. The real call path and SIP listener arrive after M2b.

The Dockerfile exposes the Helm container ports, UDP `5060` and TCP `5061`, but intentionally defines no Docker `HEALTHCHECK`. The Helm chart owns production liveness and readiness probes, which use the named TCP SIP TLS port. Until the SIP listener exists, an image-local TCP health check would always fail and would misrepresent the process shell's current capability.

To verify that the installed package is importable without starting the long-running entry point:

```sh
docker run --rm --entrypoint python as-platform:dev -c "import as_platform; print(as_platform.__name__)"
```
