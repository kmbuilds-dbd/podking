#!/usr/bin/env bash
# One-time local DB setup. Safe to re-run (idempotent).
set -euo pipefail

DB_USER="${DB_USER:-podking}"
DB_PASS="${DB_PASS:-podking}"
DB_NAME="${DB_NAME:-podking}"
DB_TEST="${DB_TEST:-podking_test}"

psql postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASS}' CREATEDB;
  END IF;
END\$\$;

SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec

SELECT 'CREATE DATABASE ${DB_TEST} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_TEST}')\gexec
SQL

psql "postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}" \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql "postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_TEST}" \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "Local DB ready: ${DB_NAME}, ${DB_TEST}"
