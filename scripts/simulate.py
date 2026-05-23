"""Simulador CLI para probar a RAI sin Twilio ni WhatsApp.

Uso:
    python scripts/simulate.py [--phone whatsapp:+34600123456]

Escribe mensajes y pulsa Enter. `:quit` para salir, `:lead` para ver el lead actual.
"""

import argparse
import json
import sys

from app import db
from app.agent import handle_user_message


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", default="whatsapp:+34600000001")
    args = parser.parse_args()

    db.init_db()
    print(f"=== RAI demo (simulando teléfono {args.phone}) ===")
    print("Comandos: ':quit' salir | ':lead' ver lead actual | ':reset' borrar lead")
    print()

    while True:
        try:
            user_text = input("Tú > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not user_text:
            continue
        if user_text == ":quit":
            return 0
        if user_text == ":lead":
            lead = db.get_or_create_lead(args.phone)
            print(json.dumps(lead, indent=2, ensure_ascii=False))
            continue
        if user_text == ":reset":
            import sqlite3
            from app.config import settings
            conn = sqlite3.connect(settings.database_path)
            conn.execute("DELETE FROM messages WHERE lead_id IN (SELECT id FROM leads WHERE phone = ?)", (args.phone,))
            conn.execute("DELETE FROM leads WHERE phone = ?", (args.phone,))
            conn.commit()
            conn.close()
            print("(lead borrado)")
            continue

        reply = handle_user_message(phone=args.phone, user_text=user_text)
        print(f"RAI > {reply}\n")


if __name__ == "__main__":
    sys.exit(main())
