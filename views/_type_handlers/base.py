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

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class AutomationError(Exception):
    """Raised when an automation operation fails."""

    def __init__(
        self, title: str, message: str, link: Optional[str] = None
    ) -> None:
        self.title = title
        self.message = message
        self.link = link
        super().__init__(message)


class AutomationHandler(ABC):
    """Base class for automation type handlers."""

    tag: str = ""
    display_name: str = ""
    badge_class: str = ""
    icon: str = "webhook.png"
    supports_edit: bool = True
    supports_auth: bool = False

    @abstractmethod
    def get_create_context(self, session_data: Dict) -> Dict[str, Any]:
        """Return extra template context for the create form."""

    @abstractmethod
    def process_create(
        self,
        form: Any,
        files: Any,
        session_data: Dict,
    ) -> Dict[str, Any]:
        """Process a create form submission.

        Returns a dict with:
          - 'entry': the dict to persist
          - 'success_msg': message for success page
          - any extra keys for the success template

        Raises AutomationError on failure.
        """

    @abstractmethod
    def process_edit(
        self,
        form: Any,
        files: Any,
        session_data: Dict,
        existing: Dict,
        all_items: Any,
    ) -> Dict[str, Any]:
        """Process an edit form submission.

        Returns a dict with success info.
        Raises AutomationError on failure.
        """

    @abstractmethod
    def process_delete(
        self, automation: Dict, session_data: Dict
    ) -> Optional[str]:
        """Perform type-specific cleanup on delete.

        Returns an error message string on failure, None on success.
        """

    @abstractmethod
    def get_detail_fields(self, automation: Dict) -> List[Tuple[str, str]]:
        """Return (label, value) pairs for the detail view."""
