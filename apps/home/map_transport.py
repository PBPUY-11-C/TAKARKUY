"""Transport HTTP kecil di subprocess: byte dibatasi, tanpa redirect, tenggat total di proses induk."""

import json
import sys
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    """Handler urllib yang menolak semua redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Mengembalikan None agar redirect tidak diikuti dan respons 3xx menjadi error."""
        return None


def fetch(data):
    """Kirim request (POST jika ada body) dan parse JSON; timeout 6 detik, respons maks 512 KiB."""
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
        sys.exit(1)
