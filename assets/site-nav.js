/* Field Brief site chrome: folder menus, mobile toggle, keyboard support.
   Progressive: assets/site-nav.css renders a usable link list when this file does not run.
   Spec: research/site-nav-spec.md */
(function () {
  "use strict";
  var bar = document.querySelector(".site-topbar[data-site-nav]");
  if (!bar) return;
  var nav = bar.querySelector(".site-nav");
  var toggle = bar.querySelector(".site-nav-toggle");
  var folders = Array.prototype.slice.call(bar.querySelectorAll(".site-nav-folder"));
  var mobile = window.matchMedia("(max-width: 860px)");
  bar.classList.add("site-nav-js");

  // Pages generated elsewhere may ship without aria-current; mark the exact match for this location.
  if (nav && !nav.querySelector("[aria-current]")) {
    var here = location.pathname.replace(/index\.html$/, "");
    Array.prototype.forEach.call(nav.querySelectorAll("a[href]"), function (a) {
      if (a.getAttribute("href") !== here) return;
      a.setAttribute("aria-current", "page");
      var folder = a.closest(".site-nav-folder");
      if (folder) folder.setAttribute("data-active", "true");
    });
  }

  function button(f) { return f.querySelector(".site-nav-folder-button"); }
  function links(f) { return Array.prototype.slice.call(f.querySelectorAll(".site-nav-menu a")); }
  function isOpen(f) { return f.getAttribute("data-open") === "true"; }
  function setOpen(f, open) {
    f.setAttribute("data-open", open ? "true" : "false");
    button(f).setAttribute("aria-expanded", open ? "true" : "false");
    if (!open || mobile.matches) return;
    // A panel that would run past the right edge of the viewport hangs from the button's right edge instead.
    var menu = f.querySelector(".site-nav-menu");
    f.removeAttribute("data-align");
    if (menu.getBoundingClientRect().right > document.documentElement.clientWidth) f.setAttribute("data-align", "right");
  }
  function closeAll(except) { folders.forEach(function (f) { if (f !== except && isOpen(f)) setOpen(f, false); }); }
  function setMenu(open) {
    if (!toggle) return;
    bar.setAttribute("data-open", open ? "true" : "false");
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (!open) closeAll();
  }

  folders.forEach(function (f) {
    var btn = button(f);
    btn.addEventListener("click", function () {
      var open = !isOpen(f);
      closeAll(f);
      setOpen(f, open);
    });
    btn.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      e.stopPropagation(); // the folder handler below would otherwise move focus a second time
      closeAll(f);
      setOpen(f, true);
      var items = links(f);
      (e.key === "ArrowDown" ? items[0] : items[items.length - 1]).focus();
    });
    f.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        if (!isOpen(f)) return;
        e.preventDefault();
        e.stopPropagation();
        setOpen(f, false);
        btn.focus();
        return;
      }
      var items = links(f);
      var i = items.indexOf(document.activeElement);
      if (i < 0) return;
      var next = null;
      if (e.key === "ArrowDown") next = items[(i + 1) % items.length];
      else if (e.key === "ArrowUp") next = items[(i - 1 + items.length) % items.length];
      else if (e.key === "Home") next = items[0];
      else if (e.key === "End") next = items[items.length - 1];
      if (next) { e.preventDefault(); e.stopPropagation(); next.focus(); } // consumed: page shortcuts (demo Home/End) must not fire
    });
    // Tabbing out of a folder closes it; a click that lands outside is handled below.
    f.addEventListener("focusout", function (e) {
      if (e.relatedTarget && !f.contains(e.relatedTarget)) setOpen(f, false);
    });
  });

  if (toggle) {
    toggle.addEventListener("click", function () { setMenu(bar.getAttribute("data-open") !== "true"); });
  }

  document.addEventListener("click", function (e) {
    if (bar.contains(e.target)) return;
    closeAll();
    if (mobile.matches) setMenu(false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (folders.some(isOpen)) { closeAll(); return; }
    if (toggle && bar.getAttribute("data-open") === "true") { setMenu(false); toggle.focus(); }
  });
  var onViewport = function () { closeAll(); setMenu(false); };
  if (mobile.addEventListener) mobile.addEventListener("change", onViewport); else mobile.addListener(onViewport);
})();
