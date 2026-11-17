"""Password rules shared by sign-up (schemas.user) and the coordinator account (config). No app imports: config uses it."""

MIN_PASSWORD = 8
MAX_PASSWORD = 128  # login refuses longer passwords without hashing them
# Shown under the sign-up password field; keep in step with check_strength.
PASSWORD_HINT = f"{MIN_PASSWORD} to {MAX_PASSWORD} characters, with an uppercase letter, a lowercase letter and a number. No spaces."


def check_strength(v: str) -> str:
    if not MIN_PASSWORD <= len(v) <= MAX_PASSWORD:
        raise ValueError(f"Password must be {MIN_PASSWORD} to {MAX_PASSWORD} characters")
    if not (any(c.isupper() for c in v) and any(c.islower() for c in v) and any(c.isdigit() for c in v)):
        raise ValueError("Password must contain an uppercase letter, a lowercase letter and a number")
    if any(c.isspace() for c in v):
        raise ValueError("Password must not contain spaces")
    return v
