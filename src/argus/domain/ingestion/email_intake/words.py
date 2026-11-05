"""Original receipt-name lists. No third-party word list and no external license.

RFC 2142 names are that standard's role mailbox names, not a copied library.
IRIS_DOMINICAN_SLANG_PLACEHOLDER is empty until Iris supplies the slang list.
Nothing in that placeholder is blocked.
"""

from __future__ import annotations

# IRIS_DOMINICAN_SLANG_PLACEHOLDER: pending Iris. Do not copy an outside list into it.
IRIS_DOMINICAN_SLANG_PLACEHOLDER: tuple[str, ...] = ()

# Blocked only when the whole alias is one of these names.
SYSTEM_WORDS = frozenset(
    {
        "hola",
        "admin",
        "info",
        "legal",
        "pagos",
        "soporte",
        "support",
        "ayuda",
        "ajuda",
        "help",
        "contacto",
        "contato",
        "facturacion",
        "billing",
        "seguridad",
        "security",
        "suporte",
        "pagamento",
        "seguranca",
        "aide",
        "facture",
        "securite",
        "paiement",
        "dgii",
        "postmaster",
        "abuse",
        "noreply",
        "recibos",
        "banco",
        "cuadrado",
        "marketing",
        "sales",
        "noc",
        "hostmaster",
        "usenet",
        "news",
        "webmaster",
        "www",
        "uucp",
        "ftp",
    }
)

# Blocked anywhere in the alias, including look-alikes of the product name.
ANYWHERE_WORDS = frozenset(
    {
        "cuadrao",
        "cuadrado",
        "kuadrao",
        "cuadrau",
        "cuadra-o",
        "shit",
        "fuck",
        "bitch",
        "asshole",
        "motherfucker",
        "pendejo",
        "maricon",
        "hijueputa",
        "mamaguevo",
        "cabron",
    }
) | frozenset(IRIS_DOMINICAN_SLANG_PLACEHOLDER)

ALLOW_SURNAMES = frozenset(
    {
        "nunez",
        "rodriguez",
        "perez",
        "garcia",
        "martinez",
        "santana",
        "pena",
        "cruz",
        "reyes",
        "jimenez",
        "diaz",
        "vargas",
        "romero",
        "almonte",
        "tejeda",
        "pimentel",
        "sosa",
        "luna",
        "ortega",
        "guerrero",
        "hernandez",
        "gonzalez",
        "mejia",
        "feliz",
        "polanco",
        "valdez",
        "castillo",
        "ramos",
        "fernandez",
        "suarez",
        "delacruz",
    }
)

ALLOW_TOWNS = frozenset(
    {
        "santodomingo",
        "santiago",
        "lavega",
        "puertoplata",
        "sanpedrodemacoris",
        "laromana",
        "sancristobal",
        "higuey",
        "moca",
        "bani",
        "azua",
        "barahona",
        "mao",
        "bonao",
        "cotui",
        "nagua",
        "hatomayor",
        "montecristi",
        "dajabon",
        "samana",
        "jarabacoa",
        "constanza",
        "bocachica",
    }
)

ALLOW_BUSINESS_WORDS = frozenset(
    {
        "ferreteria",
        "colmado",
        "supermercado",
        "farmacia",
        "pinturas",
        "nacional",
        "popular",
        "carol",
        "esquina",
        "central",
        "papeleria",
        "taller",
        "panaderia",
        "boutique",
        "ferreterianunez",
        "colmadorodriguez",
    }
)

ALLOW_WORDS = ALLOW_SURNAMES | ALLOW_TOWNS | ALLOW_BUSINESS_WORDS

FREE_MAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "hotmail.com",
        "hotmail.es",
        "outlook.com",
        "outlook.es",
        "yahoo.com",
        "yahoo.es",
        "icloud.com",
        "me.com",
        "mac.com",
        "live.com",
        "live.com.do",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "protonmail.ch",
        "gmx.com",
        "gmx.net",
        "mail.com",
        "zoho.com",
        "yandex.com",
        "msn.com",
    }
)


def domain_is_free(host: str) -> bool:
    name = host.strip().lower().lstrip("@")
    if name in FREE_MAIL_DOMAINS:
        return True
    return any(name.endswith("." + item) for item in FREE_MAIL_DOMAINS)
