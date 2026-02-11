"use strict";

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function escapeAttr(text) {
    return text
        .replaceAll("&", "&amp;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
}

const BADGE_STYLES = {
    webhook: "background:var(--color-navbar);color:#fff;",
    cron: "background:var(--color-accent-light);color:#fff;",
    template: "background:var(--color-primary);color:#fff;",
    page: "background:#6c757d;color:#fff;",
};

function buildBadge(resultType) {
    const style = BADGE_STYLES[resultType];
    if (!style) return "";
    const label = resultType.charAt(0).toUpperCase() + resultType.slice(1);
    return ' <span style="font-size:0.65rem;' + style + 'padding:1px 5px;border-radius:3px;">' + label + "</span>";
}

function buildResultHtml(results, query) {
    let html = "";
    results.slice(0, 8).forEach(function (result) {
        html += '<a class="search-result-item" href="' + escapeAttr(result.url) + '">';
        html += '<div class="search-result-title">' + escapeHtml(result.title) + buildBadge(result.result_type) + "</div>";
        if (result.description) {
            html += '<div style="font-size:0.78rem;color:#666;padding-top:2px;">' + escapeHtml(result.description).substring(0, 80) + "</div>";
        }
        html += "</a>";
    });

    html += '<a class="search-result-item" href="/search?q=' + encodeURIComponent(query) + '" style="text-align:center;color:var(--color-primary);font-weight:600;">View all results</a>';
    return html;
}

document.addEventListener("DOMContentLoaded", function () {
    const searchInput = document.getElementById("navbar-search");
    const dropdown = document.getElementById("search-dropdown");
    if (!searchInput || !dropdown) return;

    let debounceTimer = null;

    searchInput.addEventListener("input", function () {
        const query = searchInput.value.trim();
        clearTimeout(debounceTimer);

        if (query.length < 2) {
            dropdown.style.display = "none";
            dropdown.innerHTML = "";
            return;
        }

        debounceTimer = setTimeout(function () {
            fetch("/api/search?q=" + encodeURIComponent(query))
                .then(function (resp) { return resp.json(); })
                .then(function (data) {
                    if (!data.results || data.results.length === 0) {
                        dropdown.innerHTML = '<div class="search-result-item" style="color:#999;">No results found</div>';
                    } else {
                        dropdown.innerHTML = buildResultHtml(data.results, query);
                    }
                    dropdown.style.display = "block";
                });
        }, 300);
    });

    document.addEventListener("click", function (e) {
        if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.style.display = "none";
        }
    });

    searchInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            const query = searchInput.value.trim();
            if (query.length >= 2) {
                globalThis.location.href = "/search?q=" + encodeURIComponent(query);
            }
        }
    });
});
