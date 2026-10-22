"""FirstHour contact-warning generator (Phase 5, feature 1).

After an account is hijacked, the attacker messages the victim's contacts
asking for money or sending links. This builds a ready-to-send message the
victim can paste to warn their contacts quickly. Nothing is stored.
"""

from typing import Optional

PLATFORMS = ("whatsapp", "social", "email")

PLATFORM_NAMES = {
    "en": {"whatsapp": "WhatsApp", "social": "social media", "email": "email"},
    "sw": {"whatsapp": "WhatsApp", "social": "mitandao ya kijamii", "email": "barua pepe"},
}

TEMPLATES = {
    "en": (
        "URGENT WARNING: My {platform} account was hacked.\n\n"
        "Please ignore any message from me that asks for money, codes or passwords, "
        "or that has a link. Do NOT click any link and do NOT send any code.\n\n"
        "If you already sent money or clicked a link, contact your bank or mobile money "
        "provider immediately and let me know.\n\n"
        "I am recovering my account. Please forward this message to anyone who may "
        "have been contacted. Thank you.{signature}"
    ),
    "sw": (
        "TAHADHARI YA HARAKA: Akaunti yangu ya {platform} imedukuliwa.\n\n"
        "Tafadhali puuza ujumbe wowote kutoka kwangu unaoomba pesa, misimbo au nenosiri, "
        "au wenye kiungo. USIBOFYE kiungo chochote na USITUME msimbo wowote.\n\n"
        "Ikiwa ulishatuma pesa au kubofya kiungo, wasiliana na benki yako au mtoa huduma "
        "wako wa pesa za simu mara moja na uniambie.\n\n"
        "Ninarejesha akaunti yangu. Tafadhali sambaza ujumbe huu kwa yeyote ambaye "
        "huenda aliwasiliana naye. Asante.{signature}"
    ),
}


def build_warning(lang: str, platform: str = "whatsapp", name: Optional[str] = None) -> str:
    if lang not in TEMPLATES:
        raise ValueError(f"Unsupported language '{lang}'")
    if platform not in PLATFORMS:
        raise ValueError(f"Unsupported platform '{platform}'")
    clean_name = (name or "").strip()
    signature = f"\n\n- {clean_name}" if clean_name else ""
    return TEMPLATES[lang].format(
        platform=PLATFORM_NAMES[lang][platform],
        signature=signature,
    )
