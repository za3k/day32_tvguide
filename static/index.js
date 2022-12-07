'use strict';

function main() {
}

(function(fn) { if (document.readyState === "complete" || document.readyState === "interactive") setTimeout(fn, 1); else document.addEventListener("DOMContentLoaded", fn); })(main);
