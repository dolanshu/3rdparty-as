#!/bin/bash
# Dev-only role provisioning for compose. Production roles must be DBA-provisioned.
set -euo pipefail

owner_password="${AS_CONFIG_OWNER_PASSWORD:-as_config_owner_dev}"
web_password="${AS_CONFIG_WEB_PASSWORD:-as_config_web_dev}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
CREATE ROLE as_config_runtime NOLOGIN;
CREATE ROLE as_config_owner LOGIN PASSWORD '${owner_password}';
CREATE ROLE as_config_web LOGIN PASSWORD '${web_password}';

GRANT as_config_runtime TO as_config_web;
ALTER DATABASE as_config OWNER TO as_config_owner;
EOSQL
