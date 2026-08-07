/* The demo bot's routing and rendering.
 *
 * Routing is literal string checks in a fixed order, exactly as the IDE bot
 * does it — a quoted sentence is a placement question, keywords reach the
 * guide, then goals, then settings. No model decides what the user meant,
 * which is why the same question always takes the same path.
 *
 * Rendering shows the verdict FIRST and never softens it. A refusal that
 * reads like an apology invites the reader to treat it as a failure of
 * politeness rather than as the answer, and the answer is the whole point.
 */
(function () {
  'use strict';

  var log, input, chips;
  var JA = function () { return document.documentElement.lang !== 'en'; };
  function t(ja, en) { return JA() ? ja : en; }

  function esc(s) {
    return String(s).replace(/[&<>]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c];
    });
  }

  function say(html, who) {
    var d = document.createElement('div');
    d.className = 'msg ' + (who || 'bot');
    d.innerHTML = html;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
  }

  function verdictSpan(v) {
    var cls = v === 'ANSWER' ? 'ok'
            : (v.indexOf('AMBIGUOUS') >= 0 ? 'amb' : 'no');
    return '<span class="v ' + cls + '">' + esc(v) + '</span>';
  }

  // ---- renderers ---------------------------------------------------------

  function renderSetting(r) {
    if (r.verdict === 'UNKNOWN_NO_SETTING') {
      return verdictSpan(r.verdict) + '\n'
        + t('そのような設定はありません。推測はしません。',
            'There is no such setting. It does not guess.')
        + '\n<span class="m">' + esc(r.reason || '') + '</span>';
    }
    if (r.verdict === 'UNKNOWN_AMBIGUOUS') {
      return verdictSpan(r.verdict) + '\n'
        + t(r.candidates.length + ' 件が同点で、どれか一つに決められません:',
            r.candidates.length + ' settings match equally well — which did you mean?')
        + '\n' + r.candidates.map(function (c) {
            return '  · ' + esc(c.title) + '  (Settings › ' + esc(c.tab) + ')';
          }).join('\n');
    }
    var out = verdictSpan('ANSWER') + '  <strong>'
      + esc(JA() ? r.title.ja : r.title.en) + '</strong>\n' + esc(r.what)
      + '\n<span class="m">' + esc(r.where) + '</span>';
    if (r.values && r.values.length)
      out += '\n' + t('選べる値: ', 'Values: ')
           + r.values.map(esc).join(', ');
    out += '\n' + (r.cli
      ? t('コマンド: ', 'CLI: ') + esc(r.cli)
      : verdictSpan('UNKNOWN_NO_CLI') + '  '
        + t('この設定は GUI からのみ変更できます。',
            'GUI-only; there is no command for it.'));
    return out;
  }

  function renderGoal(r) {
    if (r.verdict !== 'ANSWER') {
      return verdictSpan('UNKNOWN_NO_RECIPE') + '\n'
        + t('その目的の手順はありません。用意があるのは:',
            'No recipe for that. Available goals:')
        + '\n' + (r.goals || []).map(function (g) {
            return '  · ' + esc(JA() ? g.title.ja : g.title.en);
          }).join('\n');
    }
    return verdictSpan('ANSWER') + '  <strong>'
      + esc(JA() ? r.title.ja : r.title.en) + '</strong>\n'
      + esc(r.summary) + '\n\n'
      + r.steps.map(function (s) {
          var head = s.n + '. ' + esc(s.title ? (JA() ? s.title.ja : s.title.en)
                                              : s.setting);
          var val = s.value ? '  → ' + esc(s.value)
                            : t('  → 自分で選ぶ', '  → your choice');
          var tab = s.tab ? '\n   <span class="m">Settings › ' + esc(s.tab)
                            + (s.applicable ? '' : t('(自分で入力)', '(you enter this)'))
                            + '</span>' : '';
          return head + val + tab + '\n   ' + esc(s.why);
        }).join('\n\n');
  }

  function renderPlacement(r) {
    if (r.verdict === 'UNSUPPORTED_IN_DEMO')
      return verdictSpan('UNSUPPORTED_IN_DEMO') + '\n'
           + esc(JA() ? r.note_ja : r.note_en);
    if (r.verdict !== 'ANSWER')
      return verdictSpan(r.verdict);
    var ruleNote = {
      head_of_topic_phrase: t(
        'は/が の前の句の最後の名詞(主辞後置)。「本町の避難所は」なら 避難所。',
        'The last noun of the topic phrase — Japanese is head-final.'),
      first_content_run: t(
        '主題標識が無いので最初の内容語を採用。',
        'No topic marker, so the first content run is used.')
    }[r.rule] || '';
    var out = verdictSpan('ANSWER') + '  ' + t('この文の配置', 'Placement') + '\n'
      + t('コア: ', 'Core: ') + '<strong>' + esc(r.core || '—') + '</strong>'
      + '\n<span class="m">' + esc(ruleNote) + '</span>';
    if (r.facets.length)
      out += '\n' + t('ファセット: ', 'Facets: ') + r.facets.map(esc).join('、');
    r.poles.forEach(function (p) {
      out += '\n' + t('極: ', 'Pole: ') + esc(p.aspect) + '／' + esc(p.value)
        + ' (' + p.pol + ')  '
        + (p.placed ? t('配置される', 'placed')
                    : t('配置されない — 主語がコアではない',
                        'not placed — predicated of another noun'));
    });
    if (r.pole_note) {
      out += '\n<span class="m">' + (r.pole_note.present.length
        ? t('語彙 ' + r.pole_note.present.join('、') + ' はあるが門を通らなかった'
            + '(複合語の一部か、コア以外の主語)',
            'terms present but gated: ' + r.pole_note.present.join(', '))
        : t('既知の対義語彙がありません。オーバーレイに対を追加すると検出対象になります。',
            'No known opposition here. Add a pair to the grammar overlay to detect it.'))
        + '</span>';
    }
    return out;
  }

  function renderModes(modes) {
    return verdictSpan('ANSWER') + '  '
      + t(modes.length + ' 群のモード', modes.length + ' mode families') + '\n\n'
      + modes.map(function (m) {
          return '<strong>' + esc(JA() ? m.title.ja : m.title.en) + '</strong>'
            + '  <span class="m">Settings › ' + esc(m.tab) + '</span>\n'
            + m.options.map(function (o) {
                return '  · ' + esc(JA() ? o.label.ja : o.label.en) + ' — ' + esc(o.when);
              }).join('\n');
        }).join('\n\n');
  }

  function renderBoard(rows) {
    if (!rows.length) return verdictSpan('UNKNOWN_NO_EVIDENCE');
    return t('2社の発表からの状況板:', 'The board, from two sources:') + '\n\n'
      + rows.map(function (e) {
          var head = '<strong>' + esc(e.core) + '</strong> — ' + esc(e.confidence);
          var d = e.disputed.map(function (x) {
            return '  🔴 ' + x.sides.map(function (s) {
              return esc(s.claim) + '（' + s.sources.map(esc).join('、') + '）';
            }).join(t('  対  ', '  vs  '));
          }).join('\n');
          var st = e.settled.slice(0, 3).map(function (s) {
            return '  ⚪ ' + esc(s.claim) + '（' + s.sources.map(esc).join('、') + '）';
          }).join('\n');
          return [head, d, st].filter(Boolean).join('\n');
        }).join('\n\n');
  }

  // ---- routing -----------------------------------------------------------

  function quoted(q) {
    var pairs = [['「', '」'], ['"', '"'], ['『', '』']];
    for (var i = 0; i < pairs.length; i++) {
      var a = q.indexOf(pairs[i][0]);
      if (a < 0) continue;
      var b = q.indexOf(pairs[i][1], a + 1);
      if (b < 0) continue;
      var inner = q.slice(a + 1, b).trim();
      if (inner.length >= 6) return inner;
    }
    return null;
  }

  var DEMO_A = { source: 'A新聞',
    text: '国道4号は土砂崩れで通行止です。本町の避難所は開設されました。' };
  var DEMO_B = { source: 'B放送',
    text: '国道4号は復旧し通行可能になりました。本町の避難所は閉鎖されました。' };

  function answer(q) {
    var Q = q.toLowerCase();
    var sentence = quoted(q);
    if (sentence) return renderPlacement(window.Vera.explainPlacement(sentence));
    if (/モード|mode/.test(Q)) return renderModes(window.Vera.modes());
    if (/矛盾|食い違|contradict|conflict|状況板|board|デモ|demo/.test(Q))
      return renderBoard(window.Vera.board([DEMO_A, DEMO_B]));
    var goal = window.Vera.matchGoal(q);
    if (goal.verdict === 'ANSWER') return renderGoal(goal);
    var st = window.Vera.settingsLookup(q);
    if (st.verdict !== 'UNKNOWN_NO_SETTING') return renderSetting(st);
    // Neither a known goal nor a known setting: say so, and say what IS known.
    return renderSetting(st) + '\n<span class="m">'
      + t('試せること: 設定名・「独自のAIを作るには」・「文」を引用符で囲んで配置確認・「モード」・「矛盾」',
          'Try: a setting name, "how do I build my own AI", a "quoted sentence" for placement, "modes", or "contradiction".')
      + '</span>';
  }

  function send(text) {
    var q = (text !== undefined ? text : input.value).trim();
    if (!q) return;
    input.value = '';
    say(esc(q), 'me');
    if (!window.Vera || !window.Vera.ready()) {
      say(t('エンジンデータの読み込みに失敗しました。',
            'The engine data failed to load.'));
      return;
    }
    try { say(answer(q)); }
    catch (e) { say(verdictSpan('DEMO_ERROR') + '\n' + esc(String(e))); }
  }

  var CHIPS_JA = ['独自のAIを作るには', 'ollamaのモデルを変えたい',
    '「本町の避難所は閉鎖されました」', 'モード一覧', '矛盾のデモ',
    'ブロックチェーンを有効に'];
  var CHIPS_EN = ['how do I build my own AI', 'change the Ollama model',
    '「避難所は閉鎖されました」', 'modes', 'contradiction demo',
    'enable blockchain'];

  function drawChips() {
    chips.innerHTML = '';
    (JA() ? CHIPS_JA : CHIPS_EN).forEach(function (c) {
      var b = document.createElement('button');
      b.className = 'chip'; b.textContent = c;
      b.onclick = function () { send(c); };
      chips.appendChild(b);
    });
    input.placeholder = t('設定・目的・「文」を入力…',
                          'Ask about a setting, a goal, or a "sentence"…');
  }

  function greet() {
    say(t('Verantyx サポートの体験版です。設定の場所、独自 AI の作り方、'
        + '文がどこに配置されるかを答えます。知らないことは推測せず、'
        + '型付きの判定で返します。',
          'Verantyx support, demo build. It answers where settings live, how to '
        + 'build your own AI, and where a sentence would be placed. What it does '
        + 'not know comes back as a typed verdict, never a guess.'));
  }

  document.addEventListener('DOMContentLoaded', function () {
    log = document.getElementById('log');
    input = document.getElementById('q');
    chips = document.getElementById('chips');
    if (!log) return;
    ['send', 'send-en'].forEach(function (id) {
      var b = document.getElementById(id);
      if (b) b.onclick = function () { send(); };
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') send();
    });
    document.getElementById('lang').addEventListener('change', drawChips);
    drawChips();

    fetch('data/vera.json').then(function (r) { return r.json(); })
      .then(function (j) { window.Vera.load(j); greet(); })
      .catch(function () {
        // file:// blocks fetch in some browsers. Say which failure this is —
        // "the demo is broken" and "your browser blocked a local file" need
        // different responses from the reader.
        say(t('エンジンデータを読み込めませんでした。file:// で開いた場合は'
            + 'ブラウザが読み込みを止めることがあります。ローカルサーバ'
            + '(python3 -m http.server)経由で開いてください。',
              'Could not load the engine data. Opened over file://, some browsers '
            + 'block this — serve the folder (python3 -m http.server) instead.'));
      });
  });
})();
