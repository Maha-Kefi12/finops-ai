#!/bin/bash
# Initialize pgvector extension in PostgreSQL database
# This script is run after PostgreSQL starts

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
    \dx vector
EOSQL

echo "pgvector extension initialized successfully!"
