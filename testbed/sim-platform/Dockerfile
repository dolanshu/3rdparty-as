FROM python:3.10-slim-bookworm

ARG DEBIAN_MIRROR=deb.debian.org
RUN sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin sim

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /bin/uv

WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY platform platform
COPY apps/translation apps/translation
COPY apps/anti-fraud apps/anti-fraud
COPY services/config-service services/config-service
COPY services/console services/console
COPY testbed/simulators/pyproject.toml testbed/simulators/pyproject.toml
COPY testbed/simulators/src testbed/simulators/src
COPY testbed/simulators/README.md testbed/simulators/README.md
COPY testbed/load/pyproject.toml testbed/load/pyproject.toml
COPY testbed/load/src testbed/load/src
COPY testbed/load/README.md testbed/load/README.md

RUN uv sync --frozen --no-dev --package as-simulators \
    && /src/.venv/bin/python -c "from pathlib import Path; import as_simulators; assert (Path(as_simulators.__file__).parent / 'static' / 'index.html').is_file()"

ENV PATH="/src/.venv/bin:${PATH}"
USER 10001
EXPOSE 8088 5060/tcp 5060/udp 5061/tcp
ENTRYPOINT ["as-simulators"]
CMD ["serve", "--host", "0.0.0.0", "--ui-host", "0.0.0.0"]
