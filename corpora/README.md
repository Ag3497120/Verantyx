# Corpora — how to get the documents the measurements were taken on

The published figures in [../docs/METAMORPHIC.md](../docs/METAMORPHIC.md) and
the README were measured on public Japanese government documents. **They are
not committed here**, for two reasons:

- they are third-party publications, and redistributing them is a
  copyright decision that is not mine to make casually
- disaster bulletins are revised and withdrawn, so a frozen copy would
  quietly diverge from what the ministry is actually publishing

What lives here instead is a **manifest**: the source URL and a SHA-256 for
every file used, plus a fetch script. That makes a measurement reproducible
without redistributing anything, and it makes divergence *visible* — if a
ministry replaces a bulletin, the checksum stops matching and you know the
corpus changed rather than the engine.

## The failure this exists to prevent

The original corpus was downloaded into a session temp directory and lost when
that directory was cleaned. The measurements survived only because each figure
was written into the commit message that introduced it. That is a thin thread
to hang a number on, and this directory is the fix.

## Usage

```bash
python3 -m verantyx.corpus_fetch --manifest corpora/disaster_2026.json --out ./corpora/disaster_2026
python3 -m verantyx.corpus_fetch --manifest corpora/disaster_2026.json --out ./corpora/disaster_2026 --verify
```

`--verify` re-hashes what is on disk and reports every file whose checksum no
longer matches the manifest. A mismatch is not automatically an error — it may
mean the ministry issued a correction — but it must never pass silently, since
a changed corpus invalidates any number measured on it.

Then:

```bash
vera self-evolve ./corpora/disaster_2026
```

## Adding a corpus you measured on

```bash
python3 -m verantyx.corpus_fetch --record ./my_documents \
    --source-map urls.txt --out corpora/my_corpus.json
```

`--source-map` is a two-column file of `filename<TAB>url`. Recording without
one is allowed, and the manifest then carries checksums with no origin — which
is enough to detect drift, and not enough for anyone else to reproduce. Prefer
the URL.

## What is committed here

Manifests only: JSON files listing `{name, url, sha256, bytes}`. No document
content. `.gitignore` excludes the fetched directories.
