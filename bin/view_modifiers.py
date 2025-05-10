from functools import wraps
from typing import Callable, Optional, Any, TypeVar

import flask
import werkzeug
import werkzeug.wrappers

F = TypeVar("F", bound=Callable[..., Any])


def response(
    *, mimetype: Optional[str] = None, template_file: Optional[str] = None
) -> Callable[[F], F]:
    def response_inner(f: F) -> F:
        # print("Wrapping in response {}".format(f.__name__), flush=True)

        @wraps(f)
        def view_method(*args, **kwargs) -> flask.Response:
            response_val = f(*args, **kwargs)

            if isinstance(response_val, werkzeug.wrappers.Response):
                return response_val

            if isinstance(response_val, flask.Response):
                return response_val

            if isinstance(response_val, dict):
                model = dict(response_val)
            else:
                model = dict()

            if template_file and not isinstance(response_val, dict):
                raise Exception(
                    "Invalid return type {}, we expected a dict as the return value.".format(
                        type(response_val)
                    )
                )

            if template_file:
                response_val = flask.render_template(
                    template_file, **response_val
                )

            resp = flask.make_response(response_val)
            resp.model = model
            if mimetype:
                resp.mimetype = mimetype

            return resp

        return view_method  # type: ignore

    return response_inner
