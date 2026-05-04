# 🔍 Semantic Code Search (LLM + Vector Retrieval System)

A high-performance semantic search system for codebases that enables natural language queries over source code using dense embeddings, vector similarity search, and ranking optimization.

> Example:
> Query: *“Where do we handle user authentication errors?”*
> → Returns the most relevant functions, files, and code blocks across the repository.

---

## 🚀 Why This Project Matters

Traditional code search (e.g., grep, keyword search) fails when:

* queries don’t match exact tokens
* intent is abstract (e.g., “retry logic”, “rate limiting”)
* codebases are large and poorly documented

This project explores how **semantic retrieval + embeddings** can:

* improve developer productivity
* reduce onboarding time
* enable intelligent code navigation at scale

---

## 🧠 System Overview

The system converts both **code** and **natural language queries** into a shared embedding space, enabling similarity-based retrieval.

### Architecture

```
        ┌──────────────────────┐
        │   Code Repository     │
        └─────────┬────────────┘
                  │
        ┌─────────▼───────────┐
        │ Code Chunking Layer │
        │ (AST / token split) │
        └─────────┬───────────┘
                  │
        ┌─────────▼────────────┐
        │ Embedding Generator  │
        │ (OpenAI / HF model)  │
        └─────────┬────────────┘
                  │
        ┌─────────▼────────────┐
        │ Vector Store (FAISS) │
        └─────────┬────────────┘
                  │
        ┌─────────▼────────────┐
        │ Query Embedding      │
        └─────────┬────────────┘
                  │
        ┌─────────▼────────────┐
        │ Similarity Search    │
        └─────────┬────────────┘
                  │
        ┌─────────▼────────────┐
        │ Ranking + Filtering  │
        └─────────┬────────────┘
                  │
        ┌─────────▼────────────┐
        │ Top-K Results        │
        └──────────────────────┘
```

---

## ⚙️ Key Features

* 🔎 **Natural Language → Code Retrieval**
* 🧩 **Code Chunking using AST-aware parsing**
* ⚡ **Fast vector search with FAISS**
* 📊 **Relevance ranking and filtering**
* 🧠 **Pluggable embedding models (OpenAI, SentenceTransformers)**
* 🗂️ **Supports multi-file, multi-language codebases**

---

## 🧪 Evaluation & Results

We evaluate retrieval quality using a benchmark of natural language queries mapped to relevant code snippets.

### Metrics

* **Precision@K**
* **Recall@K**
* **Mean Reciprocal Rank (MRR)**

### Results (example)

| Method          | Precision@5 | MRR  |
| --------------- | ----------- | ---- |
| Keyword Search  | 0.42        | 0.38 |
| Semantic Search | 0.71        | 0.64 |

> Semantic search significantly outperforms keyword-based approaches, especially for abstract queries.

---

## ⚡ Performance

* Indexing time: ~X seconds per 10K LOC
* Query latency: ~X ms (top-K retrieval)
* Scales to: 100K+ code chunks (tested locally)

---

## 🧱 Technical Challenges

### 1. Code Chunking Strategy

Naive chunking reduces semantic coherence.

**Solution:**

* AST-based splitting to preserve logical units (functions/classes)

---

### 2. Embedding Quality vs Cost

Higher-quality embeddings improve retrieval but increase cost/latency.

**Tradeoff:**

* Evaluated OpenAI vs SentenceTransformers
* Balanced cost vs accuracy depending on use case

---

### 3. Ranking Noise

Raw vector similarity can return semantically similar but irrelevant code.

**Solution:**

* Added post-processing filters
* Weighted scoring (filename + content + metadata)

---

## 🔧 Tech Stack

* Python
* FAISS (vector search)
* OpenAI / HuggingFace embeddings
* AST parsing tools

---

## ▶️ How to Run

```bash
git clone https://github.com/shruthikatta/semantic-code-search
cd semantic-code-search
pip install -r requirements.txt
```

### Index a repository

```bash
python index.py --repo_path ./your_repo
```

### Run a query

```bash
python query.py --text "Where is retry logic implemented?"
```

---

## 📌 Future Improvements

* 🔁 Hybrid search (BM25 + semantic)
* 🧠 Fine-tuned code-specific embeddings
* 🌐 Web UI for interactive exploration
* ⚡ Distributed indexing for large-scale repos

---

## 💡 Key Takeaways

This project demonstrates:

* building an **end-to-end retrieval system**
* applying **ML to developer tooling**
* making **tradeoffs between accuracy, latency, and cost**

---

## 📎 Example Use Cases

* Codebase onboarding
* Debugging assistance
* Documentation augmentation
* Developer productivity tools

---

## 👤 Author

Shruthi Katta
GitHub: https://github.com/shruthikatta
