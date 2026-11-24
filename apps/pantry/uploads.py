"""Pasang sebelum CSRF: byte foto struk tetap di memori yang dibatasi, tidak pernah ke file temp."""

from django.core.files.uploadhandler import MemoryFileUploadHandler, StopUpload
from django.http import JsonResponse

from .receipt_ocr import MAX_IMAGE_BYTES

SCAN_PATHS = {"/pantry/ocr-fallback/", "/api/pantry/receipt/scan/"}


class ReceiptUploadHandler(MemoryFileUploadHandler):
    """Upload handler foto struk yang selalu menyimpan di memori dan berhenti di batas ukuran."""

    def handle_raw_input(self, *args, **kwargs):
        """Memaksa handler memori aktif berapa pun ukurannya dan mereset hitungan byte."""
        self.activated = True
        self.total_bytes = 0

    def receive_data_chunk(self, raw_data, start):
        """Menghitung byte masuk; lewat MAX_IMAGE_BYTES, request ditandai dan upload dihentikan."""
        self.total_bytes += len(raw_data)
        if self.total_bytes > MAX_IMAGE_BYTES:
            self.request.receipt_too_large = True
            if hasattr(self, "file"):
                self.file.close()
            raise StopUpload(connection_reset=False)
        return super().receive_data_chunk(raw_data, start)


class ReceiptUploadMiddleware:
    """Middleware yang memasang ReceiptUploadHandler khusus untuk POST ke endpoint OCR fallback (web dan API mobile)."""

    def __init__(self, get_response):
        """Menyimpan handler berikutnya dalam rantai middleware."""
        self.get_response = get_response

    def __call__(self, request):
        """Menolak Content-Length tidak valid (400) atau terlalu besar (413) sebelum body dibaca.

        Bila handler menandai foto melebihi batas saat streaming, respons diganti 413.
        """
        if request.path in SCAN_PATHS and request.method == "POST":
            try:
                length = int(request.META.get("CONTENT_LENGTH") or 0)
            except ValueError:
                return JsonResponse({"error": "Ukuran request tidak valid."}, status=400)
            if length > MAX_IMAGE_BYTES + 1024 * 1024:
                return JsonResponse({"error": "Foto maksimal 10 MB."}, status=413)
            request.upload_handlers = [ReceiptUploadHandler(request)]
        response = self.get_response(request)
        if getattr(request, "receipt_too_large", False):
            return JsonResponse({"error": "Foto maksimal 10 MB."}, status=413)
        return response
