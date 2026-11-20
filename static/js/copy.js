"use strict";

// Copy buttons: any .copy-btn inside a .code-wrapper copies the text of
// the wrapper's <code> element. The button reads "Copied" for two
// seconds afterwards, so the result is visible as text and not only as
// a colour change.
(function () {
    var COPIED_RESET_MS = 2000;

    function fallbackCopy(text) {
        var area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        var ok = false;
        try {
            ok = document.execCommand("copy");
        } catch (err) {
            ok = false;
        }
        document.body.removeChild(area);
        return ok;
    }

    function writeText(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text).then(
                function () { return true; },
                function () { return fallbackCopy(text); }
            );
        }
        return Promise.resolve(fallbackCopy(text));
    }

    document.addEventListener("click", function (event) {
        var btn = event.target.closest(".copy-btn");
        if (!btn) {
            return;
        }
        var wrapper = btn.closest(".code-wrapper");
        var code = wrapper && wrapper.querySelector("code");
        if (!code) {
            return;
        }
        writeText(code.textContent).then(function (ok) {
            var idle = btn.getAttribute("data-idle-label") || "Copy";
            btn.setAttribute("data-idle-label", idle);
            btn.textContent = ok ? "Copied" : "Copy failed";
            btn.classList.toggle("copied", ok);
            clearTimeout(btn._copyTimer);
            btn._copyTimer = setTimeout(function () {
                btn.textContent = idle;
                btn.classList.remove("copied");
            }, COPIED_RESET_MS);
        });
    });
})();
