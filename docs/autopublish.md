# Automatisk publicering från Macen (valfritt)

Cowork-sandboxen ligger inte på tailnetet — den skriver `plans/<slug>.json`
och renderar HTML, men kan inte nå Pi:n. Utan den här vakten kör du
`./scripts/publish-plan.sh` själv efter varje ändring.

Med den blir steget osynligt: en launchd-agent på Macen ser att `plans/`
ändrats och publicerar.

## Varför det inte snurrar

`build_plan_page.py` skriver bara filer vars innehåll faktiskt ändrats, och
`index.html` tidsstämplas med nyaste planens `created_at` i stället för
klockan. En omkörning rör därför inga mtimes, och vakten triggar inte sig
själv. Ändrar du det beteendet — inför en "genererad HH:MM"-rad till exempel —
får du en loop.

## Installera

```bash
cd ~/recipe-db
sed "s|__REPO__|$PWD|g" scripts/veckomeny-autopublish.plist \
  > ~/Library/LaunchAgents/com.nils.veckomeny-autopublish.plist
launchctl unload ~/Library/LaunchAgents/com.nils.veckomeny-autopublish.plist 2>/dev/null
launchctl load  ~/Library/LaunchAgents/com.nils.veckomeny-autopublish.plist
```

Kör om exakt samma block när du flyttat repot eller ändrat mallen.

## Kontrollera

```bash
launchctl list | grep veckomeny          # ska visa labeln
touch plans/.trigger && sleep 20
tail -20 plans/.autopublish.log          # ska visa en publiceringskörning
```

Kör agenten som din användare, så den har din ssh-nyckel och tailscale-session.
Är Macen offline eller Pi:n nere loggas felet och nästa ändring försöker igen —
inget går förlorat, JSON-filerna ligger kvar i `plans/`.

## Avinstallera

```bash
launchctl unload ~/Library/LaunchAgents/com.nils.veckomeny-autopublish.plist
rm ~/Library/LaunchAgents/com.nils.veckomeny-autopublish.plist
```
