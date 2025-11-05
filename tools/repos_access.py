#!/usr/bin/env python3
"""
GitLab Repository Access Tool
Fetches all repositories associated with the GitLab API key and stores them in JSON format.
"""

import json
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional
import gitlab
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass

console = Console()


def fetch_all_repositories(gitlab_url: str, access_token: str, include_archived: bool = False, 
                          user_only: bool = False, group_filter: Optional[str] = None) -> List[Dict]:
    """
    Fetch all repositories accessible with the given GitLab access token.
    
    Args:
        gitlab_url: GitLab instance URL (e.g., https://gitlab.com)
        access_token: GitLab personal access token
        include_archived: Whether to include archived repositories
        user_only: If True, only fetch repositories owned by the user (exclude group repos)
        group_filter: If provided, only fetch repositories from this group/namespace (e.g., "mindtickle")
    
    Returns:
        List of dictionaries containing repository information
    """
    # Connect to GitLab
    gl = gitlab.Gitlab(gitlab_url, private_token=access_token)
    
    # Verify authentication
    try:
        gl.auth()
        user = gl.user
        console.print(f"[green]✓[/green] Authenticated as: {user.username} ({user.name})")
        if group_filter:
            console.print(f"[cyan]ℹ[/cyan] Filtering to repositories from group: {group_filter}")
        elif user_only:
            console.print(f"[cyan]ℹ[/cyan] Filtering to only repositories owned by: {user.username}")
        console.print()
    except Exception as e:
        console.print(f"[red]✗ Authentication failed: {e}[/red]")
        raise
    
    repositories = []
    user_username = user.username
    
    # Fetch all projects the user has access to
    # Use pagination to show progress as we go
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Fetching repositories...", total=None)
        
        try:
            # Fetch projects page by page to show progress
            page = 1
            per_page = 100
            total_fetched = 0
            total_processed = 0
            
            while True:
                filter_desc = group_filter if group_filter else ("user repos" if user_only else "repos")
                progress.update(task, description=f"[cyan]Fetching page {page}... (found {total_fetched} {filter_desc}, processed {total_processed} total)")
                
                # Fetch one page at a time
                projects = gl.projects.list(
                    page=page,
                    per_page=per_page,
                    archived=include_archived,
                    order_by='last_activity_at',
                    sort='desc'
                )
                
                if not projects:
                    break
                
                # Process projects from this page
                for project in projects:
                    total_processed += 1
                    
                    try:
                        # Get namespace information
                        namespace = project.namespace
                        if isinstance(namespace, dict):
                            namespace_kind = namespace.get("kind", "")
                            namespace_path = namespace.get("path", "")
                        else:
                            namespace_kind = getattr(namespace, "kind", "")
                            namespace_path = getattr(namespace, "path", "")
                        
                        # Apply filters
                        should_include = True
                        
                        if group_filter:
                            # Filter by group/namespace: check if path starts with or equals the group name
                            # Handles both "mindtickle" and "mindtickle/subgroup" cases
                            if namespace_path != group_filter and not namespace_path.startswith(f"{group_filter}/"):
                                should_include = False
                        
                        elif user_only:
                            # Only include if namespace is "user" type and path matches user's username
                            if namespace_kind != "user" or namespace_path != user_username:
                                should_include = False
                        
                        if not should_include:
                            continue  # Skip this repository
                        
                        # Get detailed project information
                        repo_data = {
                            "id": project.id,
                            "name": project.name,
                            "path": project.path,
                            "path_with_namespace": project.path_with_namespace,
                            "description": project.description or "",
                            "default_branch": project.default_branch or "",
                            "visibility": project.visibility,
                            "archived": project.archived,
                            "created_at": project.created_at,
                            "last_activity_at": project.last_activity_at,
                            "web_url": project.web_url,
                            "ssh_url_to_repo": project.ssh_url_to_repo or "",
                            "http_url_to_repo": project.http_url_to_repo or "",
                            "namespace": {
                                "id": namespace.get("id") if isinstance(namespace, dict) else getattr(namespace, "id", None),
                                "name": namespace.get("name") if isinstance(namespace, dict) else getattr(namespace, "name", ""),
                                "path": namespace_path,
                                "kind": namespace_kind,
                            } if namespace else {},
                            "star_count": getattr(project, "star_count", 0),
                            "forks_count": getattr(project, "forks_count", 0),
                            "open_issues_count": getattr(project, "open_issues_count", 0),
                            "merge_requests_count": getattr(project, "merge_requests_count", 0),
                        }
                        
                        repositories.append(repo_data)
                        total_fetched += 1
                    except Exception as e:
                        console.print(f"[yellow]Warning: Could not fetch details for {getattr(project, 'path_with_namespace', 'unknown')}: {e}[/yellow]")
                        # Still add basic info if it passes the filter
                        namespace = project.namespace if hasattr(project, 'namespace') else {}
                        if isinstance(namespace, dict):
                            namespace_kind = namespace.get("kind", "")
                            namespace_path = namespace.get("path", "")
                        else:
                            namespace_kind = getattr(namespace, "kind", "")
                            namespace_path = getattr(namespace, "path", "")
                        
                        # Apply same filters for error cases
                        if group_filter:
                            if namespace_path != group_filter and not namespace_path.startswith(f"{group_filter}/"):
                                continue
                        elif user_only:
                            if namespace_kind != "user" or namespace_path != user_username:
                                continue
                        
                        repositories.append({
                            "id": getattr(project, "id", None),
                            "name": getattr(project, "name", "unknown"),
                            "path_with_namespace": getattr(project, "path_with_namespace", "unknown"),
                            "web_url": getattr(project, "web_url", ""),
                            "error": str(e)
                        })
                        total_fetched += 1
                
                # If we got fewer than per_page, we're on the last page
                if len(projects) < per_page:
                    break
                
                page += 1
            
            if group_filter:
                progress.update(task, description=f"[green]✓ Fetched {total_fetched} repositories from '{group_filter}' (filtered from {total_processed} total)[/green]")
            elif user_only:
                progress.update(task, description=f"[green]✓ Fetched {total_fetched} user-owned repositories (filtered from {total_processed} total)[/green]")
            else:
                progress.update(task, description=f"[green]✓ Fetched {total_fetched} repositories[/green]")
        
        except Exception as e:
            console.print(f"[red]✗ Error fetching repositories: {e}[/red]")
            raise
    
    return repositories


def display_repositories(repositories: List[Dict], limit: int = 20):
    """Display repositories in a formatted table"""
    
    if not repositories:
        console.print("[yellow]No repositories found.[/yellow]")
        return
    
    # Summary table
    summary_table = Table(title="Repository Access Summary", show_header=True, header_style="bold magenta")
    summary_table.add_column("Metric", style="cyan", width=30)
    summary_table.add_column("Value", style="green", width=20)
    
    total_repos = len(repositories)
    archived_count = sum(1 for r in repositories if r.get("archived", False))
    public_count = sum(1 for r in repositories if r.get("visibility") == "public")
    private_count = sum(1 for r in repositories if r.get("visibility") == "private")
    internal_count = sum(1 for r in repositories if r.get("visibility") == "internal")
    
    summary_table.add_row("Total Repositories", str(total_repos))
    summary_table.add_row("Archived", str(archived_count))
    summary_table.add_row("Public", str(public_count))
    summary_table.add_row("Private", str(private_count))
    summary_table.add_row("Internal", str(internal_count))
    summary_table.add_row("Active", str(total_repos - archived_count))
    
    console.print(summary_table)
    console.print()
    
    # Repositories table (limited)
    repos_table = Table(title=f"Repositories (showing first {min(limit, len(repositories))} of {total_repos})", 
                       show_header=True, header_style="bold blue")
    repos_table.add_column("Name", style="cyan", width=40)
    repos_table.add_column("Visibility", style="yellow", width=12)
    repos_table.add_column("Default Branch", style="green", width=15)
    repos_table.add_column("Archived", style="red", width=10)
    repos_table.add_column("Last Activity", style="dim", width=20)
    
    for repo in repositories[:limit]:
        visibility = repo.get("visibility", "unknown")
        archived = "✓" if repo.get("archived", False) else "✗"
        default_branch = repo.get("default_branch", "N/A")
        last_activity = repo.get("last_activity_at", "")
        
        # Format last activity date
        if last_activity:
            try:
                # Parse ISO format and show relative time
                dt = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))
                last_activity = dt.strftime("%Y-%m-%d")
            except:
                pass
        
        repos_table.add_row(
            repo.get("path_with_namespace", "N/A"),
            visibility,
            default_branch,
            archived,
            last_activity
        )
    
    console.print(repos_table)
    
    if len(repositories) > limit:
        console.print()
        console.print(f"[dim]... and {len(repositories) - limit} more repositories (see JSON file for full list)[/dim]")


def save_repositories_json(repositories: List[Dict], output_file: str):
    """Save repositories to JSON file"""
    
    output_data = {
        "metadata": {
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "total_repositories": len(repositories),
            "gitlab_instance": "https://gitlab.com"  # Will be updated from env
        },
        "repositories": repositories
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    console.print(f"[green]✓[/green] Repositories saved to: {output_file}")
    console.print(f"[dim]Total repositories: {len(repositories)}[/dim]")


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
    
    # Check if user wants to include archived repositories
    include_archived = os.getenv('INCLUDE_ARCHIVED', 'false').lower() == 'true'
    user_only = os.getenv('USER_ONLY', 'false').lower() == 'true'  # Default to False
    group_filter = os.getenv('GROUP_FILTER', None)  # Can be set via env var
    
    # Parse command line arguments
    if '--include-archived' in sys.argv:
        include_archived = True
    if '--all-repos' in sys.argv or '--include-groups' in sys.argv:
        user_only = False
        group_filter = None
        console.print("[yellow]Warning: Including all repositories (including group repos)[/yellow]")
    if '--user-only' in sys.argv:
        user_only = True
        group_filter = None
    
    # Check for --group argument
    if '--group' in sys.argv:
        idx = sys.argv.index('--group')
        if idx + 1 < len(sys.argv):
            group_filter = sys.argv[idx + 1]
            user_only = False
        else:
            console.print("[red]Error: --group requires a group name (e.g., --group mindtickle)[/red]")
            sys.exit(1)
    
    # Ensure data directory exists
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    output_file = os.path.join(data_dir, 'repos_access.json')
    
    try:
        console.print(f"[bold]Fetching repositories from GitLab...[/bold]")
        console.print(f"[cyan]GitLab URL:[/cyan] {gitlab_url}")
        if include_archived:
            console.print("[yellow]Including archived repositories[/yellow]")
        if group_filter:
            console.print(f"[cyan]Filter: Repositories from group '{group_filter}' only[/cyan]")
        elif user_only:
            console.print("[cyan]Filter: User-owned repositories only (excluding group repos)[/cyan]")
        console.print()
        
        repositories = fetch_all_repositories(gitlab_url, access_token, include_archived, user_only, group_filter)
        
        if not repositories:
            console.print("[yellow]No repositories found.[/yellow]")
            sys.exit(0)
        
        console.print()
        display_repositories(repositories)
        console.print()
        
        # Update metadata with actual GitLab URL
        output_data = {
            "metadata": {
                "fetched_at": datetime.utcnow().isoformat() + "Z",
                "total_repositories": len(repositories),
                "gitlab_instance": gitlab_url,
                "include_archived": include_archived,
                "user_only": user_only,
                "group_filter": group_filter
            },
            "repositories": repositories
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        console.print()
        console.print(f"[green]✓[/green] Repositories saved to: {output_file}")
        console.print(f"[dim]Total repositories: {len(repositories)}[/dim]")
        console.print()
        console.print("[yellow]Note:[/yellow] This file contains all repositories you have access to.")
        console.print("[yellow]Privacy:[/yellow] The file is saved locally and will not be committed (gitignored).")
        
    except gitlab.exceptions.GitlabAuthenticationError:
        console.print("[red]✗ Authentication failed. Check your access token.[/red]")
        sys.exit(1)
    except gitlab.exceptions.GitlabError as e:
        console.print(f"[red]✗ GitLab API error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    main()

