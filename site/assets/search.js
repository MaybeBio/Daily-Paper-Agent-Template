(function () {
  'use strict';

  function foldSearchText(value) {
    return String(value).normalize('NFKD').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
  }

  function queryTokens(query) {
    var tokens = [], seen = {};
    var re = /"([^"]+)"|“([^”]+)”|(\S+)/g, m;
    while ((m = re.exec(query.slice(0, 200)))) {
      var tok = foldSearchText(m[1] || m[2] || m[3]);
      if (tok && !seen[tok]) { seen[tok] = true; tokens.push(tok); }
    }
    return tokens;
  }

  function prepareSearch(documents) {
    return documents.map(function (doc) {
      return {
        document: doc,
        fields: [
          [doc.title, 18], [doc.subtitle, 14], [doc.tags.join(' '), 10],
          [doc.summary, 6], [doc.meta.join(' '), 4], [doc.abstract, 1]
        ].map(function (f) {
          return { text: foldSearchText(String(f[0])), weight: Number(f[1]) };
        })
      };
    });
  }

  function buildMerged(hotIndex, deepMap) {
    return hotIndex.map(function (entry) {
      var deepText = deepMap[entry.document.id] || '';
      entry.document.deep = deepText;
      var fields = entry.fields.slice();
      fields.push({ text: foldSearchText(deepText), weight: 1 });
      return { document: entry.document, fields: fields };
    });
  }

  function searchDocuments(index, query) {
    var tokens = queryTokens(query);
    if (!tokens.length) return [];
    var phrase = tokens.join('');
    return index.flatMap(function (entry) {
      var score = 0;
      for (var i = 0; i < tokens.length; i++) {
        var token = tokens[i];
        var match = entry.fields.find(function (f) { return f.text.indexOf(token) !== -1; });
        if (!match) return [];
        score += match.weight;
      }
      if (entry.fields[0].text === phrase) score += 80;
      else if (entry.fields[0].text.indexOf(phrase) !== -1) score += 24;
      if (entry.fields[1].text === phrase) score += 60;
      else if (entry.fields[1].text.indexOf(phrase) !== -1) score += 16;
      return [{ document: entry.document, score: score }];
    }).sort(function (a, b) {
      return (b.score - a.score) || b.document.date.localeCompare(a.document.date)
        || a.document.title.localeCompare(b.document.title, 'zh-CN');
    });
  }

  function foldedPositions(value) {
    var text = '', offset = 0, starts = [], ends = [];
    for (var i = 0; i < value.length; i++) {
      var ch = value[i], folded = foldSearchText(ch);
      text += folded;
      for (var j = 0; j < folded.length; j++) { starts.push(offset); ends.push(offset + ch.length); }
      offset += ch.length;
    }
    return { text: text, starts: starts, ends: ends };
  }

  function highlightParts(value, tokens) {
    var fp = foldedPositions(value), ranges = [];
    tokens.filter(Boolean).forEach(function (token) {
      var from = 0, idx;
      while ((idx = fp.text.indexOf(token, from)) !== -1) {
        ranges.push([fp.starts[idx], fp.ends[idx + token.length - 1]]);
        from = idx + token.length;
      }
    });
    ranges.sort(function (a, b) { return a[0] - b[0]; });
    var merged = [];
    ranges.forEach(function (r) {
      var last = merged[merged.length - 1];
      if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
      else merged.push([r[0], r[1]]);
    });
    var parts = [], cursor = 0;
    merged.forEach(function (range) {
      if (range[0] > cursor) parts.push({ text: value.slice(cursor, range[0]), matched: false });
      parts.push({ text: value.slice(range[0], range[1]), matched: true });
      cursor = range[1];
    });
    if (cursor < value.length) parts.push({ text: value.slice(cursor), matched: false });
    return parts;
  }

  function searchSnippet(doc, tokens, length) {
    length = length || 180;
    var candidates = [doc.summary, doc.abstract, doc.deep || '', doc.subtitle, doc.meta.join(' '), doc.tags.join(' ')];
    var value = candidates.find(function (t) { return tokens.some(function (tok) { return foldSearchText(t).indexOf(tok) !== -1; }); }) || doc.summary;
    if (value.length <= length) return value;
    var fp = foldedPositions(value);
    var positions = tokens.map(function (tok) { return fp.text.indexOf(tok); }).filter(function (i) { return i >= 0; });
    var position = positions.length ? fp.starts[Math.min.apply(null, positions)] : 0;
    var start = Math.min(Math.max(0, position - 45), Math.max(0, value.length - length));
    if (start > 0 && /[\uDC00-\uDFFF]/.test(value[start])) start--;
    var end = Math.min(value.length, start + length);
    if (end < value.length && /[\uDC00-\uDFFF]/.test(value[end])) end++;
    return (start ? '…' : '') + value.slice(start, end) + (end < value.length ? '…' : '');
  }

  var root = document.querySelector('[data-search-root]');
  if (!root) return;
  var input = document.getElementById('search-query');
  var submit = document.getElementById('search-submit');
  var deepToggle = document.getElementById('search-deep');
  var results = document.getElementById('search-results');
  var status = document.getElementById('search-status');
  var empty = document.getElementById('search-empty');
  var deepHint = document.getElementById('search-deep-hint');
  var more = document.getElementById('search-more');
  var hotIndexPromise, deepPromise, hits = [], tokens = [], shown = 0, revision = 0, timer;
  var deepOn = false, mergedIndex = null;

  function loadIndex() {
    if (!hotIndexPromise) {
      hotIndexPromise = fetch(root.dataset.indexUrl)
        .then(function (r) { if (!r.ok) throw new Error('index unavailable'); return r.json(); })
        .then(function (payload) {
          if (payload.version !== 1 || !Array.isArray(payload.documents)) throw new Error('invalid index');
          return prepareSearch(payload.documents);
        })
        .catch(function (e) { hotIndexPromise = undefined; throw e; });
    }
    return hotIndexPromise;
  }

  function loadDeep() {
    if (!deepPromise) {
      deepPromise = fetch(root.dataset.deepIndexUrl)
        .then(function (r) { if (!r.ok) throw new Error('deep index unavailable'); return r.json(); })
        .then(function (payload) {
          if (payload.version !== 1 || !Array.isArray(payload.documents)) throw new Error('invalid deep index');
          var map = {};
          payload.documents.forEach(function (d) { map[d.id] = d.deep || ''; });
          return map;
        })
        .catch(function (e) { deepPromise = undefined; throw e; });
    }
    return deepPromise;
  }

  function mergedIndexPromise() {
    if (mergedIndex) return Promise.resolve(mergedIndex);
    return Promise.all([loadIndex(), loadDeep()])
      .then(function (pair) {
        mergedIndex = buildMerged(pair[0], pair[1]);
        return mergedIndex;
      })
      .catch(function () {
        return loadIndex();
      });
  }

  function highlight(el, value) {
    highlightParts(value, tokens).forEach(function (part) {
      if (part.matched) {
        var mark = document.createElement('mark');
        mark.textContent = part.text;
        el.appendChild(mark);
      } else {
        el.appendChild(document.createTextNode(part.text));
      }
    });
  }

  function appendResults() {
    var frag = document.createDocumentFragment();
    hits.slice(shown, shown + 20).forEach(function (item) {
      var doc = item.document;
      var article = document.createElement('article');
      article.className = 'search-result';
      var meta = document.createElement('div');
      meta.className = 'search-result-meta';
      doc.meta.forEach(function (m) {
        var span = document.createElement('span');
        highlight(span, m);
        meta.appendChild(span);
      });
      var heading = document.createElement('h2');
      var link = document.createElement('a');
      link.href = doc.url;
      highlight(link, doc.title);
      heading.appendChild(link);
      var snippet = document.createElement('p');
      snippet.className = 'search-result-snippet';
      highlight(snippet, searchSnippet(doc, tokens));
      article.appendChild(meta);
      article.appendChild(heading);
      article.appendChild(snippet);
      frag.appendChild(article);
    });
    results.appendChild(frag);
    shown = Math.min(shown + 20, hits.length);
    more.hidden = shown >= hits.length;
    more.textContent = '显示更多结果（还有 ' + (hits.length - shown) + ' 条）';
    status.textContent = '找到 ' + hits.length + ' 条结果' + (shown < hits.length ? '，已显示 ' + shown + ' 条' : '') + ' · 按相关性排序';
  }

  function update() {
    var current = ++revision;
    var query = input.value.trim();
    tokens = queryTokens(query);
    results.innerHTML = '';
    more.hidden = true;
    if (!tokens.length) { status.textContent = '输入关键词开始搜索'; empty.hidden = true; deepHint.hidden = true; return; }
    empty.hidden = true;
    deepHint.hidden = true;
    status.textContent = '正在搜索…';
    var ready = deepOn ? mergedIndexPromise() : loadIndex();
    ready.then(function (index) {
      if (current !== revision) return;
      hits = searchDocuments(index, query);
      shown = 0;
      appendResults();
      deepHint.hidden = !(!hits.length && !deepOn);
      if (!hits.length) empty.hidden = false;
    }).catch(function () {
      if (current !== revision) return;
      status.textContent = '暂时无法加载搜索，请重试。';
    });
  }

  function runSearch() {
    clearTimeout(timer);
    var url = new URL(window.location.href);
    if (input.value.trim()) url.searchParams.set('q', input.value.trim());
    else url.searchParams.delete('q');
    if (url.href !== window.location.href) window.history.replaceState(null, '', url);
    update();
  }

  submit.addEventListener('click', function (e) { e.preventDefault(); runSearch(); });
  input.addEventListener('input', function (e) {
    clearTimeout(timer);
    revision++;
    if (!e.isComposing) timer = setTimeout(runSearch, 150);
  });
  input.addEventListener('compositionend', function () { clearTimeout(timer); timer = setTimeout(runSearch, 150); });
  more.addEventListener('click', appendResults);
  deepToggle.addEventListener('change', function () {
    deepOn = deepToggle.checked;
    update();
  });
  function restoreURL() {
    var params = new URLSearchParams(window.location.search);
    input.value = (params.get('q') || '').slice(0, 200);
    update();
  }
  window.addEventListener('popstate', restoreURL);
  restoreURL();
})();
