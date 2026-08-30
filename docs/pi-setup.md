# Filserver för veckomenyer på `nils-rpi`

Sätter upp en statisk filserver som serverar `/srv/veckomeny/` **enbart över
tailnetet**. Ingen databas, ingen applikationskod — en Caddy-container som
läser en katalog read-only.

Instruktionen är skriven för att kunna köras av en agent (Iris) utan tolkning.
**Varje steg är idempotent** — körs det två gånger händer inget andra gången.
Kör stegen i ordning och stanna vid första kontroll som inte ger förväntat svar.

---

## Till agenten

Du ska köra stegen nedan på `nils-rpi` via shell. Regler:

1. Kör ett steg i taget och jämför utdata med "Förväntat" innan du går vidare.
2. Ändra inget som redan är korrekt konfigurerat — alla kommandon tål omkörning.
3. Rör inte andra containrar, portar eller `tailscale serve`-regler än de som
   nämns här. Pi:n kör annan produktion.
4. Om ett steg misslyckas: stanna, rapportera exakt kommando och felutdata.
   Gissa inte fram en variant.
5. Skapa inga brandväggsregler och exponera ingenting mot internet.

Variabler som används nedan:

```
KATALOG=/srv/veckomeny        # innehållet som ska serveras
STACK=$HOME/veckomeny         # compose-fil + Caddyfile
PORT=8088                     # lyssnar ENBART på 127.0.0.1
```

---

## Förutsättningar

| Krav | Kontrollkommando | Förväntat |
|---|---|---|
| Docker + compose-plugin | `docker compose version` | versionsrad |
| Tailscale uppe | `tailscale status \| head -1` | rad som innehåller `nils-rpi` |
| MagicDNS-namn | `tailscale status --json \| grep -m1 DNSName` | `nils-rpi.<tailnet>.ts.net.` |
| Porten är ledig | `ss -ltn '( sport = :8088 )'` | ingen träff utöver rubrikraden |

Om porten är upptagen: välj en annan ledig port och använd den konsekvent i
steg 3 och 4. Rapportera vilken du valde.

---

## Steg 1 — Innehållskatalog

```bash
sudo mkdir -p /srv/veckomeny/plans
sudo chown -R "$USER":"$USER" /srv/veckomeny
chmod 755 /srv/veckomeny /srv/veckomeny/plans
```

Katalogen måste ägas av inloggningsanvändaren — det är den kontot som Macen
rsync:ar in filer som.

**Kontroll:** `ls -ld /srv/veckomeny` → ägare är din användare, läge `drwxr-xr-x`.

---

## Steg 2 — Platshållarsida

Så att servern svarar 200 redan innan första veckomenyn publicerats.

```bash
[ -f /srv/veckomeny/index.html ] || cat > /srv/veckomeny/index.html <<'HTML'
<!doctype html><html lang="sv"><head><meta charset="utf-8">
<title>Veckomenyer</title></head>
<body style="font-family:ui-monospace,monospace;padding:40px;color:#3c4450">
<h1 style="font-weight:500">Veckomenyer</h1>
<p>Ingen veckomeny publicerad än.</p></body></html>
HTML
```

Villkoret `[ -f ... ]` gör steget säkert att köra om: en riktig, publicerad
`index.html` skrivs aldrig över.

**Kontroll:** `test -s /srv/veckomeny/index.html && echo OK` → `OK`.

---

## Steg 3 — Caddy-container

```bash
mkdir -p "$HOME/veckomeny"

cat > "$HOME/veckomeny/Caddyfile" <<'CADDY'
:8088 {
	root * /srv/veckomeny
	file_server
	encode gzip
	# Sidorna publiceras om på samma filnamn när veckans meny justeras.
	# Utan no-store visar telefonen gårdagens version.
	header Cache-Control "no-store"
}
CADDY

cat > "$HOME/veckomeny/docker-compose.yml" <<'YML'
services:
  veckomeny-web:
    image: caddy:2-alpine
    container_name: veckomeny-web
    restart: unless-stopped
    ports:
      # Endast loopback. Tailscale serve står för exponeringen mot tailnetet.
      - "127.0.0.1:8088:8088"
    volumes:
      - /srv/veckomeny:/srv/veckomeny:ro
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
YML

cd "$HOME/veckomeny" && docker compose up -d
```

Att skriva om `Caddyfile`/`docker-compose.yml` med samma innehåll och köra
`docker compose up -d` är idempotent — containern startas bara om ifall något
faktiskt ändrats.

**Kontroll:**

```bash
docker compose -f "$HOME/veckomeny/docker-compose.yml" ps
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8088/
```

Förväntat: status `running`, och HTTP-kod `200`.

---

## Steg 4 — Exponera på tailnetet

`tailscale serve` lyssnar bara på tailnet-gränssnittet och sköter certifikat
automatiskt. Ingen port öppnas mot LAN eller internet.

```bash
# Visa vad som redan är konfigurerat — rör inte befintliga regler.
sudo tailscale serve status

# Lägg till vår regel först om den inte redan finns:
sudo tailscale serve status | grep -q '127.0.0.1:8088' \
  || sudo tailscale serve --bg --https=443 http://127.0.0.1:8088
```

**På nils-rpi gäller redan detta:** port 443 upptas av OpenClaw-gatewayen, så
veckomeny-servern kör på **8443** — `sudo tailscale serve --bg --https=8443
http://127.0.0.1:8088`. Adressen är `https://nils-rpi:8443/` (kort MagicDNS-namn)
eller `https://nils-rpi.<tailnet>.ts.net:8443/`. Sätts servern upp på en annan
maskin: kontrollera `serve status` först och rapportera vilken port som valdes.

**Kontroll:** `sudo tailscale serve status` visar en rad som mappar
`https://nils-rpi...` → `http://127.0.0.1:8088`.

> Kräver att HTTPS-certifikat är påslaget för tailnetet (admin-konsolen →
> DNS → HTTPS Certificates). Är det avslaget misslyckas kommandot med ett
> certifikatfel — slå på det och kör om.

---

## Steg 5 — Verifiera från en annan enhet

Från Macen eller telefonen, ansluten till tailnetet:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://nils-rpi:8443/
```

Förväntat: `200`. Öppna sedan `https://nils-rpi:8443/` i webbläsaren — du ska se
antingen platshållaren eller listan över publicerade veckor.

---

## Publiceringen (görs från Macen, inte här)

Efter att den här uppsättningen är klar publiceras veckomenyer med:

```bash
cd ~/recipe-db && ./scripts/publish-plan.sh
```

Skriptet renderar `plans/*.json` till HTML och rsync:ar till
`nils-rpi:/srv/veckomeny/`. Filservern behöver inte startas om — Caddy läser
katalogen vid varje anrop.

---

## Felsökning

| Symptom | Trolig orsak | Åtgärd |
|---|---|---|
| `curl http://127.0.0.1:8088/` ger 000 | containern nere | `docker compose -f ~/veckomeny/docker-compose.yml up -d` |
| 404 på allt | fel volym-sökväg | kontrollera att `/srv/veckomeny/index.html` finns och att volymraden i compose-filen pekar rätt |
| 403 | rättigheter | `chmod 755 /srv/veckomeny && chmod 644 /srv/veckomeny/*.html` |
| Gammal version visas | cache | bekräfta `header Cache-Control "no-store"` i Caddyfile, kör `docker compose up -d` |
| rsync från Macen nekas | ägarskap | `sudo chown -R "$USER":"$USER" /srv/veckomeny` |
| `tailscale serve` klagar på cert | HTTPS avslaget i tailnetet | slå på HTTPS Certificates i admin-konsolen |

## Rollback

```bash
cd "$HOME/veckomeny" && docker compose down
sudo tailscale serve --https=443 off
# Innehållet ligger kvar i /srv/veckomeny — radera manuellt om det ska bort.
```
