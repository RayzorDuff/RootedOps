"""Run inside authentik Django shell. Preview by default; never log identifiers.
Requires a separately verified Google Directory ID / OAuth identifier equivalence.
Only prepares a new identity; never merges existing identities.
"""
import os
import json
from django.db import transaction
from authentik.core.models import User, Group, Application
from authentik.providers.oauth2.models import OAuth2Provider
from authentik.sources.oauth.models import OAuthSource, UserOAuthSourceConnection

email = os.environ["ROOTEDOPS_WORKSPACE_EMAIL"].strip().lower()
identifier = os.environ["ROOTEDOPS_GOOGLE_IDENTIFIER"].strip()
control_email = os.environ["ROOTEDOPS_CONTROL_EMAIL"].strip().lower()
control_id = os.environ["ROOTEDOPS_CONTROL_GOOGLE_IDENTIFIER"].strip()
apply = os.environ.get("ROOTEDOPS_APPLY") == "YES"
assert email.endswith("@rootedpsyche.org") and email.count("@") == 1
assert control_email.endswith("@rootedpsyche.org") and control_email != email
assert identifier.isascii() and identifier.isdigit() and 10 <= len(identifier) <= 32
assert control_id.isascii() and control_id.isdigit() and control_id != identifier
source = OAuthSource.objects.get(slug="google-rootedpsyche", enabled=True, provider_type="google")
provider = OAuth2Provider.objects.get(pk=Application.objects.get(slug="rootedpsyche-wordpress").provider_id)
assert provider.sub_mode == "hashed_user_id", "Unexpected subject mode; do not change provider"
control = UserOAuthSourceConnection.objects.get(source=source, identifier=control_id)
assert control.user.email.lower() == control_email, "Directory/source control mismatch"
group = Group.objects.get(name="rootedpsyche-board-directors")
with transaction.atomic():
    connection = UserOAuthSourceConnection.objects.filter(source=source, identifier=identifier).select_related("user").first()
    if connection:
        user = connection.user
        assert user.is_active and user.email.lower() == email, "Existing source identity conflicts or inactive"
        assert not user.is_superuser, "Privileged identity excluded"
        assert not User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists()
        assert not UserOAuthSourceConnection.objects.filter(source=source, user=user).exclude(identifier=identifier).exists()
        state = "existing"
    else:
        assert not User.objects.filter(email__iexact=email).exists(), "Existing identity: reconcile separately"
        assert not User.objects.filter(username__iexact=email).exists()
        state = "new"
        user = None
        if apply:
            user = User(username=email, email=email, name=os.environ["ROOTEDOPS_DISPLAY_NAME"], is_active=True)
            user.set_unusable_password()
            user.save()
            UserOAuthSourceConnection.objects.create(user=user, source=source, identifier=identifier)
    if apply:
        user.groups.add(group)
    print("ROOTEDOPS_RESULT=" + json.dumps({"state": state, "applied": apply, "subject": user.uid if user else None}))
