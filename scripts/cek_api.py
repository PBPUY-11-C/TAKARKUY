"""Cek cepat API TAKARKUY: login, panggil satu endpoint GET per modul, lalu logout.

Pakai:  python -m scripts.cek_api https://alfredo-nathaniel-takarkuy.pws.cs.ui.ac.id
Tanpa alamat, skrip memeriksa server lokal http://127.0.0.1:8000. Kata sandi diketik saat
skrip berjalan dan tidak disimpan di mana pun.
"""

import getpass
import sys
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

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
    opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def call(path, data=None):
        """Status HTTP satu request; cookie session dibawa otomatis oleh opener."""
        try:
            with opener.open(Request(base_url.rstrip("/") + path, data=data), timeout=30) as response:
                return response.status
        except HTTPError as error:
            return error.code

    credentials = urlencode({"username": username, "password": password}).encode()
    results = [("Login", LOGIN, call(LOGIN, credentials))]
    if results[0][2] != 200:
        return results
    results += [(name, path, call(path)) for name, path in ENDPOINTS.items()]
    results.append(("Logout", LOGOUT, call(LOGOUT, b"")))
    return results


def main():
    """Menjalankan cek dari terminal; keluar dengan kode 1 bila ada endpoint yang gagal."""
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    username = input("Username: ")
    password = getpass.getpass("Kata sandi: ")
    results = cek_semua(base_url, username, password)
    for name, path, status in results:
        print(f"{'OK   ' if status == 200 else 'GAGAL'} {status}  {name:<10} {path}")
    sys.exit(0 if all(status == 200 for _, _, status in results) else 1)


if __name__ == "__main__":
    main()
