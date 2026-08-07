/* The disaster board's UI.
 *
 * Renders findings, never conclusions. Every row carries its verdict, how
 * old the evidence is, and who said it — because the reader is the one
 * making the decision and the system's job is to hand them what it has,
 * with its age attached.
 *
 * Nothing is hidden. Conflicted and expired places stay on the list: a
 * person shown only the usable places never learns the other ones exist,
 * and may well choose to walk to a place whose status went stale forty
 * minutes ago rather than to one two kilometres further.
 */
(function () {
  'use strict';

  var JA = function () { return document.documentElement.lang !== 'en'; };
  function t(ja, en) { return JA() ? ja : en; }
  function esc(s) {
    return String(s).replace(/[&<>]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c];
    });
  }

  var NOW = 1000;
  /* A fictional afternoon, on purpose. This is a public page: real posts
   * would be real places, and a demo board that looks like live data is a
   * demo that gets screenshotted and shared as if it were. */
  var REPORTS = [
    { place: '市民体育館 給水所', category: 'water', status: 'available',
      at: NOW - 20, reporter: '住民A' },
    { place: '市民体育館 給水所', category: 'water', status: 'available',
      at: NOW - 15, reporter: '住民B', note: '並んでません' },
    { place: '中央公園 給水所', category: 'water', status: 'available',
      at: NOW - 12, reporter: '市の公式ページ', official: true },
    { place: '中央公園 給水所', category: 'water', status: 'out',
      at: NOW - 6, reporter: '住民C', note: '今行ったら終わってました' },
    { place: '駅前スーパー', category: 'food', status: 'open',
      at: NOW - 250, reporter: '住民D', note: '現金のみ' },
    { place: '南小学校 避難所', category: 'shelter', status: 'open',
      at: NOW - 700, reporter: '市の公式ページ', official: true },
    { place: '南小学校 トイレ', category: 'toilet', status: 'unusable',
      at: NOW - 520, reporter: '住民E' },
    { place: '南小学校 トイレ', category: 'toilet', status: 'usable',
      at: NOW - 25, reporter: '住民F', note: '仮設が入りました' },
    { place: '南小学校 授乳室', category: 'infant', status: 'available',
      at: NOW - 40, reporter: '住民G' },
    { place: '公民館 充電', category: 'power', status: 'available',
      at: NOW - 60, reporter: '住民H' },
    { place: '南小学校 スロープ', category: 'accessible', status: 'available',
      at: NOW - 300, reporter: '市の公式ページ', official: true },
    { place: '国道沿い ガソリンスタンド', category: 'fuel', status: 'queue',
      at: NOW - 35, reporter: '住民I', note: '40分待ち' }
  ];

  var picked = new Set(['water']);
  var needsEl, findEl;

  var VERDICT_JA = {
    CONFIRMED: '複数が確認', REPORTED: '1人が報告', CONFLICT: '食い違い',
    EXPIRED: '情報が古い', UNKNOWN_NO_REPORT: '報告なし'
  };
  var STATUS_JA = {
    available: '利用できる', queue: '並んでいる', out: '在庫なし',
    closed: '閉まっている', open: '開いている', limited: '品薄',
    usable: '使える', unusable: '使えない', passable: '通れる',
    restricted: '一部通行止', ongoing: '配布中', ended: '終了',
    full: '満員', unavailable: '利用できない'
  };
  function statusLabel(s) { return JA() ? (STATUS_JA[s] || s) : s; }
  function age(m) {
    if (m === undefined || m === null) return '';
    if (m < 60) return t(m + '分前', m + ' min ago');
    var h = Math.floor(m / 60);
    return t(h + '時間前', h + 'h ago');
  }

  function renderFinding(f) {
    var cats = window.VeraField.categories();
    var catLabel = (cats[f.category] || {})[JA() ? 'ja' : 'en'] || f.category;
    var h = '<div class="find"><div class="top">'
      + '<span class="pl">' + esc(f.place) + '</span>'
      + '<span style="font-size:12px;color:var(--dimmer)">' + esc(catLabel) + '</span>'
      + '<span class="vd ' + f.verdict + '">'
      + esc(JA() ? (VERDICT_JA[f.verdict] || f.verdict) : f.verdict) + '</span>'
      + '<span class="age">' + esc(age(f.age_minutes)) + '</span></div>';

    if (f.verdict === 'CONFLICT') {
      f.sides.forEach(function (s) {
        h += '<div class="side">' + (s.usable ? '○' : '×') + ' <strong>'
          + esc(statusLabel(s.status)) + '</strong> — '
          + esc(s.reporters.join('、'))
          + (s.official ? t('（公式）', ' (official)') : '')
          + ' <span style="color:var(--dimmer)">' + esc(age(s.age_minutes))
          + '</span></div>';
      });
      h += '<div class="why">' + t(
        'どちらとも断定できません。公式発表も一つの側であって答えではなく、'
        + '多数決もしません。',
        'Neither side is preferred; an official notice is one side, not the '
        + 'answer, and there is no majority vote.') + '</div>';
    } else if (f.verdict === 'EXPIRED') {
      h += '<div class="side">'
        + t('最後の報告: ', 'Last reported: ') + esc(statusLabel(f.status))
        + '（' + esc(age(f.age_minutes)) + '）</div>'
        + '<div class="why">' + t(
          '古すぎて、いま使えるかは言えません。<strong>「閉まっている」という意味では'
          + 'ありません。</strong>',
          'Too old to stand behind. <strong>This does not mean it is '
          + 'closed.</strong>') + '</div>';
    } else if (f.verdict === 'UNKNOWN_NO_REPORT') {
      h += '<div class="why">' + t('まだ誰も報告していません。',
                                   'Nobody has reported on this yet.') + '</div>';
    } else {
      h += '<div class="side">' + (f.usable ? '○' : '×') + ' <strong>'
        + esc(statusLabel(f.status)) + '</strong> — '
        + esc((f.reporters || []).join('、')) + '</div>';
      if (f.superseded && f.superseded.length) {
        h += '<div class="why">' + t('それ以前: ', 'Earlier: ')
          + f.superseded.map(function (s) {
              return esc(statusLabel(s.status)) + '（' + esc(age(s.age_minutes)) + '）';
            }).join('、') + '</div>';
      }
      h += '<div class="why">' + esc(
        f.verdict === 'CONFIRMED'
          ? t('複数の人が、最近、同じことを言っています。',
              'More than one person, recently, saying the same thing.')
          : t('1人の報告です。他の人による確認はありません。',
              'One report. Nobody has confirmed it independently.')) + '</div>';
    }
    var notes = REPORTS.filter(function (r) {
      return r.place === f.place && r.category === f.category && r.note;
    }).slice(-2);
    notes.forEach(function (r) {
      h += '<div class="why">💬 ' + esc(r.note) + ' — ' + esc(r.reporter) + '</div>';
    });
    return h + '</div>';
  }

  function draw() {
    if (!window.VeraField || !window.VeraField.ready()) return;
    var defs = window.VeraField.needs();
    needsEl.innerHTML = '';
    Object.keys(defs).forEach(function (k) {
      var b = document.createElement('button');
      b.className = 'need' + (picked.has(k) ? ' on' : '');
      b.textContent = defs[k][JA() ? 'ja' : 'en'];
      b.onclick = function () {
        if (picked.has(k)) picked.delete(k); else picked.add(k);
        draw();
      };
      needsEl.appendChild(b);
    });

    if (!picked.size) {
      findEl.innerHTML = '<div class="why">'
        + t('必要なものを1つ以上選んでください。',
            'Pick at least one thing you need.') + '</div>';
      return;
    }
    var rows = window.VeraField.forNeeds(REPORTS, NOW, Array.from(picked));
    findEl.innerHTML = rows.length
      ? rows.map(renderFinding).join('')
      : '<div class="why">' + t('該当する報告がありません。',
                                'No reports match.') + '</div>';
  }

  document.addEventListener('DOMContentLoaded', function () {
    needsEl = document.getElementById('needs');
    findEl = document.getElementById('findings');
    if (!needsEl) return;
    var sel = document.getElementById('lang');
    if (sel) sel.addEventListener('change', draw);
    fetch('data/field.json').then(function (r) { return r.json(); })
      .then(function (j) { window.VeraField.load(j); draw(); })
      .catch(function () {
        findEl.innerHTML = '<div class="why">' + t(
          'データを読み込めませんでした。file:// で開いた場合はブラウザが'
          + '止めることがあります(python3 -m http.server で開いてください)。',
          'Could not load the data — some browsers block this over file://. '
          + 'Serve the folder with python3 -m http.server instead.') + '</div>';
      });
  });
})();
