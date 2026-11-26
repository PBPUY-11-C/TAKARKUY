"""Endpoint REST Modul 3 untuk autentikasi token, profil, dan preferensi makanan."""

from functools import wraps

from django.contrib.auth import get_user_model, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.db import IntegrityError, transaction
from django.utils.cache import patch_cache_control
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

from .forms import AccountDetailsForm, EmailOrUsernameAuthenticationForm, PreferenceForm, SignUpForm
from .models import UserProfile
from .preferences import preferences_for, profile_for
from .serializers import ProfileSerializer

CONFLICT_MESSAGE = "Profil berubah di perangkat lain. Muat ulang sebelum menyimpan."
INVALID_BODY = "Format data tidak valid."


def private(view):
    """Menandai respons agar tidak di-cache karena berisi data akun."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        """Menjalankan view lalu memasang Cache-Control private, no-store."""
        response = view(request, *args, **kwargs)
        patch_cache_control(response, private=True, no_store=True)
        return response

    return wrapped


def first_error(form):
    """Pesan error pertama dari form, untuk ditampilkan langsung di aplikasi."""
    return next(iter(form.errors.values()))[0]


def form_errors(form):
    """Respons 400 berisi error pertama dan error per field, sama seperti API planner."""
    return Response(
        {"error": first_error(form), "fields": form.errors.get_json_data()},
        status=status.HTTP_400_BAD_REQUEST,
    )


def invalid_body():
    """Respons 400 untuk body yang bukan objek (misalnya list JSON)."""
    return Response({"error": INVALID_BODY}, status=status.HTTP_400_BAD_REQUEST)


def profile_response(user_pk):
    """Profil terbaru user dari database, termasuk preferensi makan."""
    user = get_user_model().objects.get(pk=user_pk)
    profile_for(user)
    preferences_for(user)
    return Response(ProfileSerializer(user).data)


@api_view(["POST"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def login_view(request):
    """Login email/username dan terbitkan token DRF untuk aplikasi mobile."""
    if not isinstance(request.data, dict):
        return Response({"status": False, "message": INVALID_BODY}, status=status.HTTP_400_BAD_REQUEST)
    form = EmailOrUsernameAuthenticationForm(request, data=request.data)
    if not form.is_valid():
        incomplete = "username" in form.errors or "password" in form.errors
        return Response(
            {"status": False, "message": first_error(form)},
            status=status.HTTP_400_BAD_REQUEST if incomplete else status.HTTP_401_UNAUTHORIZED,
        )
    user = form.get_user()
    token, _ = Token.objects.get_or_create(user=user)
    return Response({
        "status": True,
        "username": user.username,
        "token": token.key,
        "message": "Login berhasil.",
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request):
    """Mengakhiri session; tetap 200 bila session sudah habis agar aplikasi selalu bisa keluar."""
    username = request.user.username
    logout(request)
    return Response({"status": True, "username": username, "message": "Logout berhasil."})


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    """Daftar akun baru beserta profil dan preferensi dalam satu transaksi (body JSON), tanpa login
    otomatis; aplikasi lanjut ke endpoint login."""
    if not isinstance(request.data, dict):
        return Response({"status": False, "message": INVALID_BODY}, status=status.HTTP_400_BAD_REQUEST)
    form = SignUpForm(request.data)
    if form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
                profile_for(user)
                preferences_for(user)
        except IntegrityError:
            form.add_error(None, "Username atau email sudah terdaftar. Silakan periksa kembali.")
        else:
            return Response(
                {"status": True, "username": user.username, "message": "Akun berhasil dibuat."},
                status=status.HTTP_201_CREATED,
            )
    return Response(
        {"status": False, "message": first_error(form), "fields": form.errors.get_json_data()},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET"])
@private
def profile_view(request):
    """Detail akun dan preferensi makan milik user yang login; `version` dipakai saat menyimpan."""
    return profile_response(request.user.pk)


@api_view(["POST"])
@private
def profile_update(request):
    """Simpan nama, username, email, dan avatar; baris user dan profil dikunci, version dicek (409 bila
    berubah di perangkat lain), dan ganti email wajib `current_password`."""
    if not isinstance(request.data, dict):
        return invalid_body()
    profile = profile_for(request.user)
    form = AccountDetailsForm(request.data, user=request.user)
    if not form.is_valid():
        return form_errors(form)
    data = form.cleaned_data
    try:
        with transaction.atomic():
            locked = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            current = UserProfile.objects.select_for_update().get(pk=profile.pk)
            if current.version != data["version"]:
                return Response({"error": CONFLICT_MESSAGE}, status=status.HTTP_409_CONFLICT)
            # Cek ulang di dalam kunci: email bisa berubah di perangkat lain setelah form divalidasi.
            if data["email"] != locked.email and not locked.check_password(data["current_password"]):
                return Response({"error": "Kata sandi saat ini tidak cocok."}, status=status.HTTP_409_CONFLICT)
            first, _, last = " ".join(data["full_name"].split()).partition(" ")
            locked.first_name, locked.last_name = first, last
            locked.username, locked.email = data["username"], data["email"]
            locked.save(update_fields=["first_name", "last_name", "username", "email"])
            current.avatar = data["avatar"]
            current.version += 1
            current.save(update_fields=["version", "avatar"])
    except IntegrityError:
        return Response(
            {"error": "Username atau email sudah dipakai. Periksa kembali."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return profile_response(request.user.pk)


@api_view(["POST"])
@private
def preferences_update(request):
    """Simpan preferensi makan dengan cek version (409 bila bentrok); halal_only selalu True seperti web.
    `avoided_ingredients` berisi kode bahan (maksimal 10)."""
    if not isinstance(request.data, dict):
        return invalid_body()
    profile = profile_for(request.user)
    form = PreferenceForm(request.data)
    if not form.is_valid():
        return form_errors(form)
    try:
        with transaction.atomic():
            locked = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            current = UserProfile.objects.select_for_update().get(pk=profile.pk)
            if current.version != form.cleaned_data["version"]:
                return Response({"error": CONFLICT_MESSAGE}, status=status.HTTP_409_CONFLICT)
            food = preferences_for(locked)
            for field in ("targets", "meal_types", "servings", "allergens"):
                setattr(food, field, form.cleaned_data[field])
            food.halal_only = True
            food.save()
            food.avoided_ingredients.set(form.cleaned_data["avoided_ingredients"])
            current.version += 1
            current.save(update_fields=["version"])
    except IntegrityError:
        return Response(
            {"error": "Preferensi belum bisa disimpan. Muat ulang dan coba kembali."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return profile_response(request.user.pk)


@api_view(["POST"])
@private
def password_change(request):
    """Ganti kata sandi (old_password, new_password1, new_password2) dengan baris user terkunci,
    naikkan version profil, dan pertahankan session perangkat ini."""
    if not isinstance(request.data, dict):
        return invalid_body()
    with transaction.atomic():
        locked = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        form = PasswordChangeForm(locked, request.data)
        if not form.is_valid():
            return form_errors(form)
        user = form.save()
        profile = UserProfile.objects.select_for_update().get_or_create(user=locked)[0]
        profile.version += 1
        profile.save(update_fields=["version"])
    update_session_auth_hash(request, user)
    return Response({"status": True, "message": "Kata sandi berhasil diperbarui."})
