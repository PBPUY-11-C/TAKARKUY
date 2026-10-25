"""Install before CSRF: receipt bytes stay in bounded memory, never temp files."""

from django.core.files.uploadhandler import MemoryFileUploadHandler, StopUpload
from django.http import JsonResponse

from .receipt_ocr import MAX_IMAGE_BYTES


class ReceiptUploadHandler(MemoryFileUploadHandler):
    def handle_raw_input(self, *args, **kwargs):
        self.activated = True
        self.total_bytes = 0

    def receive_data_chunk(self, raw_data, start):
        self.total_bytes += len(raw_data)
        if self.total_bytes > MAX_IMAGE_BYTES:
            self.request.receipt_too_large = True
            if hasattr(self, "file"):
                self.file.close()
            raise StopUpload(connection_reset=False)
        return super().receive_data_chunk(raw_data, start)


class ReceiptUploadMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/modul2/ocr-fallback/" and request.method == "POST":
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
