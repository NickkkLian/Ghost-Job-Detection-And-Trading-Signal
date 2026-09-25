/* Vacancy Signal results page. The page is static; this file binds the family's light/dark toggle and Settings dialog
   (appearance.js), sends the skip link to the first visible heading, keeps focused elements clear of the sticky top bar,
   and computes the comparison line under the chart from the performance table, so the two cannot disagree.
   No network requests (the web fonts are the page's only external requests). */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };

  Appearance.bindToggle($('#theme'));
  Appearance.bindSettings($('#nl-settings-button'));

  // Skip link: the first visible h1 in main, else the first visible h2, else main itself. The address is left alone.
  function firstHeading() {
    var seen = function (x) {
      var r = x.getBoundingClientRect(), cs = getComputedStyle(x);
      return r.width > 2 && r.height > 2 && cs.visibility !== 'hidden' && !/inset\(50%\)|rect\(0/.test(cs.clipPath + cs.clip);
    };
    var pick = function (sel) { return Array.prototype.filter.call(document.querySelectorAll(sel), seen)[0]; };
    var x = pick('main h1') || pick('main h2') || $('main');
    if (x && !x.hasAttribute('tabindex')) x.setAttribute('tabindex', '-1');
    return x;
  }
  $('.skip').addEventListener('click', function (e) { e.preventDefault(); firstHeading().focus(); });

  // In-page links (the plate's "Run the pipeline without the data"): the browser scrolls and keeps the address, but
  // leaves focus on <body>; hand it to the target section's heading so the next Tab continues from there.
  Array.prototype.forEach.call(document.querySelectorAll('a[href^="#"]:not(.skip)'), function (a) {
    a.addEventListener('click', function () {
      var target = document.getElementById(a.getAttribute('href').slice(1));
      if (!target) return;
      var h = target.matches('h1, h2, h3') ? target : (target.querySelector('h2, h3') || target);
      if (!h.hasAttribute('tabindex')) h.setAttribute('tabindex', '-1');
      setTimeout(function () { h.focus(); }, 0);
    });
  });

  // The top bar wraps on narrow screens: focus scrolls clear of its real height (family rule html{scroll-padding-top})
  var bar = $('.topbar');
  var sticky = function () { document.documentElement.style.setProperty('--sticky-top', bar.offsetHeight + 'px'); };
  sticky();
  if (window.ResizeObserver) new ResizeObserver(sticky).observe(bar);

  // Comparison line: differences taken from the table's own figures
  var cell = function (row, attr) {
    var el = document.querySelector('#perf tr[data-row="' + row + '"] [data-' + attr + ']');
    return el ? parseFloat(el.getAttribute('data-' + attr)) : NaN;
  };
  var fmt = function (v, unit) { return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(1) + unit; };
  var total = cell('barbell', 'total') - cell('spy', 'total');
  var diff = $('#diff');
  if (diff && !isNaN(total)) {
    diff.replaceChildren(
      'Ghost Barbell against SPY: ', Object.assign(document.createElement('b'), { textContent: fmt(total, ' pp') }),
      ' total return · Sharpe ' + cell('barbell', 'sharpe').toFixed(2) + ' vs ' + cell('spy', 'sharpe').toFixed(2) +
      ' · worst drawdown ' + fmt(cell('barbell', 'dd'), '%') + ' vs ' + fmt(cell('spy', 'dd'), '%')
    );
  }
})();
