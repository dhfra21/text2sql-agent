# Text2SQL Agent

A conversational AI agent that translates natural language questions into SQL queries, executes them against a PostgreSQL database, and returns plain-English answers.

Built with **Google ADK** and **Gemini 2.0 Flash** as part of the Devoteam Tunisia — Agentic AI internship track (Summer 2026).

---

## How it works

```
User question (natural language)
        ↓
   ADK Agent  ←  Gemini 2.0 Flash / Llama 3.3
        ├── get_schema()       → reads DB table/column metadata
        ├── generate_sql()     → builds SQL from schema + question
        ├── validate_sql()     → blocks dangerous statements & injections
        └── execute_query()    → runs query, returns rows
        ↓
   Plain-English Answer
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent Framework | Google ADK (Python) |
| LLM | Gemini 2.0 Flash / Llama 3.3 70B (Groq) |
| Database | PostgreSQL |
| DB Driver | psycopg2 / SQLAlchemy |
| Frontend | Streamlit (Weeks 5–6) |
| Evaluation | BIRD benchmark |
| Deployment | Cloud Run |

---

## Project Structure

```
text2sql_agent/
├── agent/
│   ├── agent.py               ← ADK root_agent definition
│   ├── tools/
│   │   ├── schema_tool.py     ← get_schema()
│   │   ├── sql_generator.py   ← generate_sql()
│   │   ├── sql_validator.py   ← validate_sql()
│   │   └── query_executor.py  ← execute_query()
│   └── prompts/
│       └── system_prompt.txt
├── db/
│   ├── schema.sql             ← demo database DDL
│   └── seed.sql               ← sample data
├── frontend/
│   └── app.py                 ← Streamlit UI (coming Week 5)
├── eval/
│   ├── benchmark.py           ← BIRD evaluation runner
│   └── test_cases.json
└── tests/
    ├── test_schema_tool.py
    ├── test_sql_validator.py
    ├── test_query_executor.py
    └── test_agent_e2e.py
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/your-username/text2sql-agent.git
cd text2sql_agent
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in your values
```

Required variables:

```bash
# LLM — use one of:
GOOGLE_API_KEY=...   # Gemini 2.0 Flash (Google AI Studio)
GROQ_API_KEY=...     # Llama 3.3 70B (free at console.groq.com)

# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=text2sql_dev
DB_USER=postgres
DB_PASSWORD=...
```

### 3. Set up the database

```bash
psql -U postgres -d text2sql_dev -f db/schema.sql
psql -U postgres -d text2sql_dev -f db/seed.sql
```

### 4. Run the agent

```bash
# CLI mode
adk run agent

# Web UI (recommended)
adk web agent
```

---

## Running Tests

```bash
pytest tests/ -v
```

18 unit tests covering schema introspection, SQL validation (injection, DDL blocking), and query execution.

---

## Evaluation

### Custom benchmark (no download required)

Runs 10 hand-written questions against the local PostgreSQL demo database and measures **Execution Accuracy (EX)** — whether the agent's result set matches the gold result set.

```bash
python eval/benchmark.py
```

Expected output:
```
  [PASS] Q01  How many customers are there?
  [PASS] Q02  Which products cost more than 100 euros?
  ...
  Strict EX (exact columns):  10/10 = 100.0%
  Lax EX   (correct values):  10/10 = 100.0%
```

### BIRD benchmark (real-world evaluation)

Evaluates the agent against the [BIRD](https://bird-bench.github.io/) benchmark — 1 534 business-domain questions across 11 SQLite databases.

**Step 1 — Download BIRD dev set**

Go to [bird-bench.github.io](https://bird-bench.github.io/) → Download → `dev.zip` (~400 MB).
Extract so the layout is:

```
dev_20240627/
  dev.json
  dev_databases/
    dev_databases/
      california_schools/
        california_schools.sqlite
      card_games/
      ...
```

**Step 2 — Run**

```bash
# 50 random questions across all 11 databases (recommended first run)
python eval/bird_benchmark.py --bird-path ../dev_20240627

# Restrict to one database
python eval/bird_benchmark.py --bird-path ../dev_20240627 --db california_schools --n 50

# Filter by difficulty
python eval/bird_benchmark.py --bird-path ../dev_20240627 --difficulty simple --n 30

# Save full results to JSON
python eval/bird_benchmark.py --bird-path ../dev_20240627 --n 50 --output eval/bird_results.json
```

**Options**

| Flag | Default | Description |
|---|---|---|
| `--bird-path` | required | Path to the extracted BIRD dev directory |
| `--n` | 50 | Number of questions to evaluate |
| `--db` | all | Restrict to one database ID |
| `--difficulty` | all | `simple`, `moderate`, or `challenging` |
| `--seed` | 42 | Random seed for reproducible sampling |
| `--delay` | 3 | Seconds between Groq API calls (free-tier rate limit) |
| `--output` | none | Save detailed results to a JSON file |

**Expected output**

```
BIRD Evaluation — 50 questions
  [PASS] Q0061 [california_schools] [simple     ] How many chartered schools ...
  [FAIL] Q0065 [california_schools] [moderate   ] What is the ratio in percentage ...
         agent : SELECT COUNT(...) ...
         gold  : SELECT CAST(SUM(...)) ...
  ...
  ------------------------------------------------------------------------
  Execution Accuracy (EX) : 28/50 = 56.0%
  Target (Week 5-6)       : 60.0%

  By difficulty:
    simple      :  18/25  = 72.0%
    moderate    :   8/18  = 44.4%
    challenging :   2/7   = 28.6%
```

**How EX is measured**

Result sets are compared as **deduplicated, order-independent sets** — matching the official BIRD metric. A question scores 1 if the agent's unique result values exactly match the gold SQL's unique result values, 0 otherwise.

---

## Milestones

| Weeks | Milestone |
|---|---|
| 1–2 | Core tools + end-to-end pipeline |
| 3–4 | Session memory, error handling, unit tests |
| 5–6 | BIRD benchmark, Streamlit frontend, Cloud Run deployment |
