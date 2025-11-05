# Project Cosmos Tools

Tools for extracting and indexing GitLab data for Project Cosmos bug documentation system.

## 🔒 Privacy & Security

**CRITICAL**: All sensitive data is gitignored and will NOT be committed:

- ✅ `.env` files (GitLab tokens) - **gitignored**
- ✅ `tools/data/*.json` (all extracted/indexed data) - **gitignored**
- ✅ Only tooling code and schemas are version-controlled
- ⚠️ **Never commit tokens, extracted PR data, or indexed codebases**

## Quick Setup

1. **Install dependencies:**
   ```bash
   cd tools
   pip install -r requirements.txt
   ```

2. **Set GitLab token:**
   ```bash
   export GITLAB_TOKEN=glpat-xxxxx
   # Or create tools/.env file (gitignored)
   ```

## Tools

### `index_repo.py` - Codebase Indexer

**Indexes repositories with AST parsing for fast "find all usages" queries.**

#### Features
- 🔍 **Inverted Index**: O(1) symbol lookups without storing full codebase
- 📊 **AST Parsing**: Tracks functions, classes, variables, imports, and calls
- 🎯 **Scope-Aware**: Resolves qualified names (e.g., `ClassName.method_name`)
- 📈 **Graph Structure**: Relationship traversal between code elements
- 🧹 **Auto Cleanup**: Temporary clones removed after indexing

#### Usage
```bash
# Index default repository (sage)
python index_repo.py

# Index specific repository
python index_repo.py https://gitlab.com/group/project

# Environment variable
export REPO_URL="https://gitlab.com/group/project"
python index_repo.py
```

#### What Gets Indexed
- **File Structure**: Paths, sizes, languages, extensions
- **Python Symbols**: Functions, classes, variables with scoping
- **Code Relationships**: Calls, imports, definitions
- **Inverted Index**: Fast lookup structure (symbol → all usages)
- **Graph**: Relationship network for traversal

#### Output
Saves to `data/indexed_code_{group}_{repo}.json` with:
- File/directory structure
- Symbol definitions and usages
- Inverted index for O(1) queries
- Graph structure for relationships
- **No source code stored** - only metadata

#### Query Functions
```python
from index_repo import find_all_usages, find_symbol_by_qualified_name, find_variable_usages

# Load indexed data
import json
with open('data/indexed_code_mindtickle_sage.json') as f:
    data = json.load(f)

# Find all usages of a function (O(1) lookup)
result = find_all_usages(data, "function_name")
print(f"Found {result['total_usages']} usages")

# Find by qualified name
results = find_symbol_by_qualified_name(data, "ClassName.method_name")

# Find variable usages
var_info = find_variable_usages(data, "variable_name")
```

---

### `repos_access.py` - Repository Fetcher

Fetches all repositories accessible with your GitLab token.

#### Usage
```bash
# All repositories
python repos_access.py

# Filter by group
python repos_access.py --group mindtickle

# Include archived
python repos_access.py --include-archived
```

#### Output
Saves to `data/repos_access.json` with repository metadata (names, paths, visibility, URLs).

---

### `extract_pr_data.py` - PR Data Extractor

Extracts Merge Request data for bug document creation.

#### Usage
```bash
python extract_pr_data.py https://gitlab.com/group/project/-/merge_requests/123
```

#### Extracted Data
- Auto-extracted: Ticket ID, commit hash, author, code diff, language
- Metadata: MR details, files changed, labels, related tickets
- Output: `data/extracted_data_mr_{iid}.json` and `data/bug_doc_{ticket}_{iid}.json`

---

## Data Directory

All outputs saved to `tools/data/` (gitignored):
- `indexed_code_{group}_{repo}.json` - Indexed codebase structures
- `repos_access.json` - Repository listings
- `extracted_data_mr_{iid}.json` - PR extraction data
- `bug_doc_{ticket}_{iid}.json` - Bug documents

**⚠️ All data files are gitignored - they will NOT be committed.**

## Requirements

- Python 3.8+
- `git` (for cloning repositories)
- GitLab Personal Access Token with `api` scope

## Security Checklist

Before committing:
- ✅ No `.env` files in repo
- ✅ No `tools/data/*.json` files in repo
- ✅ No tokens in code or config files
- ✅ Only tooling code and schemas are tracked
