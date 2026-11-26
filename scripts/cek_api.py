"""Cek cepat API TAKARKUY: login, panggil satu endpoint GET per modul, lalu logout.

Pakai:  python -m scripts.cek_api https://alfredo-nathaniel-takarkuy.pws.cs.ui.ac.id
Tanpa alamat, skrip memeriksa server lokal http://127.0.0.1:8000. Kata sandi diketik saat
skrip berjalan dan tidak disimpan di mana pun.
"""

import getpass
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

LOGIN = "/api/auth/login/"
LOGOUT = "/api/auth/logout/"
ENDPOINTS = {
    "Planner": "/api/planner/plans/",
    "Pantry": "/api/pantry/items/",
    "Akun": "/api/auth/profile/",
    "Resep": "/api/recipes/?limit=1",
    "Dashboard": "/api/dashboard/summary/",
}


def cek_semua(base_url, username, password):
    """Mengembalikan [(nama, path, status HTTP)]; berhenti setelah login bila login gagal."""
    def call(path, data=None, token=None):
        """Panggil API JSON dengan token pada header bila endpoint memerlukannya."""
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Token {token}"
        request = Request(
            base_url.rstrip("/") + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers,
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read()
                return response.status, json.loads(payload) if payload else {}
        except HTTPError as error:
            return error.code, {}

    status, body = call(LOGIN, {"username": username, "password": password})
    results = [("Login", LOGIN, status)]
    if results[0][2] != 200:
        return results
    token = body.get("token")
    if not token:
        return results
    results += [(name, path, call(path, token=token)[0]) for name, path in ENDPOINTS.items()]
    results.append(("Logout", LOGOUT, call(LOGOUT, {}, token=token)[0]))
    return results


def main():
    """Menjalankan cek dari terminal; keluar dengan kode 1 bila ada endpoint yang gagal."""
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    username = input("Username: ")
    password = getpass.getpass("Kata sandi: ")
    results = cek_semua(base_url, username, password)
    for name, path, status in results:
        success = status == 200 or (name == "Logout" and status == 204)
        print(f"{'OK   ' if success else 'GAGAL'} {status}  {name:<10} {path}")
    sys.exit(0 if all(status == 200 or (name == "Logout" and status == 204) for name, _, status in results) else 1)


if __name__ == "__main__":
    main()
