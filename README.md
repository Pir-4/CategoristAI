# CategoristAI — Financial Transaction Intelligence: Master Blueprint

## 1. Project Vision
A self-learning personal finance system designed to automate expense categorization using **RAG (Retrieval-Augmented Generation)** and **AI Agents**. Handles multi-currency accounts, internal transfers, and researches unknown merchants via tiered search tools.

---

## 2. Technology Stack
*   **Package Manager:** **uv** (Astral's high-performance Python bundler).
*   **Backend:** FastAPI (Python 3.12+, Asynchronous).
*   **Primary DB:** PostgreSQL (Storage on External HDD).
*   **Vector DB:** Qdrant (Storage on External HDD).
*   **AI Engine:** Pydantic AI (Agentic logic & Structured output).
*   **LLM & Embeddings:** Google Gemini 1.5 Flash (LLM), Gemini Embedding API.
*   **Search Tools:** Perplexity API (Tier 1), DuckDuckGo Search (Tier 2 Fallback).
*   **Deployment:** Docker Compose on Raspberry Pi (ARM64).
*   **Networking:** Tailscale (Secure Mesh VPN).

---

## 3. Data Model (PostgreSQL)
*   **Account:** `id`, `name`, `currency` (GBP/EUR), `type`.
*   **Category:** `id`, `name`, `description` (Semantic instructions).
*   **Transaction:** `id`, `account_id`, `raw_description`, `amount_original`, `currency_original`, `amount_base`, `category_id`, `status`, `is_internal_transfer`, `sync_status`.

---

## 4. AI & RAG Logic Flow
1.  **Ingestion:** Parse CSV -> PostgreSQL.
2.  **RAG Search:** Create embedding -> Query Qdrant for Top-3 matches.
3.  **Agent Reasoning (Pydantic AI):** 
    *   Check for Internal Transfers.
    *   Research unknown merchants via **Perplexity/DuckDuckGo tool**.
    *   Categorize and return structured JSON.
4.  **Feedback Loop:** User approval -> Vectorize & Sync to Qdrant (Outbox Pattern).

---

## 5. Infrastructure & Security (Raspberry Pi)
*   **Dependency Management:** `uv` will be used to manage `pyproject.toml` and generate lightning-fast Docker builds.
*   **Storage:** External HDD for PostgreSQL and Qdrant data volumes.
*   **Security:** Tailscale VPN (no open ports), SSH keys only, `Fail2Ban`, `Unattended-Upgrades`.

---

## 6. Implementation Roadmap

*   **Phase 1: Local Foundation.** Setup FastAPI skeleton, Auth, and SQLAlchemy models.
*   **Phase 2: Ingestion Logic.** CSV parsing, deduplication, and currency conversion.
*   **Phase 3: AI Intelligence.** Pydantic AI Agent + Perplexity/DuckDuckGo research tools.
*   **Phase 4: Memory & RAG.** Qdrant integration and the Outbox Sync Pattern.
*   **Phase 5: RPi Transition.** Setup OS, Tailscale, HDD, and Docker Compose with `uv`-based builds.
*   **Phase 6: UI & Polish.** Telegram Bot or Web dashboard.
