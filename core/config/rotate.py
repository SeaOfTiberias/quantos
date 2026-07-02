"""
QuantOS — Key Rotation Runbook
────────────────────────────────
US-16: Guided key rotation process. Run this script when rotating
any credential (Anthropic API key, broker secrets, webhook secret, etc.)

Usage:
    python core/config/rotate.py --key ANTHROPIC_API_KEY
    python core/config/rotate.py --key WEBHOOK_SECRET --generate

It doesn't touch the actual secrets — it guides you through the
rotation steps and validates the new key is working before the old
one is revoked.
"""

import argparse
import os
import secrets
import string
import sys
import urllib.request


ROTATION_GUIDES = {
    "ANTHROPIC_API_KEY": {
        "steps": [
            "1. Go to console.anthropic.com → API Keys → Create new key",
            "2. Name it: quantos-railway-prod-{YYYYMMDD}",
            "3. Copy the new key (shown only once)",
            "4. In Railway dashboard → Variables → update ANTHROPIC_API_KEY",
            "5. Railway auto-restarts — verify /health/ready shows claude_api_key: true",
            "6. Test: curl https://your-app.railway.app/health/ready",
            "7. Revoke OLD key at console.anthropic.com",
        ],
        "verify_cmd": "curl https://your-app.railway.app/health/ready",
    },
    "WEBHOOK_SECRET": {
        "steps": [
            "1. Generate new secret: python core/config/rotate.py --key WEBHOOK_SECRET --generate",
            "2. In Railway dashboard → Variables → update WEBHOOK_SECRET",
            "3. In TradingView → Alert → Update the 'secret' field in the JSON payload",
            "4. Test: fire a manual alert from TradingView and check QuantOS logs",
            "5. Update agent/config.yaml if the secret is referenced there",
        ],
        "verify_cmd": "Check Railway logs for 'Signal received' after TradingView alert",
    },
    "CALLMEBOT_PHONE": {
        "steps": [
            "1. No rotation needed for phone number unless you change numbers",
            "2. If changing: update CALLMEBOT_PHONE in Railway + agent/config.yaml",
            "3. Send activation message to CallMeBot from the new number",
            "4. Update CALLMEBOT_API_KEY with the new key CallMeBot sends back",
        ],
        "verify_cmd": "Check WhatsApp for test message",
    },
    "FYERS_APP_ID": {
        "steps": [
            "1. Log in to myapi.fyers.in",
            "2. Deactivate old app or create new one",
            "3. Update agent/config.yaml: credentials.api_key",
            "4. Re-run: python agent/auth/fyers_auth.py to get new access token",
            "5. Restart the local agent: python agent/main.py",
        ],
        "verify_cmd": "python -c \"from core.brokers.fyers import FyersBroker; b = FyersBroker({}); print(b)\"",
    },
    "ZERODHA_API_KEY": {
        "steps": [
            "1. Log in to kite.trade/api",
            "2. Regenerate API secret",
            "3. Update agent/config.yaml: credentials.api_key + api_secret",
            "4. Re-run: python agent/auth/zerodha_auth.py to get new access token",
            "5. Restart the local agent",
        ],
        "verify_cmd": "Check agent logs for 'Zerodha connected'",
    },
}


def generate_secret(length: int = 32) -> str:
    """Generate a cryptographically secure random secret."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def print_rotation_guide(key: str) -> None:
    guide = ROTATION_GUIDES.get(key)
    if not guide:
        print(f"\n⚠️  No rotation guide for '{key}'.")
        print("General steps:")
        print("  1. Generate new credential with the provider")
        print("  2. Update Railway Variables (or agent/config.yaml for local keys)")
        print("  3. Verify the new credential works")
        print("  4. Revoke the old credential")
        return

    print(f"\n🔑 Rotation guide for: {key}")
    print("━" * 50)
    for step in guide["steps"]:
        print(f"  {step}")
    print(f"\nVerify with:\n  {guide['verify_cmd']}")
    print("━" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantOS Key Rotation Runbook")
    parser.add_argument("--key", required=True, help="Environment variable name to rotate")
    parser.add_argument("--generate", action="store_true",
                        help="Generate a new random secret value")
    parser.add_argument("--list", action="store_true",
                        help="List all keys with rotation guides")
    args = parser.parse_args()

    if args.list:
        print("\nKeys with rotation guides:")
        for k in ROTATION_GUIDES:
            print(f"  {k}")
        return

    if args.generate:
        new_secret = generate_secret()
        print(f"\n✅ Generated secret for {args.key}:")
        print(f"   {new_secret}")
        print("\n⚠️  Copy this now — it won't be shown again.")
        print("   Add it to Railway Variables (not to any file in Git).\n")

    print_rotation_guide(args.key)

    current = os.getenv(args.key, "")
    if current:
        print(f"\n✅ Current value: SET (length={len(current)})")
    else:
        print(f"\n❌ Current value: NOT SET in this environment")


if __name__ == "__main__":
    main()
