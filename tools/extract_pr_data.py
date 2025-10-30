#!/usr/bin/env python3
"""
GitLab PR Data Extractor
Extracts necessary data from GitLab Merge Request for bug document creation.
"""

import re
import json
import sys
import os
import uuid
from urllib.parse import urlparse
from datetime import datetime
from typing import Dict, Optional, List, Tuple
import gitlab
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass

console = Console()

# Hardcoded PR URL - Update this with the PR you want to extract (optional, lowest priority)
# Format: https://gitlab.com/{namespace}/{project}/-/merge_requests/{mr_iid}
# Or provide via command line argument or GITLAB_PR_URL environment variable
PR_URL = "https://gitlab.com/group/project/-/merge_requests/123"  # Dummy example - update or use command line/env variable


def extract_ticket_id(title: str, description: str) -> Optional[str]:
    """Extract ticket ID from PR title or description (pattern: [A-Z]+-\d+)"""
    pattern = r'([A-Z]+-\d+)'
    
    # Try title first
    match = re.search(pattern, title)
    if match:
        return match.group(1)
    
    # Try description
    if description:
        match = re.search(pattern, description)
        if match:
            return match.group(1)
    
    return None


def extract_related_tickets(text: str) -> List[str]:
    """Extract related ticket IDs from description/comments"""
    if not text:
        return []
    pattern = r'([A-Z]+-\d+)'
    matches = re.findall(pattern, text)
    return list(set(matches))  # Remove duplicates


def format_datetime(dt_str: str) -> str:
    """Convert GitLab datetime to ISO 8601 UTC format"""
    if not dt_str:
        return ""
    # GitLab returns ISO 8601 format, ensure UTC
    if dt_str.endswith('Z'):
        return dt_str
    # Add Z if missing timezone
    return dt_str.replace('+00:00', 'Z').replace('-00:00', 'Z')


def get_merge_commit_hash(mr) -> Optional[str]:
    """Get merge commit hash from MR"""
    if hasattr(mr, 'merge_commit_sha') and mr.merge_commit_sha:
        return mr.merge_commit_sha
    
    # Fallback to last commit
    try:
        commits = mr.commits()
        if commits and len(commits) > 0:
            return commits[-1].id
    except:
        pass
    
    return None


def get_author_name(mr) -> Optional[str]:
    """Get author name from MR"""
    # Try MR author first
    try:
        if hasattr(mr, 'author') and mr.author:
            # Method 1: Direct name attribute
            if hasattr(mr.author, 'name') and mr.author.name:
                return mr.author.name
            
            # Method 2: Dict access
            if isinstance(mr.author, dict) and 'name' in mr.author:
                return mr.author['name']
            
            # Method 3: Try to fetch user details via API
            if hasattr(mr.author, 'id') and mr.author.id:
                try:
                    user = mr.manager.gl.users.get(mr.author.id)
                    if hasattr(user, 'name') and user.name:
                        return user.name
                    if hasattr(user, 'username') and user.username:
                        return user.username  # Fallback to username
                except:
                    pass
    except Exception as e:
        console.print(f"[dim]Debug: Could not get author name from MR: {e}[/dim]")
    
    # Fallback: Try commit authors
    try:
        commits = mr.commits()
        if commits and len(commits) > 0:
            for commit in commits:
                if hasattr(commit, 'author_name') and commit.author_name:
                    return commit.author_name
                if isinstance(commit, dict) and 'author_name' in commit:
                    return commit['author_name']
                
                # Try detailed commit object
                try:
                    commit_obj = mr.project.commits.get(commit.id)
                    if hasattr(commit_obj, 'author_name') and commit_obj.author_name:
                        return commit_obj.author_name
                    if hasattr(commit_obj, 'author') and commit_obj.author:
                        if hasattr(commit_obj.author, 'name') and commit_obj.author.name:
                            return commit_obj.author.name
                except:
                    continue
    except:
        pass
    
    return None


def get_author_email(mr) -> Optional[str]:
    """Get author email from MR"""
    # Try MR author first - multiple methods
    try:
        if hasattr(mr, 'author') and mr.author:
            # Method 1: Direct email attribute
            if hasattr(mr.author, 'email') and mr.author.email:
                return mr.author.email
            
            # Method 2: Dict access
            if isinstance(mr.author, dict) and 'email' in mr.author:
                return mr.author['email']
            
            # Method 3: Try public_email
            if hasattr(mr.author, 'public_email') and mr.author.public_email:
                return mr.author.public_email
            
            # Method 4: Try to fetch user details via API
            if hasattr(mr.author, 'id') and mr.author.id:
                try:
                    user = mr.manager.gl.users.get(mr.author.id)
                    if hasattr(user, 'email') and user.email:
                        return user.email
                    if hasattr(user, 'public_email') and user.public_email:
                        return user.public_email
                except:
                    pass
    except Exception as e:
        console.print(f"[dim]Debug: Could not get author from MR: {e}[/dim]")
    
    # Fallback: Try merge commit author
    try:
        commits = mr.commits()
        if commits and len(commits) > 0:
            # Try all commits, not just first one
            for commit in commits:
                # Try different ways to access email
                if hasattr(commit, 'author_email') and commit.author_email:
                    return commit.author_email
                if isinstance(commit, dict):
                    if 'author_email' in commit:
                        return commit['author_email']
                    if 'author' in commit and isinstance(commit['author'], dict):
                        if 'email' in commit['author']:
                            return commit['author']['email']
                
                # Try accessing through detailed commit object
                try:
                    commit_obj = mr.project.commits.get(commit.id)
                    if hasattr(commit_obj, 'author_email') and commit_obj.author_email:
                        return commit_obj.author_email
                    if hasattr(commit_obj, 'author') and commit_obj.author:
                        if hasattr(commit_obj.author, 'email') and commit_obj.author.email:
                            return commit_obj.author.email
                except:
                    continue
    except Exception as e:
        console.print(f"[dim]Debug: Could not get author from commits: {e}[/dim]")
    
    # Last resort: Try MR opened_by
    try:
        if hasattr(mr, 'opened_by') and mr.opened_by:
            if hasattr(mr.opened_by, 'email') and mr.opened_by.email:
                return mr.opened_by.email
            if isinstance(mr.opened_by, dict) and 'email' in mr.opened_by:
                return mr.opened_by['email']
    except:
        pass
    
    return None


def get_code_diff(mr) -> str:
    """Get unified diff from MR changes"""
    try:
        changes = mr.changes()
        diff_parts = []
        
        for change in changes.get('changes', []):
            old_path = change.get('old_path', '')
            new_path = change.get('new_path', '')
            diff_content = change.get('diff', '')
            
            if diff_content:
                # Format as unified diff
                diff_parts.append(f"--- a/{old_path}\n+++ b/{new_path}\n{diff_content}")
        
        return "\n".join(diff_parts)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not fetch diff: {e}[/yellow]")
        return ""


def get_repo_name(project) -> str:
    """Extract repository name from project"""
    if hasattr(project, 'path_with_namespace'):
        return project.path_with_namespace
    elif hasattr(project, 'name'):
        return project.name
    return "unknown"


def parse_gitlab_url(url: str) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[str]]:
    """
    Parse GitLab URL to extract instance URL, project path, MR IID, and commit hash
    
    Supports:
    - MR URL: https://gitlab.com/group/project/-/merge_requests/123
    - Commit URL: https://gitlab.com/group/project/-/commit/abc123
    
    Returns:
        (gitlab_url, project_path, mr_iid, commit_hash)
    """
    try:
        parsed = urlparse(url)
        gitlab_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Extract project path and MR/commit info from path
        path_parts = parsed.path.strip('/').split('/')
        
        # Find the index of '-'
        try:
            dash_index = path_parts.index('-')
            project_path = '/'.join(path_parts[:dash_index])
            
            # Check what comes after '-'
            if dash_index + 1 < len(path_parts):
                resource_type = path_parts[dash_index + 1]
                
                if resource_type == 'merge_requests' and dash_index + 2 < len(path_parts):
                    mr_iid = int(path_parts[dash_index + 2])
                    return (gitlab_url, project_path, mr_iid, None)
                elif resource_type == 'commit' and dash_index + 2 < len(path_parts):
                    commit_hash = path_parts[dash_index + 2]
                    return (gitlab_url, project_path, None, commit_hash)
        except (ValueError, IndexError):
            pass
        
        # If we can't parse properly, try to extract project path manually
        # This handles URLs like: https://gitlab.com/group/project
        if len(path_parts) >= 2:
            project_path = '/'.join(path_parts[:2])
            return (gitlab_url, project_path, None, None)
            
    except Exception as e:
        console.print(f"[yellow]Warning: Could not parse URL properly: {e}[/yellow]")
    
    return (None, None, None, None)


def extract_pr_data(gitlab_url: str, access_token: str, project_id: str, mr_iid: int) -> Dict:
    """
    Extract all necessary data from GitLab Merge Request
    
    Args:
        gitlab_url: GitLab instance URL (e.g., https://gitlab.com)
        access_token: GitLab personal access token
        project_id: Project ID or path (e.g., "12345" or "group/project")
        mr_iid: Merge Request IID (internal ID within project)
    
    Returns:
        Dictionary with extracted data
    """
    # Connect to GitLab
    gl = gitlab.Gitlab(gitlab_url, private_token=access_token)
    project = gl.projects.get(project_id)
    mr = project.mergerequests.get(mr_iid)
    
    # Extract ticket ID
    ticket_id = extract_ticket_id(mr.title, mr.description or "")
    
    # Extract related tickets
    description_text = mr.description or ""
    related_tickets = extract_related_tickets(description_text)
    if ticket_id and ticket_id in related_tickets:
        related_tickets.remove(ticket_id)  # Remove main ticket from related
    
    # Extract commit hash
    commit_hash = get_merge_commit_hash(mr)
    
    # Extract author email and name
    author_email = get_author_email(mr)
    author_name = get_author_name(mr)
    
    # Get code diff
    code_diff = get_code_diff(mr)
    
    # Determine state
    state = "accepted" if mr.state == "merged" else "draft"
    
    # Extract repo name
    repo_name = get_repo_name(project)
    
    # Get files changed
    files_changed = []
    try:
        changes = mr.changes()
        for change in changes.get('changes', []):
            files_changed.append({
                'old_path': change.get('old_path'),
                'new_path': change.get('new_path'),
                'diff': change.get('diff', '')[:500] + "..." if len(change.get('diff', '')) > 500 else change.get('diff', '')
            })
    except Exception as e:
        console.print(f"[yellow]Warning: Could not fetch file changes: {e}[/yellow]")
    
    # Get commit count
    commits_count = 0
    try:
        commits = list(mr.commits())
        commits_count = len(commits)
    except:
        pass
    
    # Compile extracted data
    extracted_data = {
        "ticket_id": ticket_id,
        "created_at_utc": format_datetime(mr.created_at),
        "source_commit_hash": commit_hash,
        "author": author_email,
        "author_name": author_name,
        "code_diff": code_diff,
        "repo": repo_name,
        "branch": mr.target_branch,
        "state": state,
        "metadata": {
            "mr_id": mr.id,
            "mr_iid": mr.iid,
            "mr_title": mr.title,
            "mr_description": mr.description,
            "mr_state": mr.state,
            "source_branch": mr.source_branch,
            "target_branch": mr.target_branch,
            "merged_at": format_datetime(mr.merged_at) if hasattr(mr, 'merged_at') and mr.merged_at else None,
            "labels": mr.labels if hasattr(mr, 'labels') else [],
            "files_changed": files_changed,
            "files_count": len(files_changed),
            "related_tickets": related_tickets,
            "commits_count": commits_count
        }
    }
    
    return extracted_data


def display_extracted_data(data: Dict):
    """Display extracted data in a nice format"""
    
    # Main extraction table
    table = Table(title="Extracted PR Data", show_header=True, header_style="bold magenta")
    table.add_column("Field", style="cyan", width=25)
    table.add_column("Value", style="green", width=50)
    
    table.add_row("Ticket ID", data.get("ticket_id") or "[yellow]Not found[/yellow]")
    table.add_row("Created At (UTC)", data.get("created_at_utc", "N/A"))
    table.add_row("Source Commit Hash", data.get("source_commit_hash", "N/A"))
    table.add_row("Author Name", data.get("author_name", "N/A"))
    table.add_row("Author Email", data.get("author", "N/A"))
    table.add_row("Repository", data.get("repo", "N/A"))
    table.add_row("Target Branch", data.get("branch", "N/A"))
    table.add_row("State", f"[green]{data.get('state')}[/green]" if data.get('state') == 'accepted' else f"[yellow]{data.get('state')}[/yellow]")
    
    console.print(table)
    console.print()
    
    # Additional metadata
    metadata = data.get("metadata", {})
    meta_table = Table(title="Additional Metadata", show_header=True, header_style="bold blue")
    meta_table.add_column("Field", style="cyan")
    meta_table.add_column("Value", style="white")
    
    meta_table.add_row("MR ID", str(metadata.get("mr_id", "N/A")))
    meta_table.add_row("MR IID", str(metadata.get("mr_iid", "N/A")))
    mr_title = metadata.get("mr_title", "N/A")
    meta_table.add_row("MR Title", mr_title[:60] + "..." if len(mr_title) > 60 else mr_title)
    meta_table.add_row("MR State", metadata.get("mr_state", "N/A"))
    meta_table.add_row("Source Branch", metadata.get("source_branch", "N/A"))
    meta_table.add_row("Files Changed", str(metadata.get("files_count", 0)))
    meta_table.add_row("Commits", str(metadata.get("commits_count", 0)))
    meta_table.add_row("Labels", ", ".join(metadata.get("labels", [])) or "None")
    meta_table.add_row("Related Tickets", ", ".join(metadata.get("related_tickets", [])) or "None")
    
    console.print(meta_table)
    console.print()
    
    # Code diff preview
    code_diff = data.get("code_diff", "")
    if code_diff:
        diff_preview = code_diff[:1000] + "..." if len(code_diff) > 1000 else code_diff
        console.print(Panel(diff_preview, title="Code Diff Preview", border_style="yellow"))
        console.print(f"[dim]Total diff length: {len(code_diff)} characters[/dim]")
        console.print()
    
    # Auto-detect language from files
    files_changed = metadata.get("files_changed", [])
    detected_language = detect_language_from_files(files_changed)
    
    # Language detection display
    if detected_language:
        language_table = Table(title="Auto-Detected Information", show_header=True, header_style="bold cyan")
        language_table.add_column("Field", style="cyan")
        language_table.add_column("Value", style="green")
        language_table.add_row("Detected Language", f"[bold green]{detected_language}[/bold green]")
        console.print(language_table)
        console.print()
    
    # Files changed list
    if files_changed:
        files_table = Table(title="Files Changed", show_header=True, header_style="bold green")
        files_table.add_column("Old Path", style="red")
        files_table.add_column("New Path", style="green")
        
        for file_change in files_changed[:10]:  # Show first 10
            files_table.add_row(
                file_change.get("old_path", "N/A"),
                file_change.get("new_path", "N/A")
            )
        
        if len(files_changed) > 10:
            files_table.add_row("...", f"[dim]and {len(files_changed) - 10} more files[/dim]")
        
        console.print(files_table)


def detect_language_from_files(files_changed: List) -> str:
    """
    Auto-detect programming language from file extensions in changed files.
    Returns the most common language found, or empty string if none detected.
    
    Supported extensions:
    - .kt → kotlin
    - .java → java
    - .swift → swift
    - .m, .mm → objective-c
    - .dart → dart
    - .js, .jsx → javascript
    - .ts, .tsx → typescript
    - .py → python
    - .go → go
    - .rs → rust
    - .cpp, .cc, .cxx → cpp
    - .c → c
    - .cs → csharp
    - .rb → ruby
    - .php → php
    """
    if not files_changed:
        return ""
    
    # Map file extensions to languages (matching schema enum)
    # Single extensions
    extension_to_language = {
        # Android/Mobile
        '.kt': 'kotlin',
        '.java': 'java',
        '.m': 'objective-c',
        '.mm': 'objective-c',
        # iOS
        '.swift': 'swift',
        # Flutter
        '.dart': 'dart',
        # Web/Frontend
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        # Backend
        '.py': 'python',
        '.go': 'go',
        '.rs': 'rust',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.c': 'c',
        '.cs': 'csharp',
        '.rb': 'ruby',
        '.php': 'php',
    }
    
    # Multi-part extensions that should take precedence
    multi_part_extensions = {
        '.d.ts': 'typescript',  # TypeScript declaration files
    }
    
    language_counts = {}
    
    for file_info in files_changed:
        # Try new_path first, fallback to old_path
        file_path = file_info.get('new_path', '') or file_info.get('old_path', '')
        if not file_path:
            continue
        
        # Extract file extension
        if '.' in file_path:
            # Normalize the path (handle case sensitivity)
            file_path_lower = file_path.lower()
            parts = file_path_lower.split('.')
            
            if len(parts) > 1:
                # Check for multi-part extensions first (e.g., .d.ts)
                if len(parts) >= 2:
                    last_two = '.' + '.'.join(parts[-2:])
                    if last_two in multi_part_extensions:
                        lang = multi_part_extensions[last_two]
                        language_counts[lang] = language_counts.get(lang, 0) + 1
                        continue
                
                # Check single extension (handles .jsx, .tsx, .js, .ts, etc.)
                ext = '.' + parts[-1]
                if ext in extension_to_language:
                    lang = extension_to_language[ext]
                    language_counts[lang] = language_counts.get(lang, 0) + 1
    
    # Return the most common language, or empty string if none found
    if language_counts:
        # Sort by count (descending) and return the most common
        sorted_languages = sorted(language_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_languages[0][0]
    
    return ""


def generate_impact_scope(repo: str, files_changed: List) -> str:
    """
    Generate impact_scope based on repo and files changed
    Simple heuristic to determine impact scope
    """
    if not files_changed:
        return "unknown"
    
    # Check file paths for common patterns
    for file_info in files_changed:
        file_path = file_info.get('new_path', '') or file_info.get('old_path', '')
        
        if 'api' in file_path.lower() or 'gateway' in file_path.lower():
            return "api-gateway"
        elif 'database' in file_path.lower() or 'db' in file_path.lower() or 'model' in file_path.lower():
            return "database"
        elif 'frontend' in file_path.lower() or 'ui' in file_path.lower() or 'view' in file_path.lower():
            return "frontend"
        elif 'service' in file_path.lower():
            return "service"
        elif 'auth' in file_path.lower() or 'security' in file_path.lower():
            return "authentication"
        elif 'payment' in file_path.lower():
            return "payment-processing"
    
    # Default based on repo name
    if 'service' in repo.lower():
        return "service"
    elif 'api' in repo.lower():
        return "api-gateway"
    
    return "general"


def transform_to_bug_document(extracted_data: Dict) -> Dict:
    """
    Transform extracted PR data into bug document schema format
    Fills only auto-extracted fields, leaves rest blank for manual entry
    """
    # Generate document ID: doc_{ticket_id}_{uuid}
    ticket_id_val = extracted_data.get("ticket_id", "")
    uuid_part = uuid.uuid4().hex[:12]  # First 12 chars of UUID
    doc_id = f"doc_{ticket_id_val}_{uuid_part}" if ticket_id_val else f"doc_{uuid_part}"
    
    # Get related tickets (already extracted)
    related_tickets = extracted_data.get("metadata", {}).get("related_tickets", [])
    
    # Generate impact scope
    files_changed = extracted_data.get("metadata", {}).get("files_changed", [])
    impact_scope = generate_impact_scope(extracted_data.get("repo", ""), files_changed)
    
    # Auto-detect language from file extensions
    detected_language = detect_language_from_files(files_changed)
    
    # Get first file changed for source_file (can be updated manually)
    source_file = ""
    if files_changed and len(files_changed) > 0:
        source_file = files_changed[0].get('new_path', '') or files_changed[0].get('old_path', '')
    
    # Build bug document structure
    bug_document = {
        "schema_version": "1.0.0",
        "document_id": doc_id,
        "ticket_id": extracted_data.get("ticket_id", ""),
        "created_at_utc": extracted_data.get("created_at_utc", ""),
        "source_commit_hash": extracted_data.get("source_commit_hash", ""),
        "author": extracted_data.get("author", ""),
        "author_name": extracted_data.get("author_name", ""),
        
        "problem_details": {
            "problem_summary": "",  # Manual input
            "detail_problem": "",   # Manual input
            "error_message": "",    # Manual input
            "source_file": source_file,  # First file, can be updated
            "function_name": "",    # Manual input
            "line_range": "",       # Manual input
            "full_stack_trace": ""  # Optional, manual input
        },
        
        "analysis_and_solution": {
            "summary": "",  # Manual input
            "root_cause_pattern": "",  # Manual input
            "detailed_solution_narrative": "",  # Manual input
            "code_diff": extracted_data.get("code_diff", "")  # From PR
        },
        
        "metadata_for_retrieval": {
            "repo": extracted_data.get("repo", ""),
            "branch": extracted_data.get("branch", ""),
            "language": detected_language,  # Auto-detected from file extensions
            "tags": [],      # Manual input
            "state": extracted_data.get("state", "draft"),
            "severity": "",  # Manual input (critical, high, medium, low, info)
            "impact_scope": impact_scope,  # Generated
            "related_tickets": related_tickets,  # Extracted from PR
            "embedding_type": "cosmos_v1_bugdoc"  # Default
        },
        
        "text_for_embedding": ""  # Manual input (will be generated from other fields)
    }
    
    return bug_document


def find_mr_by_commit(gitlab_url: str, access_token: str, project_path: str, commit_hash: str) -> Optional[int]:
    """
    Find Merge Request IID that contains the given commit hash
    """
    try:
        gl = gitlab.Gitlab(gitlab_url, private_token=access_token)
        project = gl.projects.get(project_path)
        
        # Search for MRs that contain this commit
        mrs = project.mergerequests.list(state='all', per_page=100)
        
        for mr in mrs:
            try:
                commits = mr.commits()
                for commit in commits:
                    if commit.id == commit_hash or commit.id.startswith(commit_hash):
                        return mr.iid
            except:
                continue
                
        console.print(f"[yellow]Warning: Could not find MR containing commit {commit_hash}[/yellow]")
        return None
    except Exception as e:
        console.print(f"[yellow]Warning: Error finding MR by commit: {e}[/yellow]")
        return None


def main():
    """Main function"""
    # Get GitLab URL from environment or use default
    gitlab_url = os.getenv('GITLAB_URL', 'https://gitlab.com')
    
    # Get access token from environment (required)
    access_token = os.getenv('GITLAB_TOKEN')
    if not access_token:
        console.print("[red]Error: GITLAB_TOKEN environment variable is required[/red]")
        console.print()
        console.print("[yellow]Set it using:[/yellow]")
        console.print("  export GITLAB_TOKEN=glpat-xxxxx")
        console.print()
        console.print("[yellow]Or create a .env file with:[/yellow]")
        console.print("  GITLAB_TOKEN=glpat-xxxxx")
        sys.exit(1)
    
    # Get PR URL from command line, environment, or use hardcoded
    pr_url = None
    if len(sys.argv) > 1:
        pr_url = sys.argv[1]
    elif os.getenv('GITLAB_PR_URL'):
        pr_url = os.getenv('GITLAB_PR_URL')
    else:
        pr_url = PR_URL
    
    console.print(f"[cyan]Using PR URL:[/cyan] {pr_url}")
    console.print()
    
    # Parse the URL
    parsed_gitlab_url, project_path, mr_iid, commit_hash = parse_gitlab_url(pr_url)
    
    if not parsed_gitlab_url or not project_path:
        console.print("[red]Error: Could not parse GitLab URL[/red]")
        console.print(f"[yellow]URL provided: {pr_url}[/yellow]")
        console.print()
        console.print("[yellow]Expected format:[/yellow]")
        console.print("  https://gitlab.com/group/project/-/merge_requests/123")
        console.print("  or")
        console.print("  https://gitlab.com/group/project/-/commit/abc123")
        sys.exit(1)
    
    # Override gitlab_url if parsed from URL
    gitlab_url = parsed_gitlab_url
    
    # If we have a commit hash but no MR IID, try to find the MR
    if commit_hash and not mr_iid:
        console.print(f"[yellow]Found commit URL, searching for MR containing commit {commit_hash}...[/yellow]")
        mr_iid = find_mr_by_commit(gitlab_url, access_token, project_path, commit_hash)
        if not mr_iid:
            console.print("[red]Error: Could not find MR for the given commit. Please provide an MR URL instead.[/red]")
            sys.exit(1)
    
    if not mr_iid:
        console.print("[red]Error: Could not extract MR IID from URL[/red]")
        console.print(f"[yellow]Please provide a Merge Request URL or commit URL[/yellow]")
        sys.exit(1)
    
    # Ensure data directory exists
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    try:
        console.print(f"[bold]Extracting data from GitLab MR #{mr_iid} in project: {project_path}[/bold]")
        console.print()
        
        data = extract_pr_data(gitlab_url, access_token, project_path, mr_iid)
        
        display_extracted_data(data)
        
        # Save raw extracted data
        raw_output_file = os.path.join(data_dir, f"extracted_data_mr_{mr_iid}.json")
        with open(raw_output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        console.print()
        console.print(f"[green]✓[/green] Raw data saved to: {raw_output_file}")
        
        # Transform to bug document schema format
        bug_document = transform_to_bug_document(data)
        
        # Save bug document (schema format)
        ticket_id = data.get("ticket_id", f"MR-{mr_iid}")
        bug_doc_file = os.path.join(data_dir, f"bug_doc_{ticket_id}_{mr_iid}.json")
        with open(bug_doc_file, 'w') as f:
            json.dump(bug_document, f, indent=2)
        
        console.print(f"[green]✓[/green] Bug document (schema format) saved to: {bug_doc_file}")
        console.print()
        
        # Show detected language in summary
        detected_lang = bug_document.get("metadata_for_retrieval", {}).get("language", "")
        if detected_lang:
            console.print(f"[cyan]ℹ[/cyan] [bold]Auto-detected language:[/bold] [green]{detected_lang}[/green]")
            console.print()
        
        console.print("[yellow]Note:[/yellow] Fill in the blank fields manually:")
        console.print("  - problem_details.*")
        console.print("  - analysis_and_solution.summary, root_cause_pattern, detailed_solution_narrative")
        console.print("  - metadata_for_retrieval.tags, severity (language is auto-detected ✓)")
        console.print("  - text_for_embedding")
        
    except gitlab.exceptions.GitlabAuthenticationError:
        console.print("[red]✗ Authentication failed. Check your access token.[/red]")
        sys.exit(1)
    except gitlab.exceptions.GitlabGetError as e:
        console.print(f"[red]✗ Error fetching MR: {e}[/red]")
        console.print("[yellow]Hint:[/yellow] Check if the project path and mr_iid are correct.")
        console.print(f"[yellow]Project: {project_path}, MR IID: {mr_iid}[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    main()

