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

## Milestones

| Weeks | Milestone |
|---|---|
| 1–2 | Core tools + end-to-end pipeline |
| 3–4 | Session memory, error handling, unit tests |
| 5–6 | BIRD benchmark, Streamlit frontend, Cloud Run deployment |
