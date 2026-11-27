#!/usr/bin/env python3
"""Engångsomkategorisering (2026-11): kök = nationalitet, typ = menyrubrik,
taggar = den lilla fasta listan i app.py (RECIPE_TAGS).

Skriver via HTTP-API:t (`commit-edit`) så att varje recept får en ny version
med change_note — allt går att backa i versionshistoriken. Endast kitchen,
type och tags skickas; innehåll och ingredienser rörs inte.

Kräver att servern har ändringen där kategori-only-edits inte flyttar
tillagningsstatusen (apply_recipe_edit: content_changed). Kör annars inte —
då blir alla lagade recept "oprövade".

    python3 scripts/recategorize_2026_11.py            # dry-run, visar diff
    python3 scripts/recategorize_2026_11.py --apply    # skriver

Läser RECIPE_API_URL / RECIPE_API_TOKEN från miljön eller .claude/.env.
"""
import json
import os
import sys
import urllib.error
import urllib.request

SE, IT, FR, MX, ES = '🇸🇪 Svenskt', '🇮🇹 Italienskt', '🇫🇷 Franskt', '🇲🇽 Mexikanskt', '🇪🇸 Spanskt'
CN, KR, JP, TH, US = '🇨🇳 Kinesiskt', '🇰🇷 Koreanskt', '🇯🇵 Japanskt', '🇹🇭 Thailändskt', '🇺🇸 Amerikanskt'
IN, BR, LB, GR, AT = '🇮🇳 Indiskt', '🇧🇷 Brasilianskt', '🇱🇧 Libanesiskt', '🇬🇷 Grekiskt', '🇦🇹 Österrikiskt'

# id: (kitchen, type, [tags])
MAPPING = {
    1:  (IT, 'pasta',       ['långkok', 'matlåda', 'barnvänligt']),          # Ragù alla Bolognese
    3:  (KR, 'huvudrätt',   ['vardag']),                                     # Kyckling bulgogi
    4:  (MX, 'tacos',       ['fredagsmiddag']),                              # Beef taco
    5:  (IN, 'huvudrätt',   ['vardag', 'matlåda', 'vegetariskt']),           # Daal
    6:  (TH, 'huvudrätt',   ['vardag']),                                     # Thai red curry
    9:  (IT, 'pasta',       ['vardag', 'matlåda']),                          # Salsicciapasta
    10: (SE, 'huvudrätt',   ['vardag']),                                     # Renskavsgryta
    12: (ES, 'tapas',       ['fredagsmiddag', 'vegetariskt']),               # Patatas bravas
    13: (MX, 'tacos',       ['fredagsmiddag', 'barnvänligt']),               # Burritos
    14: (AT, 'huvudrätt',   ['fredagsmiddag', 'barnvänligt']),               # Wiener Schnitzel
    15: (FR, 'grundrecept', ['långkok']),                                    # Brun kött-fond
    16: (SE, 'huvudrätt',   ['vardag', 'barnvänligt']),                      # Isterband
    17: (FR, 'huvudrätt',   ['bjudning']),                                   # Poulet rôti
    18: (KR, 'huvudrätt',   ['vardag', 'matlåda']),                          # Korean beef bowl
    19: (CN, 'nudlar',      ['vardag', 'vegetariskt']),                      # Lao Gan Ma udon
    20: (CN, 'nudlar',      ['vardag']),                                     # Chow mein
    21: (SE, 'förrätt',     ['bjudning']),                                   # Råbiff, asiatiska inslag
    22: (MX, 'tacos',       ['fredagsmiddag']),                              # Pollo asado
    23: (MX, 'tillbehör',   ['vegetariskt']),                                # Salsa verde
    24: (MX, 'huvudrätt',   ['matlåda', 'långkok']),                         # Frijoles charros
    25: (SE, 'huvudrätt',   ['vardag', 'barnvänligt']),                      # Pytt i panna
    26: (JP, 'tillbehör',   ['vegetariskt']),                                # Ris i riskokare
    27: (MX, 'tillbehör',   ['vegetariskt']),                                # Queso fresco
    28: (ES, 'frukost',     ['vegetariskt']),                                # Tostada med tomat
    29: (SE, 'soppa',       ['vardag', 'matlåda', 'barnvänligt']),           # Kycklingsoppa
    30: (US, 'frukost',     ['vardag', 'vegetariskt']),                      # Grön smoothie
    31: (FR, 'sallad',      ['vardag']),                                     # Salade niçoise
    32: (IT, 'pasta',       ['fredagsmiddag', 'vegetariskt']),               # Rigatoni burrata
    33: (IT, 'huvudrätt',   ['vardag', 'matlåda', 'barnvänligt']),           # Kycklinggryta
    34: (SE, 'pasta',       ['vardag', 'barnvänligt']),                      # Fläskfilépasta
    35: (IT, 'pasta',       ['vardag']),                                     # Puttanesca
    36: (JP, 'nudlar',      ['långkok']),                                    # Shoyu-ramen
    37: (IT, 'pasta',       ['vardag', 'vegetariskt']),                      # Cacio e pepe
    38: (IT, 'pasta',       ['långkok', 'matlåda']),                         # Florentinsk ragù
    39: (CN, 'huvudrätt',   ['vardag']),                                     # Five spice-kyckling
    40: (FR, 'huvudrätt',   ['bjudning', 'långkok']),                        # Confit de canard
    41: (ES, 'tapas',       ['fredagsmiddag', 'bjudning']),                  # Gambas al ajillo
    42: (SE, 'macka',       ['fredagsmiddag']),                              # Bookmaker toast
    43: (GR, 'huvudrätt',   ['vardag', 'matlåda', 'barnvänligt']),           # Ugnskyckling feta
    44: (IT, 'pasta',       ['vardag', 'matlåda', 'barnvänligt', 'vegetariskt']),  # Linguine pesto
    45: (CN, 'huvudrätt',   ['vardag']),                                     # Mapo tofu
    46: (SE, 'förrätt',     ['bjudning', 'vegetariskt']),                    # Västerbottenostpaj
    47: (FR, 'tillbehör',   ['vegetariskt']),                                # Aïoli
    48: (IT, 'efterrätt',   ['bjudning']),                                   # Pannacotta
    49: (SE, 'huvudrätt',   ['vardag', 'barnvänligt']),                      # Raggmunkar
    50: (BR, 'macka',       ['fredagsmiddag']),                              # Mortadella-macka
    51: (US, 'macka',       ['fredagsmiddag', 'barnvänligt']),               # Fried chicken sandwich
    52: (SE, 'huvudrätt',   ['vardag', 'barnvänligt']),                      # Saltbakad lax
    53: (LB, 'sallad',      ['vardag', 'matlåda', 'vegetariskt']),           # Tabbouleh halloumi
    54: (TH, 'sallad',      ['vardag']),                                     # Larb moo
    55: (CN, 'huvudrätt',   ['långkok']),                                    # Hong shao rou
    56: (US, 'macka',       ['fredagsmiddag']),                              # Philly steak sandwich
    58: (SE, 'huvudrätt',   ['vardag', 'barnvänligt']),                      # Panerad sej
    59: (MX, 'huvudrätt',   ['vardag', 'vegetariskt']),                      # Enchiladas
}

CHANGE_NOTE = 'Ny kategorisering: kök = nationalitet, typ = menyrubrik, färre taggar'


def load_env():
    path = os.path.join(os.path.dirname(__file__), '..', '.claude', '.env')
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    url, tok = os.environ.get('RECIPE_API_URL'), os.environ.get('RECIPE_API_TOKEN')
    if not url or not tok:
        sys.exit('RECIPE_API_URL / RECIPE_API_TOKEN saknas')
    return url.rstrip('/'), tok


def call(base, tok, method, path, body=None):
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main():
    apply = '--apply' in sys.argv
    base, tok = load_env()
    all_ids = {r['id'] for r in call(base, tok, 'GET', '/api/recipe/search?q=')['results']}
    missing = sorted(all_ids - MAPPING.keys())
    if missing:
        print(f'⚠️  Recept utan mappning (rörs inte): {missing}')

    changed = 0
    for rid, (kitchen, typ, tags) in sorted(MAPPING.items()):
        if rid not in all_ids:
            print(f'⚠️  #{rid} finns inte längre — hoppar över')
            continue
        cur = call(base, tok, 'GET', f'/api/recipe/{rid}')
        new = {'kitchen': kitchen, 'type': typ, 'tags': ','.join(tags)}
        old = {k: cur.get(k) or '' for k in new}
        if old == new:
            continue
        changed += 1
        print(f"#{rid:<3} {cur['title'][:50]}")
        for k in new:
            if old[k] != new[k]:
                print(f'      {k:8} {old[k]!r} → {new[k]!r}')
        if apply:
            try:
                call(base, tok, 'POST', f'/api/recipe/{rid}/commit-edit', {
                    **new,
                    'change_note': CHANGE_NOTE,
                    'expected_version_number': cur['current_version_number'],
                })
            except urllib.error.HTTPError as e:
                print(f'      ✗ {e.code}: {e.read().decode()[:200]}')
    print(f"\n{changed} recept {'uppdaterade' if apply else 'skulle uppdateras (dry-run, kör med --apply)'}")


if __name__ == '__main__':
    main()
