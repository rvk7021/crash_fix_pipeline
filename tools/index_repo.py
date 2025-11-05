#!/usr/bin/env python3
"""
GitLab Repository Code-Aware Indexer
Clones a repository, indexes the file structure, and performs deep parsing
on Python files to extract definitions, imports, and function calls.
The indexed structure can be used for future queries without re-cloning.
"""

import json
import sys
import os
import tempfile
import shutil
import ast
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
import subprocess
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass

console = Console()


def get_file_language(file_path: Path) -> str:
    """Detect programming language from file extension"""
    extension_map = {
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
        # Config/Markup
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.xml': 'xml',
        '.html': 'html',
        '.css': 'css',
        '.md': 'markdown',
        '.txt': 'text',
        # Other
        '.sh': 'shell',
        '.bash': 'shell',
        '.zsh': 'shell',
        '.sql': 'sql',
        '.dockerfile': 'dockerfile',
        '.dockerignore': 'dockerignore',
    }
    
    ext = file_path.suffix.lower()
    return extension_map.get(ext, 'unknown')


def should_ignore_path(path: Path, ignore_patterns: List[str]) -> bool:
    """Check if a path should be ignored based on common patterns"""
    path_str = str(path)
    
    # Common ignore patterns
    default_ignores = [
        '.git',
        '.gitignore',
        '.env',
        '.DS_Store',
        '__pycache__',
        'node_modules',
        '.pytest_cache',
        '.mypy_cache',
        'dist',
        'build',
        'target',
        '.idea',
        '.vscode',
        '.gradle',
        '.gradlew',
        '*.pyc',
        '*.class',
        '*.o',
        '*.so',
        '*.dylib',
        '.next',
        '.nuxt',
        '.cache',
    ]
    
    all_patterns = ignore_patterns + default_ignores
    
    for pattern in all_patterns:
        if pattern in path_str or path_str.endswith(pattern):
            return True
    
    return False


class EnhancedPythonSymbolVisitor(ast.NodeVisitor):
    """
    Enhanced AST visitor that tracks scoping, qualified names, variables,
    docstrings, and function bodies for AI-powered code understanding.
    """
    def __init__(self, include_body: bool = True, include_docstrings: bool = True):
        self.definitions = []
        self.calls = []
        self.imports = []
        self.variables = []  # Track variable assignments and usages
        self.scope_stack = []  # Track current scope (class, function)
        self.include_body = include_body  # Whether to include function body text
        self.include_docstrings = include_docstrings  # Whether to include docstrings
    
    def _current_scope(self) -> List[str]:
        """Get current scope path as list"""
        return [s[1] for s in self.scope_stack]
    
    def _get_qualified_name(self, name: str) -> str:
        """Build qualified name from current scope"""
        if not self.scope_stack:
            return name
        # Build qualified name: ClassName.method_name
        scope_path = ".".join([s[1] for s in self.scope_stack if s[0] == "class"])
        return f"{scope_path}.{name}" if scope_path else name
    
    def _get_qualified_call_name(self, node: ast.Call) -> str:
        """Extract qualified call name from AST node"""
        try:
            if isinstance(node.func, ast.Name):
                return node.func.id
            elif isinstance(node.func, ast.Attribute):
                return ast.unparse(node.func)
            else:
                return ""
        except Exception:
            return ""
    
    def _extract_function_signature(self, node) -> Dict:
        """Extract function signature information"""
        args = []
        for arg in node.args.args:
            arg_info = {"name": arg.arg}
            if arg.annotation:
                try:
                    arg_info["type"] = ast.unparse(arg.annotation)
                except:
                    arg_info["type"] = None
            args.append(arg_info)
        
        # Get return type
        return_type = None
        if node.returns:
            try:
                return_type = ast.unparse(node.returns)
            except:
                pass
        
        return {
            "args": args,
            "return_type": return_type,
            "arg_count": len(args)
        }
    
    def _extract_function_body(self, node) -> Optional[str]:
        """Extract function body text (if enabled)"""
        if not self.include_body:
            return None
        
        try:
            # Get just the function definition (signature + body)
            return ast.unparse(node)
        except Exception:
            # Fallback: try to get body as text
            try:
                body_lines = []
                for stmt in node.body:
                    body_lines.append(ast.unparse(stmt))
                return "\n".join(body_lines)
            except:
                return None
    
    def visit_ClassDef(self, node: ast.ClassDef):
        self.scope_stack.append(("class", node.name))
        qualified = self._get_qualified_name(node.name)
        
        # Extract docstring
        docstring = None
        if self.include_docstrings:
            docstring = ast.get_docstring(node)
        
        # Extract base classes
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except:
                bases.append(str(base))
        
        self.definitions.append({
            "name": node.name,
            "qualified_name": qualified,
            "type": "class",
            "line": node.lineno,
            "scope": self._current_scope(),
            "col_offset": getattr(node, 'col_offset', None),
            "docstring": docstring,
            "bases": bases,
            "base_count": len(bases)
        })
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.scope_stack.append(("function", node.name))
        qualified = self._get_qualified_name(node.name)
        is_method = any(s[0] == "class" for s in self.scope_stack)
        
        # Extract docstring
        docstring = None
        if self.include_docstrings:
            docstring = ast.get_docstring(node)
        
        # Extract signature information
        signature = self._extract_function_signature(node)
        
        # Extract function body
        body_text = self._extract_function_body(node)
        
        self.definitions.append({
            "name": node.name,
            "qualified_name": qualified,
            "type": "function",
            "line": node.lineno,
            "scope": self._current_scope(),
            "is_method": is_method,
            "col_offset": getattr(node, 'col_offset', None),
            "docstring": docstring,
            "signature": signature,
            "body_text": body_text,
            "body_line_count": len(node.body) if node.body else 0
        })
        self.generic_visit(node)
        self.scope_stack.pop()
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        # Treat async functions the same as regular functions
        self.scope_stack.append(("function", node.name))
        qualified = self._get_qualified_name(node.name)
        is_method = any(s[0] == "class" for s in self.scope_stack)
        
        # Extract docstring
        docstring = None
        if self.include_docstrings:
            docstring = ast.get_docstring(node)
        
        # Extract signature information
        signature = self._extract_function_signature(node)
        
        # Extract function body
        body_text = self._extract_function_body(node)
        
        self.definitions.append({
            "name": node.name,
            "qualified_name": qualified,
            "type": "function",
            "line": node.lineno,
            "scope": self._current_scope(),
            "is_method": is_method,
            "is_async": True,
            "col_offset": getattr(node, 'col_offset', None),
            "docstring": docstring,
            "signature": signature,
            "body_text": body_text,
            "body_line_count": len(node.body) if node.body else 0
        })
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append({
                "name": alias.name,
                "as_name": alias.asname,
                "type": "import",
                "line": node.lineno,
                "col_offset": getattr(node, 'col_offset', None)
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module_name = node.module or "."
        for alias in node.names:
            self.imports.append({
                "name": f"{module_name}.{alias.name}",
                "as_name": alias.asname,
                "type": "import_from",
                "line": node.lineno,
                "module": module_name,
                "imported_name": alias.name,
                "col_offset": getattr(node, 'col_offset', None)
            })
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        call_name = ""
        qualified_call = ""
        
        if isinstance(node.func, ast.Name):
            # e.g., print()
            call_name = node.func.id
            qualified_call = call_name
        elif isinstance(node.func, ast.Attribute):
            # e.g., os.path.join() or self.method()
            try:
                call_name = ast.unparse(node.func)
                qualified_call = call_name
                
                # Try to resolve method calls on 'self'
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                    # This is a method call: self.method_name()
                    method_name = node.func.attr
                    # Try to find the class this belongs to
                    for scope_type, scope_name in reversed(self.scope_stack):
                        if scope_type == "class":
                            qualified_call = f"{scope_name}.{method_name}"
                            break
            except Exception:
                # Fallback for complex attributes
                if hasattr(node.func, 'attr'):
                    call_name = f"{node.func.value}.{node.func.attr}" if hasattr(node.func, 'value') else node.func.attr
                else:
                    call_name = str(node.func)
                qualified_call = call_name
        
        if call_name:
            self.calls.append({
                "name": call_name,
                "qualified_call": qualified_call,
                "type": "call",
                "line": node.lineno,
                "scope": self._current_scope(),
                "col_offset": getattr(node, 'col_offset', None)
            })
        self.generic_visit(node)
    
    def visit_Name(self, node: ast.Name):
        """Track variable assignments and usages"""
        if isinstance(node.ctx, ast.Store):  # Assignment
            self.variables.append({
                "name": node.id,
                "line": node.lineno,
                "scope": self._current_scope(),
                "type": "assignment",
                "col_offset": getattr(node, 'col_offset', None)
            })
        elif isinstance(node.ctx, ast.Load):  # Usage/Read
            self.variables.append({
                "name": node.id,
                "line": node.lineno,
                "scope": self._current_scope(),
                "type": "usage",
                "col_offset": getattr(node, 'col_offset', None)
            })
        self.generic_visit(node)


def parse_python_file(file_path: Path, include_body: bool = True, include_docstrings: bool = True) -> Optional[Dict]:
    """
    Reads and parses a Python file, extracting symbols using enhanced AST visitor.
    Returns definitions, calls, imports, and variables with scoping information.
    
    Args:
        file_path: Path to Python file
        include_body: Whether to include function body text (increases size)
        include_docstrings: Whether to include docstrings
    
    Returns:
        Dictionary with definitions (with docstrings/bodies), calls, imports, variables
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filename=str(file_path))
        visitor = EnhancedPythonSymbolVisitor(include_body=include_body, include_docstrings=include_docstrings)
        visitor.visit(tree)
        
        return {
            "definitions": visitor.definitions,
            "calls": visitor.calls,
            "imports": visitor.imports,
            "variables": visitor.variables
        }
    except SyntaxError as e:
        console.print(f"[yellow]Warning: Skipping {file_path} due to SyntaxError: {e}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not parse {file_path}: {e}[/yellow]")
    
    return None


def _resolve_call_target(call_name: str, file_path: str, files: List[Dict], imports_map: Dict = None) -> Optional[Dict]:
    """
    Try to resolve a function call to its definition.
    Returns the target definition if found, None otherwise.
    """
    # First, try direct name match
    for other_file in files:
        if not other_file.get("symbols"):
            continue
        
        for defn in other_file["symbols"].get("definitions", []):
            # Direct name match
            if defn["name"] == call_name:
                return {
                    "name": defn["name"],
                    "qualified_name": defn.get("qualified_name", defn["name"]),
                    "file": other_file["path"],
                    "line": defn["line"]
                }
            
            # Qualified name match (e.g., Class.method)
            qualified = defn.get("qualified_name", "")
            if qualified == call_name or call_name.endswith(f".{defn['name']}"):
                return {
                    "name": defn["name"],
                    "qualified_name": qualified,
                    "file": other_file["path"],
                    "line": defn["line"]
                }
    
    return None


def build_inverted_index(files: List[Dict]) -> Dict:
    """
    Build inverted index for O(1) symbol lookups.
    Structure optimized for "find all usages" queries without storing full codebase.
    
    CRITICAL: This function preserves ALL rich context data (docstrings, bodies, 
    signatures, etc.) from the AST visitor. It copies the entire definition object
    rather than manually building a limited dictionary, ensuring the inverted index
    contains the same rich information as the original files list.
    """
    symbol_index = {}
    import_map = {}
    variable_index = {}
    
    # Build import map first for better resolution
    for file_info in files:
        if not file_info.get("symbols"):
            continue
        
        file_path = file_info["path"]
        symbols = file_info["symbols"]
        
        # Index imports
        for imp in symbols.get("imports", []):
            import_name = imp.get("imported_name") or imp["name"].split(".")[-1]
            module = imp.get("module") or imp["name"].split(".")[0]
            
            if import_name not in import_map:
                import_map[import_name] = {
                    "from_modules": [],
                    "aliases": {},
                    "usages": []
                }
            
            import_map[import_name]["from_modules"].append({
                "module": module,
                "file": file_path,
                "line": imp["line"],
                "as_name": imp.get("as_name")
            })
            
            if imp.get("as_name"):
                import_map[import_name]["aliases"][imp["as_name"]] = import_name
    
    # First pass: Index all definitions
    for file_info in files:
        if not file_info.get("symbols"):
            continue
        
        file_path = file_info["path"]
        symbols = file_info["symbols"]
        
        # Index definitions
        for defn in symbols.get("definitions", []):
            name = defn["name"]
            qualified = defn.get("qualified_name", name)
            
            if name not in symbol_index:
                symbol_index[name] = {
                    "definitions": [],
                    "usages": [],
                    "qualified_names": set()
                }
            
            # Pass through the rich definition data (docstrings, bodies, signatures, etc.)
            # Copy the entire defn object and add file path
            rich_defn_entry = defn.copy()
            rich_defn_entry["file"] = file_path
            
            symbol_index[name]["definitions"].append(rich_defn_entry)
            symbol_index[name]["qualified_names"].add(qualified)
        
        # Index variables
        for var in symbols.get("variables", []):
            var_name = var["name"]
            if var_name not in variable_index:
                variable_index[var_name] = {
                    "assignments": [],
                    "usages": []
                }
            
            # Pass through the full variable info
            var_entry = var.copy()
            var_entry["file"] = file_path
            
            if var["type"] == "assignment":
                variable_index[var_name]["assignments"].append(var_entry)
            else:  # usage
                variable_index[var_name]["usages"].append(var_entry)
    
    # Second pass: Index calls (usages) and resolve them
    for file_info in files:
        if not file_info.get("symbols"):
            continue
        
        file_path = file_info["path"]
        symbols = file_info["symbols"]
        
        # Index calls (usages)
        for call in symbols.get("calls", []):
            call_name = call["name"]
            qualified_call = call.get("qualified_call", call_name)
            
            # Try to resolve the call target
            resolved = _resolve_call_target(call_name, file_path, files, import_map)
            
            # Also try qualified call name
            if not resolved and qualified_call != call_name:
                resolved = _resolve_call_target(qualified_call, file_path, files, import_map)
            
            # Extract base name (for method calls like self.method())
            base_name = call_name.split(".")[-1] if "." in call_name else call_name
            
            # Add usage to all potential targets
            for target_name in [call_name, qualified_call, base_name]:
                if target_name in symbol_index:
                    # Pass through the full call info
                    usage_entry = call.copy()
                    usage_entry["file"] = file_path
                    usage_entry["resolved"] = resolved is not None
                    
                    if resolved:
                        usage_entry["resolved_to"] = resolved["qualified_name"]
                        usage_entry["target_file"] = resolved["file"]
                        usage_entry["target_line"] = resolved["line"]
                    
                    symbol_index[target_name]["usages"].append(usage_entry)
    
    # Convert sets to lists for JSON serialization
    for name in symbol_index:
        symbol_index[name]["qualified_names"] = list(symbol_index[name]["qualified_names"])
    
    return {
        "symbol_index": symbol_index,
        "import_map": import_map,
        "variable_index": variable_index,
        "statistics": {
            "total_symbols": len(symbol_index),
            "total_definitions": sum(len(v["definitions"]) for v in symbol_index.values()),
            "total_usages": sum(len(v["usages"]) for v in symbol_index.values()),
            "total_variables": len(variable_index),
            "total_imports": len(import_map)
        }
    }


def build_code_graph(files: List[Dict], repo_path: Path) -> Dict:
    """
    Build a graph structure from indexed files for easy relationship traversal.
    
    Graph structure:
    - Nodes: files, functions, classes, imports
    - Edges: calls, imports, defined_in, contains relationships
    """
    nodes = []
    edges = []
    node_id_map = {}  # Map (type, identifier) -> node_id
    
    def get_or_create_node(node_type: str, identifier: str, properties: Dict = None) -> str:
        """Get existing node ID or create new node"""
        key = (node_type, identifier)
        if key not in node_id_map:
            node_id = len(nodes)
            node_id_map[key] = node_id
            node = {
                "id": node_id,
                "type": node_type,
                "identifier": identifier,
                "properties": properties or {}
            }
            nodes.append(node)
            return str(node_id)
        return str(node_id_map[key])
    
    def add_edge(source_id: str, target_id: str, edge_type: str, properties: Dict = None):
        """Add an edge to the graph"""
        edge = {
            "source": source_id,
            "target": target_id,
            "type": edge_type,
            "properties": properties or {}
        }
        edges.append(edge)
    
    # First pass: Create file nodes and symbol nodes
    for file_info in files:
        file_path = file_info["path"]
        file_id = get_or_create_node("file", file_path, {
            "name": file_info["name"],
            "language": file_info["language"],
            "extension": file_info["extension"],
            "directory": file_info["directory"],
            "size_bytes": file_info["size_bytes"]
        })
        
        # Add directory containment edges
        if file_info["directory"] != "root":
            dir_parts = file_info["directory"].split(os.sep)
            for i in range(len(dir_parts)):
                parent_dir = os.sep.join(dir_parts[:i+1])
                dir_id = get_or_create_node("directory", parent_dir, {
                    "name": dir_parts[i],
                    "path": parent_dir
                })
                if i == 0:
                    # Connect file to immediate parent directory
                    add_edge(file_id, dir_id, "contained_in")
        
        # Process Python symbols
        if file_info.get("symbols"):
            symbols = file_info["symbols"]
            
            # Create nodes for definitions (functions, classes)
            for defn in symbols.get("definitions", []):
                defn_id = get_or_create_node(
                    defn["type"],  # "function" or "class"
                    f"{file_path}::{defn['name']}",
                    {
                        "name": defn["name"],
                        "file": file_path,
                        "line": defn["line"]
                    }
                )
                # Link definition to its file
                add_edge(defn_id, file_id, "defined_in", {"line": defn["line"]})
            
            # Process imports
            for imp in symbols.get("imports", []):
                import_name = imp["name"]
                import_id = get_or_create_node("import", f"{file_path}::{import_name}", {
                    "name": import_name,
                    "as_name": imp.get("as_name"),
                    "file": file_path,
                    "line": imp["line"]
                })
                # Link import to file
                add_edge(import_id, file_id, "imported_in", {"line": imp["line"]})
                
                # Try to resolve import to actual file (if it's a local import)
                # This is a simple heuristic - in practice, you'd need more sophisticated resolution
                if not import_name.startswith(".") and "." in import_name:
                    # Try to find the imported module/file
                    parts = import_name.split(".")
                    potential_paths = [
                        os.path.join(*(parts[:-1] + [parts[-1] + ".py"])),
                        os.path.join(*parts) + ".py",
                        os.path.join(*parts[:-1], parts[-1] + ".py")
                    ]
                    for potential_path in potential_paths:
                        # Check if this file exists in our index
                        for other_file in files:
                            if other_file["path"].endswith(potential_path) or other_file["path"] == potential_path:
                                other_file_id = get_or_create_node("file", other_file["path"])
                                add_edge(import_id, other_file_id, "imports_from")
                                break
            
            # Process function calls
            for call in symbols.get("calls", []):
                call_name = call["name"]
                call_id = get_or_create_node("call", f"{file_path}::{call_name}::{call['line']}", {
                    "name": call_name,
                    "file": file_path,
                    "line": call["line"]
                })
                # Link call to file
                add_edge(call_id, file_id, "called_in", {"line": call["line"]})
                
                # Try to link call to definition (if we can find it)
                # This is a simple heuristic - matches by name
                for other_file in files:
                    if other_file.get("symbols"):
                        for defn in other_file["symbols"].get("definitions", []):
                            if defn["name"] == call_name or call_name.endswith(f".{defn['name']}"):
                                defn_id = get_or_create_node(
                                    defn["type"],
                                    f"{other_file['path']}::{defn['name']}"
                                )
                                add_edge(call_id, defn_id, "calls")
                                break
    
    return {
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "node_types": list(set(node["type"] for node in nodes)),
            "edge_types": list(set(edge["type"] for edge in edges))
        }
    }


def index_codebase(repo_path: Path, ignore_patterns: Optional[List[str]] = None, 
                  include_body: bool = True, include_docstrings: bool = True) -> Dict:
    """
    Index the codebase structure. Performs deep parsing for Python files.
    
    Args:
        repo_path: Path to cloned repository
        ignore_patterns: Additional patterns to ignore
        include_body: Whether to include function body text (default: True, increases size)
        include_docstrings: Whether to include docstrings (default: True)
    """
    if ignore_patterns is None:
        ignore_patterns = []
    
    indexed_structure = {
        "files": [],
        "directories": [],
        "statistics": {
            "total_files": 0,
            "total_directories": 0,
            "total_size_bytes": 0,
            "languages": {},
            "by_extension": {},
            "total_python_symbols": 0,
        },
        "tree": {},
        "graph": {
            "nodes": [],
            "edges": []
        },
        "inverted_index": {}  # NEW: For fast symbol lookups
    }
    
    languages = {}
    extensions = {}
    total_size = 0
    total_py_symbols = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Indexing codebase...", total=None)
        
        file_count = 0
        dir_count = 0
        
        # Pre-count total files for a better progress bar (optional but nice)
        total_files_estimate = sum(len(files) for _, _, files in os.walk(repo_path))
        progress.update(task, total=total_files_estimate)

        for root, dirs, files in os.walk(repo_path):
            root_path = Path(root)
            
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if not should_ignore_path(root_path / d, ignore_patterns)]
            
            # Process directories
            for dir_name in dirs:
                dir_path = root_path / dir_name
                if should_ignore_path(dir_path, ignore_patterns):
                    continue
                
                rel_path = dir_path.relative_to(repo_path)
                indexed_structure["directories"].append({
                    "path": str(rel_path),
                    "name": dir_name,
                })
                dir_count += 1
            
            # Process files
            for file_name in files:
                file_path = root_path / file_name
                if should_ignore_path(file_path, ignore_patterns):
                    continue
                
                progress.update(task, description=f"[cyan]Indexing... {file_name}[/cyan]")
                
                try:
                    rel_path = file_path.relative_to(repo_path)
                    file_size = file_path.stat().st_size
                    language = get_file_language(file_path)
                    ext = file_path.suffix.lower()
                    
                    file_info = {
                        "path": str(rel_path),
                        "name": file_name,
                        "size_bytes": file_size,
                        "language": language,
                        "extension": ext if ext else "no extension",
                        "directory": str(rel_path.parent) if rel_path.parent != Path('.') else "root",
                        "symbols": None # Placeholder for code symbols
                    }
                    
                    # --- Code-Aware Parsing with Docstrings and Bodies ---
                    if language == 'python':
                        progress.update(task, description=f"[blue]Parsing... {file_name}[/blue]")
                        symbols = parse_python_file(file_path, include_body=include_body, include_docstrings=include_docstrings)
                        if symbols:
                            file_info["symbols"] = symbols
                            # Count all symbols including variables
                            total_py_symbols += (
                                len(symbols["definitions"]) + 
                                len(symbols["calls"]) + 
                                len(symbols["imports"]) +
                                len(symbols.get("variables", []))
                            )
                    # --- End Code Parsing ---

                    indexed_structure["files"].append(file_info)
                    
                    # Update statistics
                    languages[language] = languages.get(language, 0) + 1
                    extensions[ext if ext else "no extension"] = extensions.get(ext if ext else "no extension", 0) + 1
                    total_size += file_size
                    file_count += 1
                    
                    progress.advance(task)
                    
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not index {file_path}: {e}[/yellow]")
        
        # Build tree structure
        tree = {}
        for file_info in indexed_structure["files"]:
            parts = file_info["path"].split(os.sep)
            current = tree
            for part in parts[:-1]:  # All but the file name
                if part not in current:
                    current[part] = {}
                current = current[part]
            # Add file info
            file_name = parts[-1]
            current[file_name] = {
                "type": "file",
                "size": file_info["size_bytes"],
                "language": file_info["language"],
                "extension": file_info["extension"],
                "has_symbols": file_info["symbols"] is not None
            }
        
        for dir_info in indexed_structure["directories"]:
            parts = dir_info["path"].split(os.sep)
            current = tree
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current["_type"] = "directory"
        
        indexed_structure["tree"] = tree
        
        # Update statistics
        indexed_structure["statistics"]["total_files"] = file_count
        indexed_structure["statistics"]["total_directories"] = dir_count
        indexed_structure["statistics"]["total_size_bytes"] = total_size
        indexed_structure["statistics"]["languages"] = dict(sorted(languages.items(), key=lambda x: x[1], reverse=True))
        indexed_structure["statistics"]["by_extension"] = dict(sorted(extensions.items(), key=lambda x: x[1], reverse=True))
        indexed_structure["statistics"]["total_python_symbols"] = total_py_symbols
        
        progress.update(task, description=f"[green]✓ Indexed {file_count} files and {dir_count} directories[/green]")
        
        # Build graph structure for relationship traversal
        progress.update(task, description=f"[cyan]Building code graph...[/cyan]")
        graph_data = build_code_graph(indexed_structure["files"], repo_path)
        indexed_structure["graph"] = graph_data
        indexed_structure["statistics"]["graph_nodes"] = len(graph_data["nodes"])
        indexed_structure["statistics"]["graph_edges"] = len(graph_data["edges"])
        
        # Build inverted index for fast symbol lookups (O(1) queries)
        progress.update(task, description=f"[cyan]Building inverted index...[/cyan]")
        inverted_index_data = build_inverted_index(indexed_structure["files"])
        indexed_structure["inverted_index"] = inverted_index_data
        indexed_structure["statistics"]["indexed_symbols"] = inverted_index_data["statistics"]["total_symbols"]
        indexed_structure["statistics"]["indexed_definitions"] = inverted_index_data["statistics"]["total_definitions"]
        indexed_structure["statistics"]["indexed_usages"] = inverted_index_data["statistics"]["total_usages"]
        indexed_structure["statistics"]["indexed_variables"] = inverted_index_data["statistics"]["total_variables"]
    
    return indexed_structure


def clone_repository(repo_url: str, temp_dir: Path, access_token: Optional[str] = None) -> Path:
    """
    Clone a GitLab repository to a temporary directory.
    """
    repo_name = Path(urlparse(repo_url).path).stem
    clone_path = temp_dir / repo_name
    
    # Construct clone URL with token if provided
    if access_token and "gitlab.com" in repo_url:
        # Modify URL to include token
        parsed = urlparse(repo_url)
        clone_url = f"{parsed.scheme}://oauth2:{access_token}@{parsed.netloc}{parsed.path}.git"
    else:
        clone_url = f"{repo_url}.git" if not repo_url.endswith(".git") else repo_url
    
    console.print(f"[cyan]Cloning repository to temporary cache...[/cyan]")
    
    try:
        # Clone the repository
        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(clone_path)],
            capture_output=True,
            text=True,
            check=True
        )
        console.print(f"[green]✓[/green] Repository cloned successfully")
        return clone_path
    except subprocess.CalledProcessError as e:
        console.print(f"[red]✗ Error cloning repository: {e.stderr}[/red]")
        raise
    except FileNotFoundError:
        console.print("[red]✗ Error: git is not installed or not in PATH[/red]")
        raise


def find_all_usages(indexed_data: Dict, symbol_name: str) -> Optional[Dict]:
    """
    Fast O(1) lookup for all usages of a symbol.
    Returns definitions and usages without scanning the entire codebase.
    """
    inverted_index = indexed_data.get("inverted_index", {})
    symbol_index = inverted_index.get("symbol_index", {})
    
    if symbol_name in symbol_index:
        return {
            "symbol": symbol_name,
            "definitions": symbol_index[symbol_name]["definitions"],
            "usages": symbol_index[symbol_name]["usages"],
            "qualified_names": symbol_index[symbol_name]["qualified_names"],
            "total_definitions": len(symbol_index[symbol_name]["definitions"]),
            "total_usages": len(symbol_index[symbol_name]["usages"])
        }
    return None


def find_symbol_by_qualified_name(indexed_data: Dict, qualified_name: str) -> List[Dict]:
    """
    Find symbol by qualified name (e.g., "ClassName.method_name").
    """
    inverted_index = indexed_data.get("inverted_index", {})
    symbol_index = inverted_index.get("symbol_index", {})
    
    results = []
    for name, data in symbol_index.items():
        for defn in data["definitions"]:
            if defn.get("qualified_name") == qualified_name:
                results.append({
                    "symbol": name,
                    "definition": defn,
                    "usages": data["usages"],
                    "qualified_names": data["qualified_names"]
                })
    return results


def find_variable_usages(indexed_data: Dict, variable_name: str) -> Optional[Dict]:
    """
    Find all assignments and usages of a variable.
    """
    inverted_index = indexed_data.get("inverted_index", {})
    variable_index = inverted_index.get("variable_index", {})
    
    if variable_name in variable_index:
        return {
            "variable": variable_name,
            "assignments": variable_index[variable_name]["assignments"],
            "usages": variable_index[variable_name]["usages"],
            "total_assignments": len(variable_index[variable_name]["assignments"]),
            "total_usages": len(variable_index[variable_name]["usages"])
        }
    return None


def search_symbols(indexed_data: Dict, query: str, symbol_type: Optional[str] = None) -> List[Dict]:
    """
    Search for symbols by name (partial match).
    Returns all symbols matching the query.
    """
    inverted_index = indexed_data.get("inverted_index", {})
    symbol_index = inverted_index.get("symbol_index", {})
    
    results = []
    query_lower = query.lower()
    
    for name, data in symbol_index.items():
        if query_lower in name.lower():
            # Filter by type if specified
            if symbol_type:
                matching_defs = [d for d in data["definitions"] if d.get("type") == symbol_type]
                if not matching_defs:
                    continue
            
            results.append({
                "symbol": name,
                "definitions": data["definitions"],
                "usages_count": len(data["usages"]),
                "qualified_names": data["qualified_names"]
            })
    
    return results


def display_index_summary(indexed_data: Dict, repo_url: str):
    """Display a summary of the indexed codebase"""
    
    stats = indexed_data["statistics"]
    
    # Summary table
    summary_table = Table(title="Codebase Index Summary", show_header=True, header_style="bold magenta")
    summary_table.add_column("Metric", style="cyan", width=30)
    summary_table.add_column("Value", style="green", width=20)
    
    total_size_mb = stats["total_size_bytes"] / (1024 * 1024)
    summary_table.add_row("Repository", repo_url)
    summary_table.add_row("Total Files", str(stats["total_files"]))
    summary_table.add_row("Total Directories", str(stats["total_directories"]))
    summary_table.add_row("Total Size", f"{total_size_mb:.2f} MB")
    
    # --- NEW: Show Python Symbol Stat ---
    if "total_python_symbols" in stats and stats["total_python_symbols"] > 0:
        summary_table.add_row("Python Symbols Found", f"[bold blue]{stats['total_python_symbols']}[/bold blue]")
    
    # Show graph statistics
    if "graph_nodes" in stats and "graph_edges" in stats:
        summary_table.add_row("Graph Nodes", f"[bold cyan]{stats['graph_nodes']}[/bold cyan]")
        summary_table.add_row("Graph Edges", f"[bold cyan]{stats['graph_edges']}[/bold cyan]")
    
    # Show inverted index statistics
    if "indexed_symbols" in stats:
        summary_table.add_row("Indexed Symbols", f"[bold green]{stats['indexed_symbols']}[/bold green]")
    if "indexed_definitions" in stats:
        summary_table.add_row("Indexed Definitions", f"[bold green]{stats['indexed_definitions']}[/bold green]")
    if "indexed_usages" in stats:
        summary_table.add_row("Indexed Usages", f"[bold green]{stats['indexed_usages']}[/bold green]")
    if "indexed_variables" in stats:
        summary_table.add_row("Indexed Variables", f"[bold green]{stats['indexed_variables']}[/bold green]")
    
    console.print(summary_table)
    console.print()
    
    # Languages table
    if stats["languages"]:
        lang_table = Table(title="Languages Detected", show_header=True, header_style="bold blue")
        lang_table.add_column("Language", style="cyan", width=20)
        lang_table.add_column("File Count", style="green", width=15)
        
        for lang, count in list(stats["languages"].items())[:10]:  # Top 10
            lang_table.add_row(lang, str(count))
        
        console.print(lang_table)
        console.print()
    
    # Top extensions
    if stats["by_extension"]:
        ext_table = Table(title="Top File Extensions", show_header=True, header_style="bold green")
        ext_table.add_column("Extension", style="cyan", width=20)
        ext_table.add_column("File Count", style="green", width=15)
        
        for ext, count in list(stats["by_extension"].items())[:10]:  # Top 10
            ext_table.add_row(ext if ext else "(no extension)", str(count))
        
        console.print(ext_table)


def main():
    """Main function"""
    # Get repository URL from command line or environment
    repo_url = None
    if len(sys.argv) > 1:
        repo_url = sys.argv[1]
    elif os.getenv('REPO_URL'):
        repo_url = os.getenv('REPO_URL')
    else:
        # Default to a well-known Python repo for demonstration
        console.print("[yellow]No REPO_URL provided. Using 'https://gitlab.com/psf/requests' as a demo.[/yellow]")
        repo_url = "https://gitlab.com/psf/requests"
    
    # Get GitLab token (optional, needed for private repos)
    access_token = os.getenv('GITLAB_TOKEN')
    
    # Parse repository URL to get repo identifier
    parsed = urlparse(repo_url)
    repo_path_parts = parsed.path.strip('/').split('/')
    if len(repo_path_parts) >= 2:
        repo_identifier = f"{repo_path_parts[-2]}/{repo_path_parts[-1]}"
    else:
        repo_identifier = repo_path_parts[-1] if repo_path_parts else "unknown"
    
    # Ensure data directory exists
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    # Output file name
    safe_repo_name = repo_identifier.replace('/', '_')
    output_file = os.path.join(data_dir, f"indexed_code_{safe_repo_name}.json")
    
    # Create temporary directory for cloning
    temp_dir = None
    clone_path = None
    
    try:
        console.print(f"[bold]Indexing Repository[/bold]")
        console.print(f"[cyan]Repository URL:[/cyan] {repo_url}")
        console.print()
        
        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="repo_index_"))
        console.print(f"[dim]Temporary cache directory: {temp_dir}[/dim]")
        console.print()
        
        # Clone repository
        clone_path = clone_repository(repo_url, temp_dir, access_token)
        console.print()
        
        # Check if user wants to skip body/docstrings (for smaller index files)
        include_body = os.getenv('INCLUDE_FUNCTION_BODY', 'true').lower() == 'true'
        include_docstrings = os.getenv('INCLUDE_DOCSTRINGS', 'true').lower() == 'true'
        
        if '--no-body' in sys.argv:
            include_body = False
            console.print("[yellow]Note: Function bodies will NOT be included (smaller index file)[/yellow]")
        if '--no-docstrings' in sys.argv:
            include_docstrings = False
            console.print("[yellow]Note: Docstrings will NOT be included[/yellow]")
        
        # Index the codebase
        indexed_data = index_codebase(clone_path, include_body=include_body, include_docstrings=include_docstrings)
        console.print()
        
        # Add metadata
        indexed_data["metadata"] = {
            "repository_url": repo_url,
            "repository_identifier": repo_identifier,
            "indexed_at": datetime.utcnow().isoformat() + "Z",
            "index_version": "4.0.0-ai-enhanced",
            "includes_docstrings": include_docstrings,
            "includes_function_bodies": include_body
        }
        
        # Display summary
        display_index_summary(indexed_data, repo_url)
        
        # Save to file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(indexed_data, f, indent=2, ensure_ascii=False)
        
        console.print()
        console.print(f"[green]✓[/green] Code-aware index saved to: {output_file}")
        console.print(f"[dim]Total files indexed: {indexed_data['statistics']['total_files']}[/dim]")
        console.print()
        console.print("[yellow]Note:[/yellow] The temporary clone has been removed. Use the JSON index file for future queries.")
        
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)
    
    finally:
        # Clean up temporary directory
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                console.print(f"[dim]Cleaned up temporary cache: {temp_dir}[/dim]")
            except Exception as e:
                console.print(f"[yellow]Warning: Could not clean up temp directory {temp_dir}: {e}[/yellow]")


if __name__ == "__main__":
    main()