"""
main.py

PURPOSE
-------
FastAPI backend for a relational CRUD data platform.

This project demonstrates:
- PostgreSQL integration using psycopg2
- FastAPI route design
- request and response models using Pydantic
- UUID-based public identifiers
- internal numeric database keys
- soft delete behavior
- category/item relationships
- filtering, sorting, pagination, and basic aggregate counts

DESIGN NOTES
------------
The database uses internal numeric ids for relational joins and indexing, while
the API exposes UUID public ids. This keeps internal database structure separate
from external API usage.

Client input is limited to business fields only. System-managed fields such as
ids, timestamps, audit fields, and delete flags are intentionally excluded from
request models.

Delete operations are soft deletes. Records are retained in the database but
excluded from normal API queries by checking `is_deleted = false`.
"""

import os
from contextlib import contextmanager
from uuid import UUID

import psycopg2
from psycopg2 import IntegrityError
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Query
from pydantic import BaseModel, Field


# ==================================================
# ENVIRONMENT AND APPLICATION SETUP
# ==================================================
# This section prepares the runtime environment and creates the FastAPI
# application object. Database credentials are loaded from environment variables
# so they are not hardcoded into the source file.

load_dotenv()

app = FastAPI()


# ==================================================
# DATABASE CONNECTION HELPER
# ==================================================
# All database access goes through this helper. It opens a PostgreSQL
# connection, yields it to the endpoint, and closes it automatically afterward.
# This keeps connection management consistent across the API.
@contextmanager
def get_connection():
    """
    Open a PostgreSQL connection and always close it afterward.
    """
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )
    try:
        yield conn
    finally:
        conn.close()


# ==================================================
# REQUEST MODELS
# ==================================================
# These Pydantic models define what clients are allowed to send into the API.
# They include only business fields. Database ids, UUIDs, timestamps, audit
# fields, and soft-delete fields are managed by the backend/database.

class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category_public_id: UUID


class ItemUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category_public_id: UUID


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class CategoryUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None

# ==================================================
# CATEGORY RESPONSE MODELS
# ==================================================
# These models define the public API shape for category data. Response models
# intentionally expose `public_id` instead of internal database `id`.
#
# CategoryListResponse extends the basic category response with `item_count`
# for list views.

# base shape for a category returned by API
class CategoryResponse(BaseModel):
    public_id: str
    name: str
    description: str | None = None

class CategoryListResponse(BaseModel):
    public_id: str
    name: str
    description: str | None = None
    item_count: int

# ==================================================
# ITEM RESPONSE MODELS
# ==================================================
# Item responses include both the item's public id and the related category's
# public id/name. This lets the API return useful relationship information
# without exposing internal foreign key ids.

# response for single item request
class ItemResponse(BaseModel):
    public_id: str
    name: str
    category_public_id: str
    category_name: str

# response for list of items (same shape for now)
class ItemListResponse(ItemResponse):
    pass


# ==================================================
# SHARED COLUMN LISTS
# ==================================================
# These constants centralize repeated SELECT columns. This keeps endpoint SQL
# consistent and avoids repeating audit/metadata fields across every query.

ITEM_COLUMNS = """
    i.id,
    i.public_id,
    i.category_id,
    i.name,
    i.created_at,
    i.updated_at,
    i.created_by_user_id,
    i.updated_by_user_id,
    i.is_deleted,
    i.deleted_at,
    i.deleted_by_user_id,
    c.public_id as category_public_id,
    c.name as category_name
"""

CATEGORY_COLUMNS = """
    c.id,
    c.public_id,
    c.name,
    c.description,
    c.created_at,
    c.updated_at,
    c.created_by_user_id,
    c.updated_by_user_id,
    c.is_deleted,
    c.deleted_at,
    c.deleted_by_user_id
"""


# ==================================================
# CURSOR / ROW HELPERS
# ==================================================
# psycopg2 returns rows as tuples. These helpers convert query results into
# dictionaries keyed by column name, which makes the API response easier to
# return as JSON.

def fetch_one_as_dict(cur):
    """
    Fetch one row from the cursor and return it as a dict.
    Returns None if no row exists.
    """
    row = cur.fetchone()

    if row is None:
        return None

    columns = [desc[0] for desc in cur.description]
    result = dict(zip(columns, row))

    if "public_id" in result and result["public_id"] is not None:
        result["public_id"] = str(result["public_id"])

    return result


def fetch_all_as_dicts(cur):
    """
    Fetch all rows from the cursor and return them as a list of dicts.
    """
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]

    result = []

    for row in rows:
        record = dict(zip(columns, row))

        if "public_id" in record and record["public_id"] is not None:
            record["public_id"] = str(record["public_id"])

        result.append(record)

    return result


def get_category_id_by_public_id(cur, category_public_id: UUID):
    """
    Resolve a category UUID to its internal numeric id.
    Excludes soft-deleted categories.
    """
    cur.execute("""
        select id
        from categories
        where public_id = %s
          and is_deleted = false;
    """, (str(category_public_id),))

    row = cur.fetchone()

    if row is None:
        return None

    return row[0]


# ==================================================
# ROOT / HEALTH CHECK ENDPOINT
# ==================================================
# Minimal endpoint used to confirm that the backend server is running.

@app.get("/")
def root():
    """
    Basic health/check endpoint.
    """
    return {"message": "backend is running"}


# ==================================================
# ITEMS ENDPOINTS
# ==================================================
# These endpoints manage item records. Items belong to categories, so item
# create/update operations resolve category public UUIDs into internal category
# ids before writing to the database.

@app.get("/items", response_model=list[ItemListResponse])
def get_items(
    category_public_id: str | None = None,
    sort_by: str = "id",
    sort_dir: str = "asc",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    # Build one query that supports optional category filtering, safe sorting,
    # and pagination.
    with get_connection() as conn:
        cur = conn.cursor()

        # start with the base SQL
        query = f"""
            select
                {ITEM_COLUMNS}
            from items i
            join categories c
              on c.id = i.category_id
            where i.is_deleted = false
              and c.is_deleted = false
        """

        # Query values are stored separately from SQL text so psycopg2 can
        # safely parameterize them.
        params = []

        # if a category_public_id was provided, filter to that category
        if category_public_id:
            query += " and c.public_id = %s"
            params.append(category_public_id)

        # Only known sort keys are mapped to SQL column names.
        allowed_sort = {
            "id": "i.id",
            "name": "i.name",
            "category_name": "c.name"
        }

        # Invalid sort input falls back to a safe default.
        sort_column = allowed_sort.get(sort_by, "i.id")

        # Sort direction is constrained to asc/desc.
        sort_direction = "asc" if sort_dir.lower() != "desc" else "desc"

        # add order by as Python, not inside the SQL text block
        query += f" order by {sort_column} {sort_direction}"

        # finish query with pagination
        query += """
            limit %s
            offset %s;
        """

        # add pagination params last
        params.extend([limit, offset])

        # execute final SQL
        cur.execute(query, params)

        return fetch_all_as_dicts(cur)


@app.get("/items/{public_id}", response_model=ItemResponse)
def get_item(public_id: UUID):
    """
    Get one item by public UUID, including category info.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            select
                {ITEM_COLUMNS}
            from items i
            join categories c
              on c.id = i.category_id
            where i.public_id = %s
              and i.is_deleted = false
              and c.is_deleted = false;
        """, (str(public_id),))

        result = fetch_one_as_dict(cur)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="item not found"
        )

    return result


@app.post("/items", status_code=status.HTTP_201_CREATED)
def create_item(item: ItemCreate):
    """
    Create a new item linked to an existing category.
    """
    with get_connection() as conn:
        cur = conn.cursor()

        category_id = get_category_id_by_public_id(cur, item.category_public_id)

        if category_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="category not found"
            )

        try:
            cur.execute("""
                insert into items (name, category_id)
                values (%s, %s)
                returning public_id;
            """, (item.name, category_id))

            inserted_row = cur.fetchone()
            conn.commit()

        except IntegrityError:
            conn.rollback()
            raise HTTPException(
                status_code=409,
                detail="item name already exists"
            )

    new_public_id = inserted_row[0]

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            select
                {ITEM_COLUMNS}
            from items i
            join categories c
              on c.id = i.category_id
            where i.public_id = %s
              and i.is_deleted = false
              and c.is_deleted = false;
        """, (str(new_public_id),))

        result = fetch_one_as_dict(cur)

    return result


@app.put("/items/{public_id}")
def update_item(public_id: UUID, item: ItemUpdate):
    """
    Update an existing item.
    """
    with get_connection() as conn:
        cur = conn.cursor()

        category_id = get_category_id_by_public_id(cur, item.category_public_id)

        if category_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="category not found"
            )

        try:
            cur.execute("""
                update items
                set
                    name = %s,
                    category_id = %s
                where public_id = %s
                  and is_deleted = false
                returning public_id;
            """, (item.name, category_id, str(public_id)))

            updated_row = cur.fetchone()

            if not updated_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="item not found"
                )

            conn.commit()

        except IntegrityError:
            conn.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="item name already exists"
            )

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            select
                {ITEM_COLUMNS}
            from items i
            join categories c
              on c.id = i.category_id
            where i.public_id = %s
              and i.is_deleted = false
              and c.is_deleted = false;
        """, (str(public_id),))

        result = fetch_one_as_dict(cur)

    return result


@app.delete("/items/{public_id}")
def delete_item(public_id: UUID):
    """
    Soft delete an item.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            update items
            set
                is_deleted = true,
                deleted_at = now()
            where public_id = %s
              and is_deleted = false
            returning {ITEM_COLUMNS};
        """, (str(public_id),))

        result = fetch_one_as_dict(cur)
        conn.commit()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="item not found"
        )

    return {
        "message": "item deleted",
        "item": result
    }


# ==================================================
# CATEGORIES ENDPOINTS
# ==================================================
# These endpoints manage category records. Category list responses include an
# active item count so the API can show relationship context without requiring a
# second request.

@app.get("/categories", response_model=list[CategoryListResponse])
def get_categories(
    name: str | None = None,
    sort_by: str = "id",
    sort_dir: str = "asc",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    # Build one query that supports optional name filtering, safe sorting,
    # pagination, and active item counts.
    with get_connection() as conn:
        cur = conn.cursor()

        # start with the base SQL
        query = f"""
            select
                {CATEGORY_COLUMNS},
                (
                    select count(*)
                    from items i
                    where i.category_id = c.id
                      and i.is_deleted = false
                ) as item_count
            from categories c
            where c.is_deleted = false
        """

        # params list will hold values for %s placeholders
        params = []

        # if user provided a name, add filter to SQL
        if name:
            query += " and c.name ilike %s"
            params.append(f"%{name}%")

        # map allowed sort columns to real SQL columns
        allowed_sort = {
            "id": "c.id",
            "name": "c.name"
        }

        # default to safe values if input is invalid
        sort_column = allowed_sort.get(sort_by, "c.id")

        # only allow asc or desc
        sort_direction = "asc" if sort_dir.lower() != "desc" else "desc"

        # add order by as Python, not inside SQL text block
        query += f" order by {sort_column} {sort_direction}"

        # finish query with pagination
        query += """
            limit %s
            offset %s;
        """

        # add pagination params last
        params.extend([limit, offset])

        # execute final SQL
        cur.execute(query, params)

        return fetch_all_as_dicts(cur)


@app.get("/categories/{public_id}", response_model=CategoryResponse)
def get_category(public_id: UUID):
    """
    Get one category by public UUID.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            select
                {CATEGORY_COLUMNS}
            from categories c
            where c.public_id = %s
              and c.is_deleted = false;
        """, (str(public_id),))

        result = fetch_one_as_dict(cur)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="category not found"
        )

    return result


@app.post("/categories", status_code=status.HTTP_201_CREATED)
def create_category(category: CategoryCreate):
    """
    Create a new category.
    """
    with get_connection() as conn:
        cur = conn.cursor()

        try:
            cur.execute("""
                insert into categories (name, description)
                values (%s, %s)
                returning public_id;
            """, (category.name, category.description))

            inserted_row = cur.fetchone()
            conn.commit()

        except IntegrityError:
            conn.rollback()
            raise HTTPException(
                status_code=409,
                detail="category name already exists"
            )

    new_public_id = inserted_row[0]

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            select
                {CATEGORY_COLUMNS},
                (
                    select count(*)
                    from items i
                    where i.category_id = c.id
                      and i.is_deleted = false
                ) as item_count
            from categories c
            where c.public_id = %s
              and c.is_deleted = false;
        """, (str(new_public_id),))

        result = fetch_one_as_dict(cur)

    return result


@app.put("/categories/{public_id}")
def update_category(public_id: UUID, payload: CategoryUpdate):
    """
    Update a category name by public UUID.
    """
    with get_connection() as conn:
        cur = conn.cursor()

        try:
            cur.execute("""
                update categories
                set
                    name = %s,
                    description = %s,
                    updated_at = now()
                where public_id = %s
                  and is_deleted = false
                returning public_id;
            """, (
                payload.name,
                payload.description,
                str(public_id),
            ))

            updated = cur.fetchone()

            if not updated:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="category not found"
                )

            cur.execute(f"""
                select
                    {CATEGORY_COLUMNS},
                    (
                        select count(*)
                        from items i
                        where i.category_id = c.id
                          and i.is_deleted = false
                    ) as item_count
                from categories c
                where c.public_id = %s
                  and c.is_deleted = false;
            """, (str(public_id),))

            result = fetch_one_as_dict(cur)
            conn.commit()
            return result

        except IntegrityError:
            conn.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="category name already exists"
            )


@app.delete("/categories/{public_id}")
def delete_category(public_id: UUID):
    """
    Soft delete a category only if it has no active items.
    """
    with get_connection() as conn:
        cur = conn.cursor()

        # First get the category row itself
        cur.execute(f"""
            select
                {CATEGORY_COLUMNS}
            from categories c
            where public_id = %s
              and is_deleted = false;
        """, (str(public_id),))

        existing_category = fetch_one_as_dict(cur)

        if not existing_category:
            raise HTTPException(
                status_code=404,
                detail="category not found"
            )

        # Use the internal id for child-record checks.
        category_id = existing_category["id"]

        # Prevent deleting a category that still has active child items.
        cur.execute("""
            select 1
            from items
            where category_id = %s
              and is_deleted = false
            limit 1;
        """, (category_id,))

        child_row = cur.fetchone()

        if child_row:
            raise HTTPException(
                status_code=409,
                detail="cannot delete category with active items"
            )

        # No active children exist, so the category can be soft-deleted.
        cur.execute("""
            update categories
            set
                is_deleted = true,
                deleted_at = now()
            where public_id = %s
              and is_deleted = false;
        """, (str(public_id),))

        conn.commit()

    return {
        "message": "category deleted",
        "category": existing_category
    }

@app.get("/categories/{public_id}/items")
def get_items_by_category(public_id: UUID):
    """
    Get all items for a specific category.
    """
    with get_connection() as conn:
        cur = conn.cursor()

        category_id = get_category_id_by_public_id(cur, public_id)

        if category_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="category not found"
            )
        
        cur.execute(f"""
            select
                {ITEM_COLUMNS}
            from items i
            join categories c
              on c.id = i.category_id
            where i.category_id = %s
              and i.is_deleted = false
              and c.is_deleted = false
            order by i.id;
        """, (category_id,))

        result = fetch_all_as_dicts(cur)

    return result

# ==================================================
# DEBUG ENDPOINTS (DEV ONLY)
# ==================================================
# These endpoints expose raw active rows without response-model filtering.
# They are useful during development for verifying database state, but should
# not be exposed in a production API.

# returns the full raw category rows (no response model filtering)
@app.get("/debug/categories")
def debug_categories():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            select  *
            from categories
            where is_deleted = false
            order by id;
        """)
        return fetch_all_as_dicts(cur)
    

@app.get("/debug/items")
def debug_items():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            select *
            from items
            where is_deleted = false
            order by id;
        """)

        return fetch_all_as_dicts(cur)
        