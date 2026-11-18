from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    """Backend autentikasi yang menerima email atau username, keduanya tanpa membedakan huruf besar."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        """Cari akun lewat email (bila ada @) lalu username; tetap hash password saat akun tidak ada
        agar waktu respons tidak membocorkan apakah akun terdaftar."""
        if not isinstance(username, str) or not isinstance(password, str):
            return None
        identifier = username.strip()
        users = get_user_model().objects
        try:
            if "@" in identifier:
                user = users.filter(email__iexact=identifier).first()
                if user is None:
                    user = users.get(username__iexact=identifier)
            else:
                user = users.get(username__iexact=identifier)
        except (get_user_model().DoesNotExist, get_user_model().MultipleObjectsReturned):
            user = None
        if user is None:
            get_user_model()().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
