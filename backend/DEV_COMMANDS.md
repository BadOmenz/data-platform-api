# DEV COMMANDS — PROJECT 01 DATA PLATFORM

## NAVIGATE TO PROJECT

cd C:\dev\project01_data_platform\backend

---

## ACTIVATE VENV (PowerShell)

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1

---

## RUN API SERVER

uvicorn main:app --reload

Swagger:
http://127.0.0.1:8000/docs

---

## CONNECT TO DATABASE (psql)

psql -U postgres -d project01_data_platform

(password: your DB password)

Exit:
\q

---

## RUN SQL

select * from categories;
select * from items;

IMPORTANT: always end with ;

---

## ALEMBIC COMMANDS

### show migration history

alembic history

### show current version

alembic current

### create new migration

alembic revision -m "your message"

### apply migrations

alembic upgrade head

---

## COMMON FLOW

1. create migration
2. edit upgrade()
3. run: alembic upgrade head
4. update main.py if needed
5. test in Swagger

---
