"""
db_test.py

PURPOSE:
- Recreate database schema from scratch
- Establish production-style table structure
- Add audit fields, UUIDs, soft delete, timestamps
- Add trigger for automatic updated_at handling

NOTE:
This is NOT a migration system — just a reset script for now.
"""

import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Create database connection
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)

cur = conn.cursor()

# --------------------------------------------------
# DROP EXISTING TABLES (clean reset)
# --------------------------------------------------
# CASCADE ensures dependent objects are also dropped
cur.execute("drop table if exists items cascade;")
cur.execute("drop table if exists categories cascade;")

# --------------------------------------------------
# ENABLE EXTENSIONS
# --------------------------------------------------
# pgcrypto gives us gen_random_uuid()
cur.execute("create extension if not exists pgcrypto;")

# --------------------------------------------------
# TRIGGER FUNCTION FOR updated_at
# --------------------------------------------------
# Automatically updates updated_at on any row update
cur.execute("""
create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;
""")

# --------------------------------------------------
# CREATE TABLE: categories
# --------------------------------------------------
cur.execute("""
create table categories (

    -- internal primary key (fast, indexed, sequential)
    id bigint generated always as identity primary key,

    -- external/public-safe identifier (non-guessable)
    public_id uuid not null unique default gen_random_uuid(),

    -- business field
    name text not null,

    -- timestamps
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    -- audit fields (nullable until auth is added)
    created_by_user_id bigint null,
    updated_by_user_id bigint null,

    -- soft delete fields
    is_deleted boolean not null default false,
    deleted_at timestamptz null,
    deleted_by_user_id bigint null
);
""")

# --------------------------------------------------
# CREATE TABLE: items
# --------------------------------------------------
cur.execute("""
create table items (

    id bigint generated always as identity primary key,
    public_id uuid not null unique default gen_random_uuid(),
             
    category_id bigint not null references categories(id),
            
    name text not null,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    created_by_user_id bigint null,
    updated_by_user_id bigint null,

    is_deleted boolean not null default false,
    deleted_at timestamptz null,
    deleted_by_user_id bigint null
);
""")

# index lookups and joins on category_id
cur.execute("""
create index idx_items_category_id on items(category_id);
""")

# --------------------------------------------------
# ADD TRIGGERS (auto-update updated_at)
# --------------------------------------------------
cur.execute("""
create trigger trg_categories_set_updated_at
before update on categories
for each row
execute function set_updated_at();
""")

cur.execute("""
create trigger trg_items_set_updated_at
before update on items
for each row
execute function set_updated_at();
""")

# --------------------------------------------------
# UNIQUE INDEXES (BUSINESS RULES)
# --------------------------------------------------
# These enforce real-world constraints on active data only.
# We use PARTIAL UNIQUE INDEXES because we support soft deletes.

# Rule 1:
# Category names must be unique among ACTIVE (non-deleted) categories.
# This prevents duplicate categories like "fruit", "fruit".
# Soft-deleted categories do NOT block reuse of the name.
cur.execute("""
create unique index uq_categories_name_active
on categories (name)
where is_deleted = false;
""")


# Rule 2:
# Item names must be globally unique among ACTIVE items.
# An item represents a single real-world entity (e.g., "carrot"),
# and must not exist in multiple categories.
# This prevents duplication that would break inventory logic.
# Soft-deleted items do NOT block reuse of the name.
cur.execute("""
create unique index uq_items_name_active
on items (name)
where is_deleted = false;
""")








# --------------------------------------------------
# COMMIT + CLEANUP (keep this at the bottom of file)
# --------------------------------------------------
conn.commit()
cur.close()
conn.close()

print("tables recreated successfully")

