# Vendored design-system files

`roster-web.css`, `roster-html.css` and `icons.svg` here, and `templates/vendor/roster-macros.html`,
are generated files from roster-bridge, which turns the
[@blakesteve/roster](https://github.com/blakesteve/roster) design tokens into plain CSS and Jinja macros.
The first line of each file names the roster version and a content hash. Do not edit them by hand:
replace them with newer generated copies.

Only the fork's own pages load them: the Tap Action device pages (`templates/tap/`) and the
Brander pages (`templates/brander/`). The Jamf console pages keep `main.css` and Bootstrap.

## Licences

- The generated CSS and macros are MIT licensed. They contain design-token values derived from
  @blakesteve/roster, used under the MIT License. Copyright (c) 2026 Blake Ball.
- `icons.svg` contains icons from Font Awesome Free (@fortawesome/free-solid-svg-icons,
  https://fontawesome.com), Copyright (c) Fonticons, Inc. The icons are licensed under CC BY 4.0
  (https://creativecommons.org/licenses/by/4.0/); see https://fontawesome.com/license/free.
