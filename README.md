# PROJECT 01 — DATA PLATFORM (FASTAPI + POSTGRES)

## Overview

This project is a backend API built with FastAPI and PostgreSQL that manages categories and items with relational constraints, soft deletion, and production-style list endpoints.

It demonstrates core backend engineering concepts including schema design, API structure, and safe query handling.

---

## Project Structure

```
project01_data_platform/
│
├── backend/
│   ├── main.py
│   ├── alembic/
│   └── db_test.py
│
└── README.md
```

## Tech Stack

* FastAPI (API layer)
* PostgreSQL (database)
* psycopg2 (DB driver)
* Alembic (migrations)
* Pydantic (request/response models)

---

## Core Features

### Data Model

* Categories and Items (1-to-many relationship)
* UUID-based public IDs
* Soft delete (is_deleted flag)
* Partial unique indexes for active records

---

### API Features

#### CRUD

* Create, read, update, delete for categories and items
* Deletes are soft deletes

#### Response Models

* Clean API outputs using Pydantic
* Internal fields (id, audit fields) not exposed

#### List Endpoints

Both `/categories` and `/items` support:

* Pagination

  * `limit`
  * `offset`

* Filtering

  * categories by name
  * items by category

* Sorting

  * `sort_by`
  * `sort_dir`

---

### Validation

* Query parameter validation using FastAPI `Query`
* Limits enforced (e.g. max page size)
* Prevents invalid or unsafe input

---

### Migrations

* Alembic used for schema changes
* Schema evolves incrementally
* No manual DB resets required

---

### Debug Endpoints (Dev Only)

* `/debug/categories`
* `/debug/items`

Used for inspecting full raw database records during development.

---

## Example Requests

```http
GET /categories?limit=10&offset=0
GET /categories?name=fruit
GET /categories?sort_by=name&sort_dir=desc

GET /items?category_public_id=UUID
GET /items?sort_by=category_name
```

---

## Design Notes

* SQL written manually for clarity and control
* Dynamic SQL built safely with parameter binding
* Separation of concerns:

  * DB schema (Alembic)
  * queries (SQL)
  * API contract (Pydantic)

---

## Status

Project complete and ready as a portfolio backend example.

Next step: Full stack application using React + TypeScript.
