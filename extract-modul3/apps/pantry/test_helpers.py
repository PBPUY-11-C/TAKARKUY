from django.contrib.auth import get_user_model


def authenticate(client, username="pantry-test"):
    user = get_user_model().objects.create_user(username=username)
    client.force_login(user)
    return user
