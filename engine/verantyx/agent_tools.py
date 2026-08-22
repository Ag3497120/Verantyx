"""Agent tools — the hands and feet (手足) of agent mode.

Every tool is a plain function with declared mutability; the agent loop
gates every *mutating* tool behind arrow-key approval. Read-only tools run
freely. Vera's own faculties (ask / remember / math / code) are tools too,
so the ReAct loop can consult the deterministic core at any step.

Note on web search: the Verantyx IDE's BrowserBridge is JCross-vaulted
(deliberately opaque), so this is an independent Python counterpart —
DuckDuckGo HTML search + plain page fetch over stdlib urllib.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .cross_store import CrossStore

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko)"}


@dataclass
class Tool:
    name: str
    description: str
    mutating: bool
    fn: Callable[..., Dict[str, Any]]
    args_hint: str = ""


# ---------------------------------------------------------------------------
# filesystem
# ---------------------------------------------------------------------------

def read_file(path: str, max_chars: int = 8000) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "error": f"not_a_file: {path}"}
    text = p.read_text(errors="replace")
    return {"ok": True, "path": str(p), "chars": len(text),
            "content": text[:max_chars]}


def write_file(path: str, content: str) -> Dict[str, Any]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return {"ok": True, "path": str(p), "chars": len(content)}


def edit_file(path: str, old: str, new: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "error": f"not_a_file: {path}"}
    text = p.read_text(errors="replace")
    n = text.count(old)
    if n == 0:
        return {"ok": False, "error": "old_string_not_found"}
    if n > 1:
        return {"ok": False, "error": f"old_string_not_unique ({n} matches)"}
    p.write_text(text.replace(old, new, 1))
    return {"ok": True, "path": str(p), "replaced": 1}


def list_dir(path: str = ".") -> Dict[str, Any]:
    p = Path(path)
    if not p.is_dir():
        return {"ok": False, "error": f"not_a_dir: {path}"}
    entries = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
    return {"ok": True, "path": str(p), "entries": entries[:200]}


def make_dir(path: str) -> Dict[str, Any]:
    Path(path).mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": path}


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------

def run_command(command: str, timeout: int = 60) -> Dict[str, Any]:
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {
            "ok": r.returncode == 0,
            "returncode": r.returncode,
            "stdout": r.stdout[-4000:],
            "stderr": r.stderr[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout_{timeout}s"}


# ---------------------------------------------------------------------------
# git clone (scoped, NOT run_command) -- real-usage gap found live: a
# "study this repo" task had no way to actually get the repo without
# reaching for run_command's arbitrary-shell escape hatch, which correctly
# gets denied by the mutating-tool approval gate. This is the safe
# alternative: URL-allowlisted (https://github.com/... only, no shell
# metacharacters possible since args are passed as a list, not a shell
# string), shallow (--depth 1, bounded time/size), and writes ONLY into
# Vera's own scratch workspace -- never the user's project directory, never
# an arbitrary path chosen by the LLM. Same risk class as fetch_url/
# web_search (reads external content, writes only to Vera's own private
# state), which is why it's registered non-mutating below, unlike
# run_command/write_file/edit_file which can touch anything.
# ---------------------------------------------------------------------------

_GITHUB_CLONE_URL_RE = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+(?:\.git)?/?$")


def git_clone_scratch(url: str, *, scratch_dir: Path, timeout: int = 120) -> Dict[str, Any]:
    url = url.strip()
    if not _GITHUB_CLONE_URL_RE.match(url):
        return {"ok": False, "error": "only_https_github_repo_urls_supported"}
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", url.rstrip("/")).strip("_")[:80]
    dest = Path(scratch_dir) / slug
    if dest.is_dir() and any(dest.iterdir()):
        return {"ok": True, "path": str(dest), "already_cloned": True}
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout_{timeout}s"}
    except FileNotFoundError:
        return {"ok": False, "error": "git_not_installed"}
    if r.returncode != 0:
        return {"ok": False, "error": r.stderr.strip()[-2000:]}
    return {"ok": True, "path": str(dest)}


def git_clone_scratch_dir() -> Path:
    """Vera's own private clone workspace -- next to the same Application
    Support location vera-memory already uses (see vera_server.py's
    resolved_store_path pattern), never inside the user's own project."""
    from pathlib import Path as _Path
    import os as _os

    base = _os.environ.get("XDG_STATE_HOME") or str(_Path.home() / "Library" / "Application Support")
    return _Path(base) / "Verantyx" / "vera-memory" / "scratch_repos"


# ---------------------------------------------------------------------------
# web (Python counterpart of the vaulted BrowserBridge)
# ---------------------------------------------------------------------------

# DDG lite endpoint: <a ... href="URL" class='result-link'>TITLE</a>
_RESULT = re.compile(
    r'<a[^>]+href="([^"]+)"[^>]*class=[\'"]result-link[\'"][^>]*>(.*?)</a>', re.S
)
_SNIPPET = re.compile(r'class=[\'"]result-snippet[\'"][^>]*>(.*?)</td>', re.S)
_TAG = re.compile(r"<[^>]+>")


def web_search(query: str, k: int = 5) -> Dict[str, Any]:
    url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            page = r.read().decode(errors="replace")
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    links = _RESULT.findall(page)
    snips = _SNIPPET.findall(page)
    out: List[Dict[str, str]] = []
    for i, (href, title) in enumerate(links[:k]):
        if "uddg=" in href:
            href = urllib.parse.unquote(
                href.split("uddg=", 1)[1].split("&", 1)[0]
            )
        out.append(
            {
                "title": html.unescape(_TAG.sub("", title)).strip(),
                "url": href,
                "snippet": html.unescape(_TAG.sub("", snips[i])).strip()[:200]
                if i < len(snips) else "",
            }
        )
    return {"ok": True, "query": query, "results": out}


_GITHUB_REPO_ROOT_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$"
)


def _github_readme_url(url: str) -> Optional[str]:
    """A bare github.com/OWNER/REPO URL renders as a full HTML page whose
    file-tree listing alone can run past max_chars before the actual README
    ever starts (confirmed directly: fetch_url on a real repo page spent its
    entire 6000-char budget on a doubled file-name list, cutting off right
    as the README began) -- agent.run() then has nothing useful to answer
    from and keeps re-searching instead of concluding. GitHub's REST API
    returns the README as clean raw text with no chrome, so repo-root URLs
    are redirected there instead of being scraped as HTML."""
    m = _GITHUB_REPO_ROOT_RE.match(url.strip())
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    return f"https://api.github.com/repos/{owner}/{repo}/readme"


def jgen_reflect(
    jgen_endpoint: str, prompt: str, interventions: List[Dict[str, Any]], observe_layers: List[int],
) -> Dict[str, Any]:
    """Milestone P: injects short text labels (Vera's own state -- goal,
    confirmed facts, rejected hypotheses, knowledge gaps -- one per
    intervention) into JGEN's hidden states at specific layers in ONE
    forward pass, and returns what JGEN's internal representation decodes
    to at each requested layer, as text. This is the first concrete step
    of the "Vera is the persistent cognitive architecture; JGEN is its
    steerable neural cortex" design -- Vera doesn't have its own vector
    space, so JGEN's own encode() is what turns Vera's text state into
    vectors on the IDE side (see JCrossChatManager.reflect); this function
    only ever sends/receives text across the process boundary, never a
    raw vector, matching Milestone L's own principle.

    `interventions`: [{"layer": int, "text_label": str, "alpha": float}].
    `observe_layers`: which layers to report back (pre/post-layer
    conventions differ between inject and observe -- see the Swift/Rust
    doc comments this mirrors)."""
    payload = json.dumps({
        "prompt": prompt, "interventions": interventions, "observe_layers": observe_layers,
    }).encode()
    req = urllib.request.Request(
        jgen_endpoint.rstrip("/") + "/jgen/inject_multi_layer",
        data=payload, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return d


def _browser_bridge_fetch(url: str, browser_endpoint: str, max_chars: int) -> Optional[Dict[str, Any]]:
    """Calls the IDE's JGenAgentServer /browser/fetch (Milestone N-adjacent
    bridge over BrowserBridge/verantyx-browser, a real WKWebView) instead
    of this module's own urllib scrape. Real browser rendering handles
    JS-heavy pages and gives markdown extraction tuned by BrowserBridge
    itself, not a generic tag-strip. Returns None (never raises) on any
    failure so the caller falls through to the existing urllib path --
    this is a preference, not a hard dependency, since not every `vera
    serve` invocation has a browser_endpoint configured."""
    payload = json.dumps({"url": url}).encode()
    req = urllib.request.Request(
        browser_endpoint.rstrip("/") + "/browser/fetch",
        data=payload, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read())
    except Exception:
        return None
    if not d.get("ok"):
        return None
    markdown = d.get("markdown", "")
    return {"ok": True, "url": url, "text": markdown[:max_chars],
            "note": "fetched via verantyx-browser (real WKWebView render)"}


def fetch_url(url: str, max_chars: int = 6000, browser_endpoint: Optional[str] = None) -> Dict[str, Any]:
    if browser_endpoint:
        via_browser = _browser_bridge_fetch(url, browser_endpoint, max_chars)
        if via_browser is not None:
            return via_browser

    readme_url = _github_readme_url(url)
    if readme_url:
        req = urllib.request.Request(
            readme_url, headers={**_UA, "Accept": "application/vnd.github.raw+json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode(errors="replace")
            return {"ok": True, "url": url, "text": text[:max_chars],
                    "note": "fetched as README (raw), not the rendered repo page"}
        except Exception as e:
            # README fetch failing (e.g. no README, private repo) falls
            # through to the normal HTML scrape below rather than giving up.
            pass

    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            page = r.read().decode(errors="replace")
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    text = _TAG.sub(" ", re.sub(r"<(script|style).*?</\1>", " ", page, flags=re.S))
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return {"ok": True, "url": url, "text": text[:max_chars]}


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

def build_registry(store: CrossStore, save: Callable[[], None],
                    browser_endpoint: Optional[str] = None) -> Dict[str, Tool]:
    from .code_ingest import code_ask, ingest_python_repo
    from .consensus_store import consensus_over_store
    from .math_sim import math_ask

    def vera_ask(query: str) -> Dict[str, Any]:
        return consensus_over_store(store, query)

    def vera_remember(sentence: str) -> Dict[str, Any]:
        key = store.ingest_sentence(sentence)
        save()
        return {"remembered": key}

    def vera_recall(core: str, k: int = 8) -> Dict[str, Any]:
        hits = {
            key: store.top_facets(key, int(k))
            for key in (core, core + "#p")
            if store.has(key)
        }
        return hits or {"verdict": "UNKNOWN_NO_EVIDENCE"}

    def vera_code_ingest(path: str) -> Dict[str, Any]:
        rep = ingest_python_repo(store, Path(path))
        save()
        return rep

    def vera_git_clone_bound(url: str) -> Dict[str, Any]:
        return git_clone_scratch(url, scratch_dir=git_clone_scratch_dir())

    def vera_code_query(query: str) -> Dict[str, Any]:
        return code_ask(store, query)

    def vera_math(query: str) -> Dict[str, Any]:
        return math_ask(query)

    def fetch_url_bound(url: str, max_chars: int = 6000) -> Dict[str, Any]:
        return fetch_url(url, max_chars, browser_endpoint=browser_endpoint)

    def jgen_reflect_bound(prompt: str, interventions: str, observe_layers: str) -> Dict[str, Any]:
        # LLM tool-call args arrive as JSON strings for the two structured
        # params (matches how other tools here take flat scalar args) --
        # parsed defensively so a malformed call fails typed, not with a
        # raw exception surfacing to the ReAct loop.
        if not browser_endpoint:
            return {"ok": False, "error": "no_jgen_endpoint_configured"}
        try:
            iv = json.loads(interventions) if interventions else []
            layers = json.loads(observe_layers) if observe_layers else []
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"bad_json_args: {e}"}
        return jgen_reflect(browser_endpoint, prompt, iv, layers)

    tools = [
        Tool("read_file", "Read a text file", False, read_file, "path"),
        Tool("list_dir", "List a directory", False, list_dir, "path"),
        Tool("write_file", "Create/overwrite a file", True, write_file,
             "path, content"),
        Tool("edit_file", "Replace a unique string in a file", True, edit_file,
             "path, old, new"),
        Tool("make_dir", "Create a directory", True, make_dir, "path"),
        Tool("run_command", "Run a shell command", True, run_command, "command"),
        Tool("web_search", "DuckDuckGo search", False, web_search, "query"),
        Tool("fetch_url", "Fetch a web page as text", False, fetch_url_bound, "url"),
        Tool("jgen_reflect",
             "Inject short text state labels into JGEN's hidden states at "
             "specific layers and see what JGEN's internal representation "
             "decodes to -- only useful when a jgen_endpoint is configured; "
             "returns a typed error otherwise",
             False, jgen_reflect_bound,
             'prompt, interventions (JSON list of {"layer","text_label","alpha"}), observe_layers (JSON list of int)'),
        Tool("vera_ask", "Ask the deterministic knowledge store", False,
             vera_ask, "query"),
        Tool("vera_remember", "Store a fact permanently", True, vera_remember,
             "sentence"),
        Tool("vera_recall", "Dump a concept's facets", False, vera_recall,
             "core"),
        Tool("vera_code_ingest", "AST-ingest a Python repo", True,
             vera_code_ingest, "path"),
        Tool("vera_git_clone",
             "Shallow-clone a public https://github.com/... repo URL into "
             "Vera's own private scratch workspace (never the user's project "
             "directory) so vera_code_ingest has a local path to read. "
             "Same risk class as fetch_url/web_search -- reads external "
             "content, writes only to Vera's own state.",
             False, vera_git_clone_bound, "url"),
        Tool("vera_code_query", "who calls X / impact of X", False,
             vera_code_query, "query"),
        Tool("vera_math", "Exact arithmetic / equations", False, vera_math,
             "query"),
    ]
    return {t.name: t for t in tools}


def tools_manifest(registry: Dict[str, Tool]) -> str:
    lines = []
    for t in registry.values():
        mut = " [needs approval]" if t.mutating else ""
        lines.append(f"- {t.name}({t.args_hint}): {t.description}{mut}")
    return "\n".join(lines)
