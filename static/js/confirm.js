"use strict";

// A form with data-confirm-run asks before it runs an automation's real
// script. The name travels as data and is only ever set as text.
document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form.hasAttribute || !form.hasAttribute("data-confirm-run")) {
        return;
    }
    var name = form.getAttribute("data-confirm-run");
    var ok = window.confirm(
        "This runs the real script for " + name +
        " once, with sample data. Continue?"
    );
    if (!ok) {
        event.preventDefault();
    }
});
