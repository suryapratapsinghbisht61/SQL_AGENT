#!/bin/bash
# Creates a SELECT-only role for the app. Password comes from the environment, never from this file.
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname chinook \
  -v ro_user="$RO_USER" -v ro_password="$RO_PASSWORD" <<'SQL'
CREATE ROLE :"ro_user" LOGIN PASSWORD :'ro_password';
REVOKE ALL ON DATABASE chinook FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE chinook TO :"ro_user";
GRANT USAGE ON SCHEMA public TO :"ro_user";
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"ro_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO :"ro_user";
ALTER ROLE :"ro_user" SET default_transaction_read_only = on;
ALTER ROLE :"ro_user" SET statement_timeout = '10s';
SQL
