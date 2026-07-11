# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2026 Jamf.  All rights reserved.
#
#       Redistribution and use in source and binary forms, with or without
#       modification, are permitted provided that the following conditions are met:
#               * Redistributions of source code must retain the above copyright
#                 notice, this list of conditions and the following disclaimer.
#               * Redistributions in binary form must reproduce the above copyright
#                 notice, this list of conditions and the following disclaimer in the
#                 documentation and/or other materials provided with the distribution.
#               * Neither the name of the Jamf nor the names of its contributors may be
#                 used to endorse or promote products derived from this software without
#                 specific prior written permission.
#
#       THIS SOFTWARE IS PROVIDED BY JAMF SOFTWARE, LLC "AS IS" AND ANY
#       EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#       WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#       DISCLAIMED. IN NO EVENT SHALL JAMF SOFTWARE, LLC BE LIABLE FOR ANY
#       DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
#       (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#       LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
#       ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#       (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#       SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

"""URL-safety helpers for building local redirect targets (bug B8).

Several legacy compatibility routes build a redirect ``Location`` by
interpolating a user-controlled value straight into a path string
(``f"/automations/{name}/edit"``). A value such as ``//evil.com`` or
``/\\evil.com`` turns the result into a protocol-relative URL that the
browser resolves off-site (open redirect / phishing; CodeQL
``py/url-redirection``).

This module has no third-party imports, so it is safe to import from
``app.py`` and any blueprint without creating an import cycle.
"""


def safe_path_segment(value: str) -> str:
    """Sanitize a user value that will be interpolated as a *single*
    path segment in a local redirect target.

    The interpolated value is an automation name and must never contain
    a path separator. Stripping every slash and backslash guarantees the
    result cannot introduce an extra segment, a ``//`` run, or a
    ``/\\`` sequence -- the three ways an interpolated value can make the
    final path protocol-relative or otherwise escape its intended slot.

    Returns a bare segment safe to embed in an f-string path.
    """
    if not value:
        return ""
    return value.replace("/", "").replace("\\", "")
