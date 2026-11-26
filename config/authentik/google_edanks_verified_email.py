# authentik OAuth Source User Property Mapping
# Assign ONLY to the trusted, restricted google-edanks OAuth source.
# This runs on the user's first successful Google sign-in and subsequent logins.
# It never grants application roles or access based on an email domain.
#
# Google's v1 userinfo returns verified_email; OIDC may return email_verified. If missing, false or the email
# is outside the expected Workspace, clear the marker (fail closed).
email = info.get("email")
email = email.strip().lower() if isinstance(email, str) else ""
verified = (info.get("verified_email") is True or info.get("email_verified") is True)

return {
    "attributes": {
        "email_verified_address": (
            email if verified and email.endswith("@edanks.com") else ""
        )
    }
}
