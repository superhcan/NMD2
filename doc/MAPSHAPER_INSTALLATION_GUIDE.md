# 🔧 Mapshaper Installation Guide

**Målgrupp:** Första gången man installerar Mapshaper  
**Tid:** ~10 minuter  
**OS:** Linux (Debian-baserad, Ubuntu, etc.)

---

## 📋 Krav

- Linux-system med internet
- `curl` eller `wget` (för nedladdning)
- Grundläggande terminal-kunskap
- **Lösenord** för `sudo`-kommandon (kan behövas)

---

## 🚀 Installation (Fullständig Guide)

### Steg 1: Installera Node Version Manager (nvm)

**Vad det gör:** nvm låter dig installera och hantera flera Node.js-versioner utan sudo.

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
```

**Output:** Du bör se något som:
```
=> Cloning into '/home/username/.config/nvm'...
=> Appending nvm source string to /home/username/.bashrc
```

**Ladda in nvm i din nuvarande bash-session:**
```bash
source ~/.bashrc
```

**Verifiera installation:**
```bash
command -v nvm
```

Ska skriva ut:
```
nvm
```

---

### Steg 2: Installera Node.js LTS

Node.js är JavaScript-körmiljön som Mapshaper behöver.

```bash
nvm install 18
```

**Output:** Tar ~2-5 minuter. Du ser något som:
```
Downloading and installing node v18.20.8...
Downloading https://nodejs.org/dist/v18.20.8/node-v18.20.8-linux-x64.tar.xz...
Computing checksum...
...
Now using node v18.20.8 (npm v10.8.2)
```

**Verifiera installation:**
```bash
node --version
npm --version
```

Ska skriva ut:
```
v18.20.8
10.8.2
```

---

### Steg 3: Installera Mapshaper Globalt

```bash
npm install -g mapshaper
```

**Output:** Tar ~5-10 sekunder. Du ser något som:
```
added 94 packages in 7s
14 packages are looking for funding
```

**Verifiera installation:**
```bash
mapshaper --version
```

Ska skriva ut:
```
0.6.113
```

---

## ✅ Verifikation - Allt Fungerar?

Kör denna checklist:

```bash
# 1. Kontrollera Node.js
node --version    # Ska visa v18.x.x eller senare

# 2. Kontrollera npm
npm --version     # Ska visa 10.x.x eller senare

# 3. Kontrollera Mapshaper
mapshaper --version    # Ska visa 0.6.113 eller senare

# 4. Testa Mapshaper CLI
echo '{"type":"Feature","geometry":{"type":"Point","coordinates":[0,0]}}' | \
  mapshaper -o format=json <(echo "test.geojson")
```

Om alla 4 kommandona fungerar → **Installation OK!** ✓

---

## 🔄 Nodig i Varje Ny Terminal-Session?

**Nej** efter första installationen, MEN du behöver **ladda** nvm om du startar en helt ny terminal:

```bash
export NVM_DIR="$HOME/.config/nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
```

Sedan fungerar `mapshaper` direkt.

**ELLER:** Lägg detta i din `~/.bashrc` för att det automatiskt laddas:

```bash
# Lägg denna rad i slutet av ~/.bashrc
[ -s "$HOME/.config/nvm/nvm.sh" ] && \. "$HOME/.config/nvm/nvm.sh"
```

Efter detta: `source ~/.bashrc` och det är färdigt för alltid.

---

## 📍 Installationskatalog

Allt installeras här (du behöver inte veta detta, men för referens):

```
~/.config/nvm/                    ← nvm själv
~/.config/nvm/versions/v18.20.8/  ← Node.js
~/.npm-global/bin/mapshaper       ← Mapshaper executable
```

---

## 🐛 Felsökning

### Problem 1: "command not found: nvm"

**Orsak:** nvm är inte laddat i din session.

**Lösning:**
```bash
# Alt 1: Ladda nvm
source ~/.bashrc

# Alt 2: Starta ny terminal-session
exit
# [Starta ny terminal]

# Alt 3: Checka ~/.bashrc är uppdaterad
grep "nvm.sh" ~/.bashrc
# Ska visa: [ -s "$HOME/.config/nvm/nvm.sh" ] && \. "$HOME/.config/nvm/nvm.sh"
```

---

### Problem 2: "command not found: node"

**Orsak:** nvm är installerad men Node.js inte än.

**Lösning:**
```bash
source ~/.bashrc
nvm install 18
nvm use 18
node --version   # Ska fungera nu
```

---

### Problem 3: "command not found: mapshaper"

**Orsak:** Node.js är installerad men Mapshaper inte, eller nvm är inte laddat.

**Lösning:**
```bash
# Först: Ladda nvm
source ~/.bashrc

# Sedan: Installera Mapshaper
npm install -g mapshaper

# Verifiera
mapshaper --version
```

---

### Problem 4: "npm ERR! code EACCES" (Permission Denied)

**Orsak:** npm försöker skriva till systemkatalog utan tillåtelse.

**Lösning 1 (REKOMMENDERAD):** Ändra npm's cache-katalog
```bash
mkdir ~/.npm-global
npm config set prefix '~/.npm-global'
export PATH=~/.npm-global/bin:$PATH
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc

# Försök igen
npm install -g mapshaper
```

**Lösning 2 (INTE REKOMMENDERAT):** Använd sudo (säkerhetsproblem)
```bash
sudo npm install -g mapshaper
```

---

### Problem 5: Gamla version av Mapshaper

**Symptom:** `mapshaper --version` visar något under 0.6.100

**Lösning:** Uppdatera
```bash
npm install -g mapshaper@latest
```

---

## 🔄 Uppdatera Framöver

```bash
# Uppdatera Node.js
nvm install 18   # eller latest version
nvm use 18

# Uppdatera Mapshaper
npm update -g mapshaper

# Eller helt ny version
npm install -g mapshaper@latest
```

---

## 📦 Alternativ 1: Installera Utan nvm (Systempaket)

**Val:** Enklare, men mindre flexibelt.

### Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install nodejs npm
sudo npm install -g mapshaper
```

**Nackdel:** Kan ge äldre versioner av Node.js beroende på Linux-version.

---

## 📦 Alternativ 2: Docker (Om Du Redan Använder Docker)

```bash
docker run --rm -v $(pwd):/data mbloch/mapshaper \
  mapshaper /data/input.geojson -simplify percentage=50 -o /data/output.geojson
```

**Fördel:** Isolerad miljö, inga installationsproblem.  
**Nackdel:** Långsammare än lokal installation.

---

## 🎯 Nästa Steg

Efter installation, kör:

```bash
# Gå till projekt-katalogen
cd /home/hcn/projects/NMD2

# Kör förenkling-scriptet
export NVM_DIR="$HOME/.config/nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

python3 simplify_mapshaper.py
```

---

## 📞 Support

**Mapshaper FAQ:** https://github.com/mbloch/mapshaper/wiki  
**GitHub Issues:** https://github.com/mbloch/mapshaper/issues  
**nvm Guide:** https://github.com/nvm-sh/nvm

---

**Version:** 1.0  
**Senast uppdaterad:** 13 mars 2026  
**Testad på:** Ubuntu 22.04 LTS, Debian 11
