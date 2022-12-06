'use strict';

function main() {
    console.log("hi");
}

(function(fn) { if (document.readyState === "complete" || document.readyState === "interactive") setTimeout(fn, 1); else document.addEventListener("DOMContentLoaded", fn); })(main);
