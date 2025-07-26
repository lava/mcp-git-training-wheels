#!/usr/bin/env python3
from fastmcp import FastMCP
import subprocess
import time
from typing import List, Tuple
import gitrevise.odb as gitrevise_odb
from gitrevise.utils import Repository, commit_range, edit_commit

# Create the MCP server
mcp = FastMCP("git-mcp")

# Store the last commit info in memory
last_commit_info = None

# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF = 0.5  # seconds
MAX_BACKOFF = 10.0  # seconds

def run_git_command_with_retry(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """
    Run a git command with retry logic for handling concurrent operations.
    
    Args:
        cmd: Command to run as list of strings
        check: Whether to raise CalledProcessError on non-zero exit
        
    Returns:
        CompletedProcess instance
        
    Raises:
        subprocess.CalledProcessError: If command fails after all retries
    """
    backoff = INITIAL_BACKOFF
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            result = subprocess.run(cmd, check=check, capture_output=True, text=True)
            return result
        except subprocess.CalledProcessError as e:
            last_error = e
            error_msg = e.stderr.lower() if e.stderr else str(e).lower()
            
            # Check if this is a concurrency error
            if any(phrase in error_msg for phrase in [
                "another git process",
                "index.lock",
                "unable to create",
                "resource temporarily unavailable",
                "cannot lock ref"
            ]):
                if attempt < MAX_RETRIES - 1:
                    # Log the retry attempt
                    print(f"Git operation blocked (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)  # Exponential backoff
                    continue
            
            # Not a concurrency error or last attempt, re-raise
            raise
    
    # If we get here, we've exhausted retries
    raise last_error

@mcp.tool()
def git_commit(files: List[str], message: str) -> str:
    """
    Commit specified files to git with the given commit message.
    
    Args:
        files: List of file paths to commit
        message: Commit message
        
    Returns:
        Result of the git commit operation
    """
    try:
        # Stage the specified files
        run_git_command_with_retry(["git", "add"] + files)
        
        # Commit with the message
        result = run_git_command_with_retry(["git", "commit", "-m", message])
        
        # Get the commit hash of the newly created commit
        commit_hash_result = run_git_command_with_retry(["git", "rev-parse", "HEAD"])
        commit_hash = commit_hash_result.stdout.strip()
        
        # Save the commit info
        global last_commit_info
        last_commit_info = {
            "hash": commit_hash,
            "message": message
        }
        
        return f"Successfully committed {len(files)} file(s) (commit: {commit_hash}):\n{result.stdout}"
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        return f"Git commit failed: {error_msg}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def fixup_commit(files: List[str]) -> str:
    """
    Amend files to the last commit created by git_commit.
    If the commit is still HEAD, uses git commit --amend.
    Otherwise, uses gitrevise to edit the commit in history.
    
    Args:
        files: List of file paths to add to the commit
        
    Returns:
        Result of the fixup operation
    """
    try:
        # Check if we have a saved commit
        global last_commit_info
        if not last_commit_info:
            return "Error: No previous commit found. Use git_commit first."
        
        saved_hash = last_commit_info["hash"]
        saved_message = last_commit_info["message"]
        
        # Get current HEAD hash
        head_result = run_git_command_with_retry(["git", "rev-parse", "HEAD"])
        head_hash = head_result.stdout.strip()
        
        # Stage the files
        run_git_command_with_retry(["git", "add"] + files)
        
        if saved_hash == head_hash:
            # The saved commit is still HEAD, use --amend
            result = run_git_command_with_retry(["git", "commit", "--amend", "--no-edit"])
            return f"Successfully amended HEAD commit {saved_hash[:8]} with {len(files)} file(s)"
        else:
            # Need to find the commit in history
            # First try by hash
            try:
                run_git_command_with_retry(["git", "rev-parse", f"{saved_hash}^{{commit}}"])
                target_commit = saved_hash
            except subprocess.CalledProcessError:
                # Hash not found, try to find by message
                log_result = run_git_command_with_retry(
                    ["git", "log", "--oneline", "--grep", f"^{saved_message}$"]
                )
                if not log_result.stdout.strip():
                    return f"Error: Could not find commit with hash {saved_hash} or message '{saved_message}'"
                
                # Get the first matching commit
                target_commit = log_result.stdout.strip().split()[0]
            
            # Use gitrevise to edit the commit
            repo = Repository()
            
            # Get the commit to edit
            target = repo.get_commit(target_commit)
            
            # Create a new tree with the staged changes
            tree_result = run_git_command_with_retry(["git", "write-tree"])
            new_tree_oid = tree_result.stdout.strip()
            
            # Create updated commit with new tree
            new_commit = target.update(tree=repo.get_tree(new_tree_oid))
            
            # Get the range of commits to rebase
            base_commit = f"{target_commit}~1"
            try:
                commits = list(commit_range(repo, base_commit, "HEAD"))
            except:
                # If the commit is the root commit
                commits = list(commit_range(repo, target_commit, "HEAD"))
                base_commit = None
            
            # Replace the target commit in the list
            for i, commit in enumerate(commits):
                if commit.oid.hex == target.oid.hex:
                    commits[i] = new_commit
                    break
            
            # Rebase the commits
            if base_commit:
                base = repo.get_commit(base_commit)
            else:
                base = None
                
            for commit in commits:
                if base:
                    commit = commit.rebase(base)
                base = commit
            
            # Update the branch
            run_git_command_with_retry(["git", "reset", "--hard", base.oid.hex])
            
            return f"Successfully edited commit {target_commit[:8]} with {len(files)} file(s) using gitrevise"
            
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        return f"Git operation failed: {error_msg}"
    except ImportError:
        return "Error: gitrevise module not found. Install with: pip install gitrevise"
    except Exception as e:
        return f"Error: {str(e)}"

def main():
    """Entry point for the MCP server."""
    mcp.run()

if __name__ == "__main__":
    main()