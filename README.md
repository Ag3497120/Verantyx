<div align="center">
  <h1>🛡️ Verantyx</h1>
  <p><b>A macOS IDE built around an engine that refuses to guess</b></p>

  <p>
    <a href="https://github.com/Ag3497120/Verantyx/releases/latest"><img src="https://img.shields.io/badge/version-2.4.6-blue?style=flat-square" alt="Version 2.4.6"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square"></a>
  </p>
  <p>
    <a href="README.md">English</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasil)</a> · <a href="README-de.md">Deutsch</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">简体中文</a> · <a href="README-zh-TW.md">繁體中文</a> · <a href="README-ko.md">한국어</a> · <a href="README-ja.md">日本語</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

## The one-sentence version

Verantyx is a macOS IDE carrying **Vera-α**, a deterministic knowledge
engine that answers from stored facts or says — as a **type** — why it
cannot. No language model sits in that path, so the same question always
gets the same answer, and every answer walks back to the sentence it came
from.

```
> 避難所
🚫 UNKNOWN_NO_EVIDENCE
no_candidate_cross
Vera-a standalone does not guess. Pour documents in, or switch to council mode.
```

That is a real transcript from the app against an empty store. An LLM asked
the same question produces a paragraph about shelters, because producing a
paragraph is what it does. Vera-α has nothing stored, so it says so.

## Two engines, switched in the header

The switch sits in the chat header rather than in settings, because the two
produce different **kinds** of answer, and which kind you are reading should
never be something you go and check.

| Mode | What it is | When |
|---|---|---|
| **jgen council** | LLM and agent deliberation, models loaded through JGEN | Exploration, drafting, unfamiliar problems |
| **Vera-a only** | Deterministic. Typed verdicts from stored facts. No LLM in the path | Where being wrong is expensive; audit; citation |

A refusal is never rewritten by a model. The moment it is, the answer stops
being reproducible and citable — which was the entire point of the mode.

## Five modes, one screen

The header picks which character answers, and the screen stays the same
because Vera runs under all of them:

| mode | who answers |
|---|---|
| **jgen 合議** | the council of local models |
| **Vera-a** | the dual path — a model composes, Vera manages memory beside it |
| **Vera** | the store alone. **No LLM anywhere in the turn** |
| **Bot** | the app about itself — settings and UI, from the registry |
| **LLM** | the plain model path |

### The cross is the route, not a logo

The stereo cross is a watermark across the whole surface, lit by the real
call — `VeraRouteState` publishes from the one code path every Vera door
takes, so the light on screen and the work in the engine are the same event.
Only the arms the answer actually evidenced take colour; an arm with no
surface cue stays grey, because a fact without a cue has no arm and painting
one would forge the very thing the gate exists to refuse.

Two crosses exist and are never mixed: the **six arms** are structure
(support/oppose, cause/effect, general/instance) and the **phase** is process
(routing / answered / refused / saving).

### The reply is a console, not a bubble

A transcript of bubbles makes every answer look like the same kind of thing.
Vera's are not:

```text
ANSWER     the reading — verdict, grain n/m, witnesses
EVIDENCE   the named source files behind the shown facets
CONFLICT   both poles held, sides named, verdict downgraded
GAP        a typed refusal — never an error
```

**A refusal is a GAP.** The engine did not fail when it declined; declining
*is* the answer, and rendering that in red beside a warning triangle would
teach the reader that the most valuable behaviour here is a malfunction.

### Memory a person can mark

The ledger shows what the store actually holds. A row moves from 証言 to
「ユーザーの校正」 when a person approves it, and from then on an agent reads
it with that label. The review state lives *beside* the cross, never inside
it: an approval is not testimony the corpus gave, and writing it into the
facets would forge evidence.

### Surfaces are summoned by name

Say 設定 / 記憶 / 画面 / 免許 / モード and the surface arrives in the chat.
The table is closed and the match exact — 「設定を変えたい理由なんだけど」 is
a sentence about settings, not a request to open them — and anything
unmatched falls through untouched.

### Documents are offered, never taken

Attaching a file asks: 「…を Vera-a に入れますか?」 「はい」 ingests it;
anything else leaves it in the conversation only. An attachment is a file you
wanted the conversation to see, which is not the same as a document you want
the store to hold forever.

### Screen presence

Two independent switches, because their costs differ. **Always in front** is
for you — the window you are reading should not sink under the apps Vera
opens. **Excluded from screenshots** is for Vera — its own window was landing
on top of every screenshot it took of other apps. `NSWindow.sharingType =
.none` keeps the window visible to you and invisible to the window server's
capture, verified two ways.

## Growth — what the system does not know

A dedicated screen for the typed unknowns: the failure histogram, recurring
buckets with their classification (`growth_candidate` vs `needs_more_facts`),
the gap graph, and the five review queues. Nothing here is a model's opinion;
every number is a count of typed failures or pending human reviews.

The reason it deserves its own screen: this system's distinctive claim is
that it knows what it does not know, in types with counts. Watching those
numbers shrink is what learning honestly means here — and a reader who
cannot see the unknowns in one place has no way to watch.

Quarantined proposals never act on their own. Growth that bypassed you
would not be growth you can trust.

## What is measured

Every number below comes out of a check in CI that you can re-run. They are
results, not claims.

The measurement that matters is on **real published documents**, because a
planted corpus is graded by whoever wrote it. Two government report series
about the same live disaster — 令和8年熊本地震 — read revision by revision:

| Corpus | Detections | True, by reading | False | Recall |
|---|---|---|---|---|
| 内閣府 damage reports, 4 revisions (252,575 chars) | 8 | **8** | **0** | **8 / 8** |
| 国交省 第N報 series, 4 revisions — *blind* (61,083 chars) | 6 | **6** | **0** | **6 / 6** |

Each detection is one a person can check against the source: 熊本市 listed as
having no water on 29 July and restored by 6 August; 熊本刑務所's shelter
opened on 3 August and closed on the 6th; 直轄国道 clearing after 29 July
while 有料道路 gained a closure on the 6th. All are reported as **updates**
with dates, not as conflicts.

**Recall has a denominator here**, which is the part that is usually missing.
The water table names every affected municipality on both dates, so it *is*
an answer key: read by hand, then compared. The controls hold too —
八代市・宇城市・氷川町, still without water on the last revision, are reported
as still without water and never as restored.

The second row is the one that tests whether any of this generalises. 国交省
uses its own format, and it was ingested with **no code changes** and read
only afterwards. Five of six landed on the first try; the sixth exposed two
layout defects, both fixed structurally, neither mentioning an agency.

| | | How |
|---|---|---|
| Precision, real documents | **14 / 14** | Both corpora above, every detection read against its source |
| Recall, real documents | **8/8 and 6/6** | Against hand-read ground truth, with controls |
| False positives, 21.6 M chars | **1** | 1,742 documents of mixed EN/JA prose · 5,304 polar claims |
| Precision, planted traps | **100%** | Compound nouns, prepositions, subordinate clauses, hypotheticals |
| Recall, planted forms | **100%** | Both languages, canonical and passive/formal register |
| Ingestion | **34 MB in 14s** | CPU only, single-threaded, no GPU |
| Reproducibility | **byte-identical** | Same corpus built twice: same output, same hash |
| Automated checks | **83 + 9** | 83 behavioural forks and 9 eval suites, every CI run |

**The limits, stated here rather than left to be discovered.** Recall is
measured against two corpora, not against every document ever written; both
are Japanese government disaster reports, and a third format may well expose
a third layout defect — that is what the blind run is for, and it will be run
again. The one false positive in 21.6 M characters is English, and it is
honest: two documents using the word *channels* generically about different
situations. And 249 segments in the 内閣府 corpus hold a state word the
vocabulary does not carry — the largest, 障害, is deliberately excluded,
because 「障害のある方」 would otherwise read as a system failure in the
documents written for them.

## What it does with documents

Point it at PDFs, Word files, HTML, CSV, JSON or text — a folder at a time —
and it separates four things it will never blend together:

- **settled** — every source that spoke agrees
- **updated** — the same story told twice, ordered by publication time
- **contested** — sources disagree, with *which source said which side*
- **missing** — a question nobody answered, named as a typed gap

Blending those is what a summary does, and it is what makes a summary
unusable for a decision: the reader cannot tell what is agreed from what is
disputed from what nobody checked.

Time is what separates an update from a dispute. A road closed at 09:00 and
reopened at 15:00 is one story; showing it as a conflict is how an
information officer stops trusting the board. The bar for calling it an
update is deliberately high — every side stamped, stamps comparable,
ordering strict — because demoting a real conflict hides exactly what the
report exists to surface. An unparseable date fails safe: it can leave a
dispute standing, never invent an update.

## Placement is inspectable, and adjustable without code

Every placement decision has a stateable reason, so the bot will state it:

```
> 「本町の避難所は閉鎖されました」
ANSWER  Placement
Core: 避難所   ← the last noun of the topic phrase (Japanese is head-final)
Facets: 本町、閉鎖
Pole: 開設／閉鎖 (−)  placed — the core is the subject of this predicate
```

Adjusting it means adjusting the **grammar**, not hand-moving facts. Drop a
`ja_grammar.json` beside your store and it loads at startup:

```json
{ "antonym_pairs": [["点灯", "消灯"]],
  "predicates": {"点灯": "は点灯しています。"} }
```

The validator refuses bad vocabulary loudly, with every problem named: terms
under two characters (開 lives inside 開始, 公開, 展開), a term carrying both
poles, references pointing at nothing. Nothing half-loads.

There is deliberately **no hand-reordering tool**. Hand-placed facts cannot
be re-derived from their sentences, and reproducibility — the property the
whole system rests on — requires placement to be a pure function of text
plus grammar data.

## Install

Requires macOS 14+ on Apple Silicon and Xcode.

```bash
git clone https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
xcodebuild -project Verantyx.xcodeproj -scheme Verantyx -configuration Release build
```

Or download the DMG from [Releases](https://github.com/Ag3497120/Verantyx/releases/latest).

The engine ships inside the app as a self-contained binary — no Python
install needed to run it. To work on the engine itself, see
[Verantyx-Vera-alpha](https://github.com/Ag3497120/Verantyx-Vera-alpha):
it has zero third-party dependencies for its base install, and CI proves it
by importing every module before installing anything.

## Try it without installing

[`site/`](site/) is a single-page site with the same bot running **in the
page** — no server, no API, no model. Ask where a setting lives, how to
build your own AI, or what a sentence's placement would be.

```bash
cd site && python3 -m http.server 8899
```

The bot's vocabulary and rules are exported from the engine rather than
retyped, and the port is checked against the Python implementation on 15
cases. Its scope is stated on the page: settings, modes, recipes, and
**Japanese** placement. The English grammatical decomposer stays in the full
engine.

## Where this is genuinely useful

Not everywhere. It fits where **being wrong costs more than being silent**,
and where "why is there no answer" is itself actionable:

- **Disaster information** — several agencies, one event, and the question
  "what is actually going on". This is the measured case above: two
  ministries' report series about 令和8年熊本地震, 14 findings, all true, every
  one traceable to the line it came from. Runs offline on a cheap laptop; no
  GPU, because there is no matrix arithmetic anywhere in it.
- **Build and CI failure triage** — 9 confirmed patterns; the failure's name
  points at its remedy
- **Spec vs implementation drift** — where your own documents disagree with
  each other
- **Regulated decisions** — an adverse outcome that must name the missing
  document rather than gesture at a model

And where it does not fit, said plainly: free-form writing, summarisation,
translation, open-domain chat. It does not generate prose. That is not a
weakness being worked on; it is the trade that buys everything above.

## Repository layout

```
cli/VerantyxIDE/     the macOS app (Swift, 242 files)
  Sources/Verantyx/Engine/    JGEN, agents, MCP, memory bridge
  Sources/Verantyx/Views/     UI, including Growth and the mode overview
  Vendor/                     the engine, frozen as a binary
site/                the bilingual site with the in-page bot
docs/                design notes
```

Related repositories:

- [Verantyx-Vera-alpha](https://github.com/Ag3497120/Verantyx-Vera-alpha) — the engine (Python, zero dependencies)
- [verantyx-cli](https://github.com/Ag3497120/verantyx-cli) — v6, origin of the six-axis cross structure

## Contributing

The most useful contribution right now is **a corpus in a format we have not
read yet**. Recall on real documents is measured — 8/8 and 6/6 against
hand-read ground truth — but on two corpora that are both Japanese government
disaster reports. Every defect the second one exposed was in layout reading,
which is exactly where format variation lives, so a third format is the
cheapest way to find the next one. A corpus whose disagreements you already
know about is worth more than any amount of code.

Also welcome, in rough order of value:

- Domain vocabulary packs, with the compound-noun traps they need to survive
- Failure-domain packs for fields we have only seeded (15 of the 17 packs are
  seeded by an AI and explicitly cannot self-calibrate until an expert
  supplies a confirmed case)
- Translations — the site and README are bilingual; more languages welcome
- Speed. The engine is Python and rewrites its store wholesale. Both are
  known and deliberately deprioritised: correctness first, and the failure
  modes are already fenced (WAL journaling, atomic replace) so that
  optimising is safe rather than dangerous.

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
