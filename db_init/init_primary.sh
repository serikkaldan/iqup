#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER ${REPLICATOR_USER} WITH REPLICATION ENCRYPTED PASSWORD '${REPLICATOR_PASSWORD}';
EOSQL

cat >> "$PGDATA/pg_hba.conf" <<EOF
host replication ${REPLICATOR_USER} 0.0.0.0/0 md5
EOF

cat >> "$PGDATA/postgresql.conf" <<EOF
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
hot_standby = on
EOF