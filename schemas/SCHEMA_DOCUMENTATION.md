# Cosmos Bug Document Schema Documentation

## Overview

This document describes the standardized JSON schema used for documenting bug fixes and root cause analysis in Project Cosmos. All bug documents stored in the VectorDB must conform to this schema to ensure consistent retrieval and embedding generation.

## Schema Version

**Current Version**: `1.0.0`

## Document Structure

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | ✅ | Version of the schema (e.g., "1.0.0") |
| `document_id` | string | ✅ | Unique identifier (UUID format) |
| `ticket_id` | string | ✅ | Ticket/issue ID (e.g., "PAY-451") |
| `created_at_utc` | string (ISO 8601) | ✅ | Creation timestamp |
| `source_commit_hash` | string | ✅ | Git commit hash (40 chars) |
| `author` | string (email) | ✅ | Developer email |
| `problem_details` | object | ✅ | Problem description |
| `analysis_and_solution` | object | ✅ | RCA and fix details |
| `metadata_for_retrieval` | object | ✅ | Search/tagging metadata |
| `text_for_embedding` | string | ✅ | Text for vector embeddings |

---

### 1. Problem Details (`problem_details`)

Describes the bug/problem that was encountered and fixed.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `problem_summary` | string | ✅ | One-line summary (10-200 chars) |
| `detail_problem` | string | ✅ | Detailed problem description (50+ chars) |
| `error_message` | string | ✅ | Exact error/exception message (5+ chars) |
| `source_file` | string | ✅ | Path to source file |
| `function_name` | string | ✅ | Function/method name |
| `line_range` | string | ✅ | Line number(s) (e.g., "182" or "180-230") |
| `full_stack_trace` | string | ❌ | Complete stack trace (optional) |

**Example:**
```json
{
  "problem_summary": "TypeError when accessing 'id' property of undefined 'req.user' object.",
  "detail_problem": "The 'handlePayment' function at line 182 directly accessed `req.user.id` assuming the 'user' object would always be present...",
  "error_message": "TypeError: Cannot read property 'id' of undefined",
  "source_file": "src/payments/handler.js",
  "function_name": "handlePayment",
  "line_range": "180-230",
  "full_stack_trace": "TypeError: Cannot read property 'id' of undefined\n    at handlePayment (src/payments/handler.js:182:25)..."
}
```

---

### 2. Analysis and Solution (`analysis_and_solution`)

Contains root cause analysis and the implemented solution.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `summary` | string | ✅ | Brief summary of RCA and solution (20-300 chars) |
| `root_cause_pattern` | string | ✅ | Categorized pattern (e.g., "Missing Guard Clause / Null Check") |
| `detailed_solution_narrative` | string | ✅ | Comprehensive narrative (100+ chars) |
| `code_diff` | string | ✅ | Unified diff format showing the fix |

**Root Cause Patterns** (Common Examples):
- `Missing Guard Clause / Null Check`
- `Race Condition`
- `Type Error`
- `Authentication / Authorization Issue`
- `Memory Leak`
- `Infinite Loop`
- `Deadlock`
- `API Contract Violation`
- `Data Validation Issue`
- `Concurrency Issue`

**Example:**
```json
{
  "summary": "A TypeError occurred in the payment handler because the 'req.user' object was accessed before it was verified to exist...",
  "root_cause_pattern": "Missing Guard Clause / Null Check",
  "detailed_solution_narrative": "The code at line 182 attempted to access 'req.user.id' directly...",
  "code_diff": "--- a/src/payments/handler.js\n+++ b/src/payments/handler.js\n@@ -181,1 +181,2 @@\n+  if (!req.user) { return res.status(401).send('Unauthorized'); }\n   const userId = req.user.id;"
}
```

---

### 3. Metadata for Retrieval (`metadata_for_retrieval`)

Metadata used for semantic search, tagging, and retrieval in the VectorDB.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repo` | string | ✅ | Repository name |
| `branch` | string | ❌ | Git branch (optional) |
| `language` | string | ✅ | Programming language (enum) |
| `tags` | array[string] | ✅ | Searchable tags (1+ required) |
| `state` | string | ❌ | Ticket state (enum: open, in-progress, resolved, accepted, rejected, deferred) |
| `severity` | string | ❌ | Severity level (enum: critical, high, medium, low, info) |
| `impact_scope` | string | ❌ | Impact scope (e.g., "api-gateway") |
| `related_tickets` | array[string] | ❌ | Related ticket IDs |
| `embedding_type` | string | ✅ | Embedding type identifier (e.g., "cosmos_v1_bugdoc") |

**Supported Languages:**
- `javascript`
- `typescript`
- `python`
- `java`
- `go`
- `rust`
- `cpp`
- `csharp`
- `ruby`
- `php`
- `other`

**Example:**
```json
{
  "repo": "payments-service",
  "branch": "main",
  "language": "javascript",
  "tags": ["TypeError", "auth", "guard-clause", "payments-service", "req.user"],
  "state": "accepted",
  "severity": "critical",
  "impact_scope": "api-gateway",
  "related_tickets": ["PAY-301", "AUTH-112"],
  "embedding_type": "cosmos_v1_bugdoc"
}
```

---

### 4. Text for Embedding (`text_for_embedding`)

This field contains concatenated text from all relevant fields, used for generating vector embeddings. It should include:

- Problem summary and details
- Error message
- Root cause pattern
- Solution narrative
- Relevant tags

**Best Practices:**
- Include all searchable/relevant text
- Use natural language
- Maintain context and relationships
- Keep it concise but comprehensive (100+ characters)
- Separate sections with newlines or special markers if needed

**Example:**
```
TypeError when accessing 'id' property of undefined 'req.user' object.
The 'handlePayment' function at line 182 directly accessed `req.user.id` assuming the 'user' object would always be present...
TypeError: Cannot read property 'id' of undefined
handlePayment
Missing Guard Clause / Null Check
A TypeError occurred in the payment handler because the 'req.user' object was accessed before it was verified to exist...
The code at line 182 attempted to access 'req.user.id' directly...
TypeError auth guard-clause payments-service req.user File
```

---

## Validation

Documents should be validated against the JSON Schema before being stored in the VectorDB. Use the schema file:
- `schemas/bug-document-schema.json`

### Validation Tools

- **Python**: Use `jsonschema` library
- **Go**: Use `github.com/xeipuuv/gojsonschema`
- **Node.js**: Use `(-validator)` or `ajv`

### Example Validation (Python)

```python
import json
import jsonschema

with open('schemas/bug-document-schema.json') as f:
    schema = json.load(f)

with open('examples/PAY-451.json') as f:
    document = json.load(f)

jsonschema.validate(instance=document, schema=schema)
```

---

## Usage in Project Cosmos

### When to Create a Document

Create a bug document when:
1. A bug is resolved and the fix is merged
2. Root cause analysis is complete
3. The solution is tested and verified
4. The fix adds value to the knowledge base

### Where Documents Are Stored

- Documents are stored in the VectorDB (via Nebula RAG Pipeline)
- Used for semantic similarity search
- Retrieved when similar bugs are encountered
- Continuously enriched as more bugs are resolved

### Workflow

1. Developer fixes a bug and creates a merge request
2. After merge, document is created using this schema
3. Document is validated against schema
4. Embedding is generated from `text_for_embedding`
5. Document + embedding stored in VectorDB
6. Available for future retrieval and similarity matching

---

## Version History

- **v1.0.0** (2025-10-29): Initial schema release

---

## References

- [JSON Schema Specification](https://json-schema.org/)
- [ISO 8601 Date Format](https://en.wikipedia.org/wiki/ISO_8601)
- [Unified Diff Format](https://en.wikipedia.org/wiki/Diff#Unified_format)

