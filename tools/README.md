# Tools - PR Data Extractor

This directory contains tools for extracting data from GitLab Merge Requests to create bug documentation for Project Cosmos.

## 🔒 Privacy & Security

**IMPORTANT**: All sensitive data is gitignored and will NOT be published:

- **`.env` files** - Contains your GitLab API token (gitignored)
- **`tools/data/*.json`** - All extracted PR data and bug documents (gitignored)
- **Never commit sensitive tokens or extracted data to the repository**

Your extracted data remains local and private. Only schema files and tooling code are version-controlled.

## Setup

1. **Install dependencies:**
```bash
cd tools
pip install -r requirements.txt
```

2. **Configure GitLab token** (choose one method):

   **Option A: Use setup script (recommended)**
   ```bash
   bash setup_env.sh
   ```
   This creates a `.env` file with your token (gitignored).

   **Option B: Manual setup**
   ```bash
   export GITLAB_TOKEN=glpat-xxxxx
   ```
   
   **Option C: Create `.env` file manually**
   ```bash
   echo "GITLAB_TOKEN=glpat-xxxxx" > .env
   ```
   The `.env` file is automatically loaded if `python-dotenv` is installed.

## Tools

### extract_pr_data.py

Extracts necessary data from a GitLab Merge Request (PR) for bug document creation.

#### Usage

The tool uses environment variables for configuration and accepts a PR URL:

```bash
python extract_pr_data.py [pr_url]
```

#### Environment Variables (Required)

- `GITLAB_TOKEN` - GitLab personal access token (create at: GitLab Settings → Access Tokens)
  - **Required**: Must be set before running the tool

#### Environment Variables (Optional)

- `GITLAB_URL` - GitLab instance URL (default: `https://gitlab.com`)
  - Only needed for self-hosted GitLab instances
- `GITLAB_PR_URL` - PR URL to extract (alternative to command line argument)

#### Configuration Methods (in priority order)

1. **Command line argument** (highest priority):
   ```bash
   python extract_pr_data.py https://gitlab.com/group/project/-/merge_requests/123
   ```

2. **Environment variable**:
   ```bash
   export GITLAB_PR_URL="https://gitlab.com/group/project/-/merge_requests/123"
   python extract_pr_data.py
   ```

3. **Hardcoded in script** (lowest priority):
   - Edit `PR_URL` variable at the top of `extract_pr_data.py`

#### Supported URL Formats

- **Merge Request URL**:
  ```
  https://gitlab.com/group/project/-/merge_requests/123
  ```

- **Commit URL** (will try to find the MR containing the commit):
  ```
  https://gitlab.com/group/project/-/commit/abc123def456...
  ```

#### Example

```bash
# Set environment variable
export GITLAB_TOKEN=glpat-xxxxx

# Extract from MR URL
python extract_pr_data.py https://gitlab.com/group/project/-/merge_requests/123

# Or extract from commit URL
python extract_pr_data.py https://gitlab.com/group/project/-/commit/abc123def456...
```

#### Output

The tool will:
1. Display extracted data in a formatted table
2. Save extracted data to `data/extracted_data_mr_{mr_iid}.json`

#### Extracted Data

The tool extracts the following fields from the PR:

**Auto-extracted (fully automated):**
- `ticket_id` - Extracted from PR title/description (pattern: `[A-Z]+-\d+`)
- `created_at_utc` - PR creation timestamp (ISO 8601 UTC format)
- `source_commit_hash` - Merge commit SHA (40 characters)
- `author` - PR author email and name
- `code_diff` - Unified diff from all file changes
- `repo` - Repository name (project path)
- `branch` - Target branch (where PR was merged)
- `state` - `"accepted"` if merged, `"draft"` otherwise
- **`language`** - ✨ **Auto-detected from file extensions** (NEW!)
  - Supports: Kotlin, Swift, Dart, Java, JavaScript, TypeScript, Python, Go, Rust, C/C++, C#, Ruby, PHP
  - Detects the most common language from changed files
  - Mobile-first: Optimized for Android (Kotlin/Java) and iOS (Swift/Objective-C) development

**Additional metadata:**
- MR ID, MR IID
- MR title, description, state
- Source and target branches
- Files changed list
- Commit count
- Labels
- Related tickets (extracted from description)
- Impact scope (auto-generated heuristic)

**Output files:**
- `extracted_data_mr_{mr_iid}.json` - Raw extracted PR data
- `bug_doc_{ticket_id}_{mr_iid}.json` - Bug document in schema format (with auto-detected language)

## Data Directory

All extracted data is saved in the `tools/data/` directory:
- `extracted_data_mr_{mr_iid}.json` - Raw extracted PR data
- `bug_doc_{ticket_id}_{mr_iid}.json` - Bug documents in Project Cosmos schema format

**⚠️ Important**: This directory is gitignored - extracted data will NOT be committed to the repository.

## Auto-Detection Features

### Language Detection

The tool automatically detects programming languages from file extensions:

- **Android**: `.kt` → `kotlin`, `.java` → `java`
- **iOS**: `.swift` → `swift`, `.m`/`.mm` → `objective-c`
- **Flutter**: `.dart` → `dart`
- **Web**: `.js`/`.jsx` → `javascript`, `.ts`/`.tsx` → `typescript`
- **Backend**: `.py` → `python`, `.go` → `go`, `.rs` → `rust`, etc.

The detected language is:
- Displayed in the console output
- Automatically filled in the bug document schema
- Based on the most common language in changed files

### Example Output

```
Auto-Detected Information
┌───────────────────┬──────────┐
│ Field             │ Value    │
├───────────────────┼──────────┤
│ Detected Language │ kotlin   │
└───────────────────┴──────────┘

✓ Bug document (schema format) saved to: bug_doc_MPB-21185_5233.json

ℹ Auto-detected language: kotlin
```

## GitLab Access Token

To create a GitLab Personal Access Token:

1. Go to GitLab Settings → Access Tokens
2. Create a new token with `api` scope (read access)
3. Copy the token (format: `glpat-xxxxx`)
4. Store it securely using `setup_env.sh` or environment variables

For private projects, ensure your token has access to the project.

**Security**: Your token is stored in `.env` file which is gitignored and will not be published.

## Finding MR IID

The MR IID (internal ID) can be found in the Merge Request URL:

```
https://gitlab.com/group/project/-/merge_requests/123
                                                  ^^^ This is the MR IID
```

## Notes & Best Practices

### Usage Tips
- The tool requires network access to your GitLab instance
- Ensure your access token has appropriate permissions
- For self-hosted GitLab, set `GITLAB_URL` environment variable
- Large diffs may take a moment to fetch
- The tool handles missing data gracefully (shows warnings for optional fields)

### Privacy & Data Handling
- ✅ All `.env` files are gitignored (tokens stay local)
- ✅ All `tools/data/*.json` files are gitignored (extracted data stays local)
- ✅ Only tooling code and schemas are version-controlled
- ⚠️ Never commit sensitive tokens or extracted data
- ⚠️ Review extracted data before sharing outside your local environment

### Manual Completion

After extraction, you'll need to manually fill in:
- `problem_details.*` - Problem summary, details, error message, function name, line range
- `analysis_and_solution.*` - Root cause summary, pattern, detailed narrative
- `metadata_for_retrieval.tags` - Searchable tags
- `metadata_for_retrieval.severity` - Severity level
- `text_for_embedding` - Text used for vector embeddings

**Note**: The `language` field is now auto-detected! ✨

### Next Steps

After creating bug documents:
1. Review and complete the manually-filled fields
2. Validate against the schema: `schemas/bug-document-schema.json`
3. Use the completed documents for Nebula RAG Pipeline (VectorDB ingestion)
