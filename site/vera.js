/* Vera in the browser — the same decisions, no server, no model.
 *
 * A faithful port of the parts of the engine a visitor can judge from a
 * chat box: the settings lookup with its typed refusals, the goal recipes,
 * the mode list, and the polarity placement that makes a disagreement
 * visible. Every rule here mirrors one in the Python engine, and the
 * vocabulary is exported from it (data/vera.json) rather than retyped —
 * a demo that drifts from the thing it demonstrates is worse than none.
 *
 * What is deliberately NOT ported: the English grammatical decomposer.
 * The browser demo therefore states plainly that it is a subset, because
 * a visitor who mistakes the subset for the whole will conclude the engine
 * is weaker than it is — and one who mistakes it for MORE will be misled,
 * which is worse.
 */
(function (global) {
  'use strict';

  var DATA = null;
  var CJK = /[぀-ヿ㐀-䶿一-鿿]/;

  function load(json) { DATA = json; }

  // ---- tokenisation, mirroring settings_registry ------------------------
  var STOP = new Set(['how','do','does','did','i','you','the','a','an','to','of',
    'in','on','is','are','can','want','would','like','please','my','me','it',
    'this','that','what','where','which','and','or','for','change','set',
    'setting','settings','option','enable','disable','turn','make','use',
    'using','verantyx','ide','app']);

  function tokens(s) {
    return (s || '').toLowerCase().split(/[^\w.]+/).filter(Boolean);
  }
  function minNameLen(name) { return CJK.test(name) ? 2 : 3; }

  function scoreSetting(st, query) {
    var q = (query || '').toLowerCase(), score = 0;
    var strong = new Set([st.key.toLowerCase()].concat(
      (st.aliases || []).map(function (a) { return a.toLowerCase(); })));
    var weak = [st.title.en.toLowerCase(), st.title.ja.toLowerCase()];
    strong.forEach(function (n) {
      if (n.length >= minNameLen(n) && q.indexOf(n) >= 0) score += 3;
    });
    weak.forEach(function (n) {
      if (n.length >= minNameLen(n) && q.indexOf(n) >= 0) score += 2;
    });
    var entry = new Set(tokens(st.title.en).concat(tokens(st.what)));
    tokens(q).forEach(function (t) {
      if (t.length < 3 || STOP.has(t)) return;
      if (strong.has(t)) score += 3; else if (entry.has(t)) score += 1;
    });
    return score;
  }

  /* Typed lookup. The refusals are the point: UNKNOWN_NO_SETTING rather than
   * a plausible guess, UNKNOWN_AMBIGUOUS rather than silently picking one,
   * and UNKNOWN_NO_CLI for settings that genuinely have no command — the
   * verdict the predecessor bot had no way to express and so invented
   * around. */
  function settingsLookup(query) {
    if (!(query || '').trim())
      return { verdict: 'UNKNOWN_NO_SETTING', reason: 'empty query' };
    var scored = DATA.settings.map(function (s) {
      return { s: s, n: scoreSetting(s, query) };
    }).sort(function (a, b) { return b.n - a.n; });
    if (!scored.length || scored[0].n === 0)
      return { verdict: 'UNKNOWN_NO_SETTING', query: query,
               reason: 'no setting matches these words' };
    var top = scored[0].n;
    var tied = scored.filter(function (x) { return x.n === top; });
    if (tied.length > 1)
      return { verdict: 'UNKNOWN_AMBIGUOUS', query: query,
               candidates: tied.map(function (x) {
                 return { key: x.s.key, title: x.s.title.en, tab: x.s.tab }; }) };
    var s = tied[0].s;
    var out = { verdict: 'ANSWER', key: s.key, title: s.title, what: s.what,
                tab: s.tab, where: 'Settings > ' + s.tab + ' > ' + s.title.en,
                values: s.values };
    if (s.cli) out.cli = s.cli;
    else { out.cli_verdict = 'UNKNOWN_NO_CLI';
           out.cli_reason = 'this setting is changed in the GUI; no CLI command exists'; }
    return out;
  }

  // ---- goals -------------------------------------------------------------
  function matchGoal(query) {
    var q = (query || '').toLowerCase();
    if (!q.trim()) return { verdict: 'UNKNOWN_NO_RECIPE' };
    var scored = DATA.goals.map(function (r) {
      var n = 0;
      (r.keywords || []).forEach(function (k) {
        k = k.toLowerCase();
        if (k.length >= minNameLen(k) && q.indexOf(k) >= 0) n += 3;
      });
      [r.title.en.toLowerCase(), r.title.ja.toLowerCase()].forEach(function (t) {
        if (q.indexOf(t) >= 0) n += 3;
      });
      return { r: r, n: n };
    }).sort(function (a, b) { return b.n - a.n; });
    if (!scored.length || scored[0].n === 0)
      return { verdict: 'UNKNOWN_NO_RECIPE',
               goals: DATA.goals.map(function (r) {
                 return { goal: r.goal, title: r.title }; }) };
    var r = scored[0].r;
    var byKey = {};
    DATA.settings.forEach(function (s) { byKey[s.key] = s; });
    var modesByGroup = {};
    DATA.modes.forEach(function (m) { modesByGroup[m.group] = m; });
    return { verdict: 'ANSWER', goal: r.goal, title: r.title, summary: r.summary,
      steps: r.steps.map(function (st, i) {
        var row = { n: i + 1, why: st.why, value: st.value,
                    applicable: st.applicable, setting: st.setting };
        if (st.setting.indexOf('mode:') === 0) {
          var fam = modesByGroup[st.setting.slice(5)];
          if (fam) { row.kind = 'mode'; row.tab = fam.tab; row.title = fam.title; }
        } else {
          var s = byKey[st.setting];
          if (s) { row.kind = 'setting'; row.tab = s.tab; row.title = s.title; }
        }
        return row;
      }) };
  }

  // ---- placement, mirroring lang.py + polarity.py -------------------------
  var JA_RUN = /[゠-ヿー]+|[㐀-䶿一-鿿0-9０-９]+(?:[いな]|[れめきちりつけ](?=[はがをにでとのへもや、。！？\s]|$))?/g;
  var JA_TOPIC = /^(.*?[㐀-䶿一-鿿゠-ヿー0-9０-９][いなれめきちりつけ]?)[はが]/;
  var ALL_DIGITS = /^[0-9０-９]+$/;
  var KANJI = /[㐀-䶿一-鿿]/;
  var JA_NEG_AFTER = /^(?:さ)?(?:では|じゃ)?(?:あり)?ません|^(?:では|じゃ)?ない|^(?:して|されて|できて)?(?:い|おり)?(?:ない|ません)|^できない|^できません/;

  function jaRuns(text) {
    var stops = new Set(DATA.grammar.stopwords);
    return (String(text || '').match(JA_RUN) || []).filter(function (r) {
      return !stops.has(r) && !ALL_DIGITS.test(r);
    });
  }

  function aspectOf() {
    var m = {};
    DATA.grammar.pairs.forEach(function (p) {
      m[p[0]] = [p[0], '+']; m[p[1]] = [p[0], '-'];
    });
    DATA.grammar.joins.forEach(function (j) { m[j[0]] = [j[1], j[2]]; });
    return m;
  }

  /* Compound guard: a term followed by a kanji is part of a longer noun.
   * 停止線 is a painted stop line and 危険物 is hazardous materials — neither
   * claims a state, and both produced poles before this rule existed. */
  function standaloneIndex(text, term) {
    var at = 0;
    for (;;) {
      at = text.indexOf(term, at);
      if (at < 0) return -1;
      var after = text.slice(at + term.length, at + term.length + 1);
      if (!after || !KANJI.test(after)) return at;
      at += 1;
    }
  }

  function detectJa(sentence) {
    var A = aspectOf(), aliases = DATA.grammar.aliases;
    var terms = Object.keys(A).concat(Object.keys(aliases))
      .sort(function (a, b) { return b.length - a.length; });
    var text = String(sentence || ''), out = [], seen = new Set();
    terms.forEach(function (term) {
      var start = standaloneIndex(text, term);
      if (start < 0) return;
      var canon = aliases[term] || term;
      var hit = A[canon];
      if (!hit || seen.has(canon)) return;
      seen.add(canon);
      var negated = JA_NEG_AFTER.test(text.slice(start + term.length));
      text = text.slice(0, start) + '　'.repeat(term.length)
             + text.slice(start + term.length);
      out.push(negated
        ? { aspect: hit[0], value: 'not_' + canon, pol: hit[1] === '+' ? '-' : '+' }
        : { aspect: hit[0], value: canon, pol: hit[1] });
    });
    return out;
  }

  /* The subject gate — a pole belongs to the noun it is predicated of, and
   * a hypothetical belongs to nobody. Both were measured: without the gate,
   * "the gateway surfaces one installer (brew when available)" filed a claim
   * about brew under the gateway. */
  function jaAnchored(text, noun, word) {
    var pat = new RegExp(esc(noun) + '(?:に関して|について|につきまして)?'
                         + '[^。]{0,12}?[はがも][^。]{0,24}?' + esc(word));
    var m = pat.exec(text);
    if (!m) return false;
    var after = text.slice(m.index + m[0].length, m.index + m[0].length + 8);
    return !/^[のでにと]?(場合|とき|なら|れば|たら)/.test(after);
  }
  function esc(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function explainPlacement(sentence) {
    var s = String(sentence || '').trim();
    if (!s) return { verdict: 'UNKNOWN_EMPTY' };
    if (!CJK.test(s)) {
      return { verdict: 'UNSUPPORTED_IN_DEMO', sentence: s,
        note_ja: 'この体験版は日本語の配置のみ移植しています。英語の文法分解は'
               + 'エンジン本体(Python)にあります。',
        note_en: 'This demo ports the Japanese placement only. The English '
               + 'grammatical decomposer lives in the full engine.' };
    }
    var runs = jaRuns(s);
    var core = runs[0] || null, rule = 'first_content_run';
    var m = JA_TOPIC.exec(s);
    if (m) {
      var topicRuns = jaRuns(m[1]);
      if (topicRuns.length) { core = topicRuns[topicRuns.length - 1];
                              rule = 'head_of_topic_phrase'; }
    }
    var poles = detectJa(s).map(function (p) {
      var word = p.value.replace('not_', '');
      var placed = core ? jaAnchored(s, core, word) : false;
      return { aspect: p.aspect, value: p.value, pol: p.pol, placed: placed };
    });
    var known = Object.keys(aspectOf()).concat(Object.keys(DATA.grammar.aliases));
    var present = known.filter(function (t) { return s.indexOf(t) >= 0; });
    return { verdict: 'ANSWER', sentence: s, core: core, rule: rule,
      facets: runs.filter(function (r) { return r !== core; }),
      poles: poles,
      pole_note: poles.length ? null
        : (present.length
            ? { present: present, why: 'compound_or_other_subject' }
            : { present: [], why: 'no_known_opposition' }) };
  }

  /* Two documents in, the board out. The whole point in one function: what
   * every source agrees on, what they disagree about with attribution, and
   * nothing blended. */
  function board(docs) {
    var A = aspectOf();
    var cores = {};  // core -> { facets:Set, poles: {aspect: {value: [sources]}} }
    docs.forEach(function (doc) {
      String(doc.text || '').split(/(?<=[。．.!?！？])\s*/).forEach(function (raw) {
        var s = raw.trim();
        if (s.length < (CJK.test(s) ? 6 : 12)) return;
        var p = explainPlacement(s);
        if (p.verdict !== 'ANSWER' || !p.core) return;
        var slot = cores[p.core] || (cores[p.core] =
          { facets: {}, poles: {}, sources: {} });
        slot.sources[doc.source] = true;
        p.facets.forEach(function (f) {
          (slot.facets[f] || (slot.facets[f] = {}))[doc.source] = true; });
        p.poles.forEach(function (pole) {
          if (!pole.placed) return;
          var asp = slot.poles[pole.aspect] || (slot.poles[pole.aspect] = {});
          (asp[pole.value] || (asp[pole.value] = {}))[doc.source] = true;
        });
      });
    });
    return Object.keys(cores).map(function (core) {
      var slot = cores[core];
      var disputed = [], settled = [];
      Object.keys(slot.poles).forEach(function (aspect) {
        var vals = Object.keys(slot.poles[aspect]);
        if (vals.length > 1) {
          disputed.push({ aspect: aspect, sides: vals.map(function (v) {
            return { claim: v, sources: Object.keys(slot.poles[aspect][v]) }; }) });
        }
      });
      var contestedWords = {};
      disputed.forEach(function (d) {
        d.sides.forEach(function (x) { contestedWords[x.claim] = true; }); });
      Object.keys(slot.facets).forEach(function (f) {
        if (!contestedWords[f])
          settled.push({ claim: f, sources: Object.keys(slot.facets[f]) });
      });
      return { core: core, disputed: disputed, settled: settled,
               confidence: disputed.length ? 'contested'
                         : (settled.length ? 'supported' : 'unknown') };
    }).filter(function (e) { return e.disputed.length || e.settled.length; });
  }

  global.Vera = { load: load, settingsLookup: settingsLookup,
                  matchGoal: matchGoal, explainPlacement: explainPlacement,
                  board: board, modes: function () { return DATA.modes; },
                  ready: function () { return !!DATA; } };
})(window);
