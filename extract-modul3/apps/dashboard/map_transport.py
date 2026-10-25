"""Small subprocess HTTP transport: bounded bytes, no redirects, total deadline in parent."""

import json
import sys
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(data):
    request = Request(
        data["url"], data=data.get("body", "").encode() or None, headers=data["headers"]
    )
    with build_opener(NoRedirect()).open(request, timeout=6) as response:
        raw = response.read(524289)
    if len(raw) > 524288:
        raise ValueError("Response too large")
    return json.loads(raw)


if __name__ == "__main__":
    try:
        request = json.loads(sys.stdin.buffer.read(8192))
        sys.stdout.write(json.dumps(fetch(request)))
    except Exception:
        # No provider body, headers, or queries in logs/errors.
        sys.exit(1)
