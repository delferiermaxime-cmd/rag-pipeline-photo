# RAG Local

Application RAG (**Retrieval-Augmented Generation**) auto-hébergée permettant d'interroger vos documents via un LLM local. **Aucune donnée ne quitte votre serveur.**

> 🔓 Stack 100% open source — auto-hébergeable, aucune dépendance cloud.

---

## Table des matières

- [Architecture](#architecture)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Mise à jour](#mise-à-jour)
- [Utilisation](#utilisation)
- [Paramètres avancés](#paramètres-avancés)
- [Résolution d'erreurs](#résolution-derreurs)

---

## Architecture

```
Browser → Nginx (port 80)
              ↓
    ┌─────────────────┐
    │  Frontend        │  Next.js 15 (port 3000)
    └────────┬────────┘
             │ /api/*
    ┌────────▼────────┐
    │  Backend        │  FastAPI (port 8000)
    └──┬──────┬───────┘
       │      │       │
  ┌────▼─┐ ┌──▼───┐  ┌▼───────┐
  │Ollama│ │Qdrant│  │Postgres│
  │LLM + │ │Vect. │  │Users + │
  │Embed.│ │Base  │  │Docs +  │
  └──────┘ └──────┘  │Histor. │
                     └────────┘
```

**Pipeline RAG :**
```
Fichier → Docling → Markdown → Chunks (3000 chars, overlap 450) → bge-m3 → Qdrant
Question → bge-m3 → Qdrant MMR (similarité cosine + diversité) → TOP_K chunks → LLM → Réponse SSE
```

**Stack technique :**

| Composant | Technologie | Licence | Lien |
|---|---|---|---|
| Frontend | Next.js 15, TypeScript | MIT | [docs](https://nextjs.org/docs) |
| Backend | FastAPI, SQLAlchemy async | MIT | [docs](https://fastapi.tiangolo.com) |
| Base vectorielle | Qdrant | Apache 2.0 | [docs](https://qdrant.tech/demo/) |
| Base de données | PostgreSQL 16 | PostgreSQL License | [docs](https://www.postgresql.org/docs/16/index.html) |
| LLM & Embedding | Ollama (gemma3, deepseek-r1, bge-m3) | MIT | [docs](https://docs.ollama.com) |
| Parser de documents | Docling (OCR, tableaux, images) | MIT | [docs](https://www.docling.ai) |
| Reverse proxy | Nginx | BSD 2-Clause | [docs](https://nginx.org) |

> ✅ Usage commercial autorisé pour l'ensemble de la stack. Voir licences individuelles pour les conditions détaillées. Les modèles LLM ont leurs propres licences — vérifier sur [ollama.com/library](https://ollama.com/library).

---

## Prérequis

- **OS** : Linux (Ubuntu 22.04+ recommandé)
- **RAM** : 8 GB minimum, 16 GB recommandé (selon le modèle LLM)
- **Stockage** : 20 GB minimum (modèles LLM inclus)
- **Docker** : 24.0+
- **Docker Compose** : 2.20+
- **Git**

Vérifier les versions :
```bash
docker --version
docker compose version
git --version
```

---

## Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/delferiermaxime-cmd/rag-pipeline-photo.git
cd rag-pipeline-photo
```

### 2. Configurer les variables d'environnement

```bash
cp .env.example .env
nano .env
```


```bash
cd frontend

# Regénérer le package-lock.json
npm install

# Revenir à la racine et rebuilder
cd ..
```



Contenu minimal du `.env` :
```env
SECRET_KEY=changez-moi-avec-une-cle-tres-longue-et-aleatoire
CORS_ORIGINS=http://localhost,http://votre-ip-serveur
```

Générer une clé secrète sécurisée :
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Build et démarrage

```bash
docker compose build --no-cache
docker compose up -d
```

> ⏱ Le premier build prend **10-15 minutes** (téléchargement de Docling et ses modèles).

### 4. Télécharger les modèles Ollama

```bash
# Modèle LLM (obligatoire — choisir selon la RAM disponible)
docker compose exec ollama ollama pull gemma3:4b      # ~3 GB — 8 GB RAM
docker compose exec ollama ollama pull gemma3:12b     # ~8 GB — 16 GB RAM
docker compose exec ollama ollama pull deepseek-r1:14b # ~9 GB — 16 GB RAM

# Modèle d'embedding (obligatoire)
docker compose exec ollama ollama pull bge-m3:567m    # ~600 MB
```

### 5. Vérifier que tout fonctionne

```bash
docker compose ps
```

Tous les containers doivent être en état `Up` :
```
rag-pipeline-photo-backend-1    Up
rag-pipeline-photo-frontend-1   Up
rag-pipeline-photo-nginx-1      Up
rag-pipeline-photo-ollama-1     Up
rag-pipeline-photo-postgres-1   Up
rag-pipeline-photo-qdrant-1     Up
```

### 6. Accéder à l'application

Ouvrir **http://votre-ip-serveur** dans le navigateur, créer un compte et commencer à uploader des documents.

> **Accès distant via SSH tunnel :**
> ```bash
> ssh -p PORT user@ip-serveur -L 8080:localhost:80 -N -f
> ```
> Puis ouvrir `http://localhost:8080`

---

## Configuration

### Variables d'environnement (`.env`)

| Variable | Description | Défaut |
|---|---|---|
| `SECRET_KEY` | Clé JWT — **obligatoire, changer en production** | — |
| `CORS_ORIGINS` | Origines autorisées (séparées par virgules) | `http://localhost` |
| `OLLAMA_AVAILABLE_MODELS` | Modèles disponibles dans l'UI | `["gemma3:4b"]` |

### Modèles LLM disponibles

Par défaut dans `docker-compose.yml` :
```yaml
OLLAMA_AVAILABLE_MODELS: '["gemma3:4b","deepseek-r1:14b","gemma3:12b","gemma3:27b"]'
```

Pour ajouter un modèle :
```bash
# 1. Télécharger le modèle
docker compose exec ollama ollama pull llama3.2:latest

# 2. L'ajouter dans .env (format JSON obligatoire)
OLLAMA_AVAILABLE_MODELS=["gemma3:4b","gemma3:12b","llama3.2:latest"]

# 3. Redémarrer le backend
docker compose restart backend
```

Parcourir tous les modèles disponibles : **https://ollama.com/library**

### Formats de documents supportés

| Format | Extension | Parser |
|---|---|---|
| PDF | `.pdf` | Docling + PyPdfium (OCR inclus) |
| Word | `.docx`, `.dotx`, `.doc` | Docling |
| PowerPoint | `.pptx`, `.ppt` | Docling |
| Excel | `.xlsx`, `.xls` | Docling |
| HTML | `.html`, `.htm` | Docling |
| Texte | `.txt`, `.md`, `.csv` | Fallback natif |
| EPUB | `.epub` | Docling |
| AsciiDoc | `.asciidoc`, `.adoc` | Docling |
| ODT/ODS/ODP | `.odt`, `.ods`, `.odp` | Docling |

> ⚠️ Les fichiers `.dotx` et `.doc` sont automatiquement convertis en `.docx` avant traitement par Docling.

### GPU (optionnel)

Pour utiliser un GPU Nvidia avec Ollama :

```bash
# 1. Installer nvidia-container-toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit

# 2. Configurer Docker
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 3. Vérifier
nvidia-smi
```

---

## Mise à jour

### Mise à jour complète (recommandée)

```bash
cd ~/rag-pipeline-photo
git pull
docker compose build --no-cache
docker compose up -d
```

> ⚠️ Le rebuild recompile les images Docker mais **ne supprime pas les données** (PostgreSQL, Qdrant, modèles Ollama sont dans des volumes persistants).

### Mise à jour rapide du backend (sans rebuild)

```bash
git pull

# Copier les fichiers modifiés directement dans le container
docker compose up -d backend
sleep 15
docker compose cp backend/app/services/rag_service.py rag-pipeline-photo-backend-1:/app/app/services/rag_service.py
docker compose cp backend/app/routers/chat.py rag-pipeline-photo-backend-1:/app/app/routers/chat.py

docker compose restart backend
```

> ⚠️ Toujours faire `docker compose up -d backend` **avant** le `cp` — le container doit exister pour accepter la copie.

> ⚠️ Les changements frontend nécessitent toujours un rebuild complet.

---

## Utilisation

### Uploader des documents

1. Aller dans **Upload**
2. Glisser-déposer ou cliquer pour parcourir
3. Attendre le statut **✅ X chunks indexés**
4. Les documents sont accessibles par **tous les utilisateurs**

> Le système détecte automatiquement les **doublons** (même nom de fichier) et refuse le re-upload.

### Gérer les documents

Aller dans **Documents** pour :
- Rechercher un document par nom
- Supprimer un document individuel (et ses vecteurs associés)
- **Tout supprimer** en un clic

### Interroger les documents

1. Aller dans **Chat**
2. Taper une question → le LLM répond en streaming avec rendu Markdown
3. Les **sources** sont affichées avec le score de similarité, la page, et un bouton **"Voir le chunk complet"**
4. Si la réponse n'est pas dans les documents, le LLM répond depuis ses connaissances générales

### Filtrer par document

Cliquer sur **"Tous les docs"** dans la toolbar du chat pour :
- Sélectionner un ou plusieurs documents spécifiques à interroger
- Activer **"🚫 Sans base vectorielle"** pour interroger uniquement les connaissances générales du LLM

### Upload temporaire dans la conversation

Cliquer sur 📎 pour joindre un fichier **sans l'indexer** dans la base vectorielle. Le contenu est injecté directement dans le contexte de la conversation (formats texte uniquement : `.txt`, `.md`, `.csv`, `.html`).

### Historique

Cliquer sur **Historique** pour retrouver les conversations précédentes. Chaque conversation est sauvegardée automatiquement.

---

## Paramètres avancés

Accessible via **Paramètres** dans la sidebar.

| Paramètre | Description | Défaut |
|---|---|---|
| **Prompt système** | Instructions données au LLM avant chaque réponse | Voir app |
| **Température** | 0 = déterministe · 1 = créatif | 0.1 |
| **Tokens max** | Longueur maximale de la réponse | 1024 |
| **TOP_K** | Nombre de chunks récupérés depuis Qdrant | 8 |
| **Score minimum** | Seuil de similarité — chunks en dessous ignorés | 0.3 |
| **Contexte max** | Taille max du contexte envoyé au LLM | 12 000 chars |

> Les paramètres sont sauvegardés localement dans le navigateur.

### Algorithme MMR (diversité des résultats)

Le système utilise **Maximum Marginal Relevance** pour diversifier les sources retournées. Il récupère 3× plus de candidats que `TOP_K`, puis sélectionne les chunks les plus pertinents **et** les plus diversifiés entre eux — évitant que le même document occupe tous les slots de résultats.

---

## Résolution d'erreurs

### Commandes de diagnostic générales

```bash
# État de tous les containers
docker compose ps

# Logs backend
docker compose logs backend --tail=50

# Logs frontend
docker compose logs frontend --tail=30

# Tester la connectivité backend
curl http://localhost/api/v1/auth/me
```

---

### ❌ Bad Gateway au démarrage

**Cause :** Nginx démarre avant le backend/frontend.

```bash
docker compose restart nginx
```

Si ça persiste, vérifier que tous les containers sont `Up` :
```bash
docker compose ps
docker compose logs backend --tail=20
```

---

### ❌ `docker compose cp` échoue — `no container found`

**Cause :** Le container n'existe pas encore au moment du `cp`.

```bash
# Toujours démarrer d'abord, attendre, puis copier
docker compose up -d backend
sleep 15
docker compose cp fichier.py rag-pipeline-photo-backend-1:/app/app/...
docker compose restart backend
```

---

### ❌ Rebuild frontend échoue — `npm ci` / `package-lock.json` désynchronisé

**Cause :** `package.json` modifié sans regénérer le `package-lock.json`.

```bash
# Regénérer le lock file sur le serveur
cd ~/rag-pipeline-photo/frontend
npm install
git add package-lock.json
git commit -m "update package-lock.json"
git push
cd ..
docker compose build --no-cache frontend && docker compose up -d frontend
```

---

### ❌ Erreur `.dotx` / `.doc` — `Input document is not valid`

**Cause :** Docling valide l'extension du fichier temporaire et rejette `.dotx`/`.doc`.

**Fix :** Déjà corrigé dans `docling_service.py` — les fichiers `.dotx`, `.doc`, `.odt` sont automatiquement renommés en `.docx` avant conversion. Si l'erreur persiste, vérifier que le fichier `docling_service.py` dans le container est bien la dernière version :

```bash
docker compose exec backend grep "DOCX_ALIASES" /app/app/services/docling_service.py
```

---

### ❌ `OLLAMA_AVAILABLE_MODELS` — erreur de parsing

**Cause :** Le format doit être un tableau JSON valide, pas une liste séparée par des virgules.

```env
# ❌ Incorrect
OLLAMA_AVAILABLE_MODELS=gemma3:4b,gemma3:12b

# ✅ Correct
OLLAMA_AVAILABLE_MODELS=["gemma3:4b","gemma3:12b"]
```

---

### ❌ Le LLM ne répond pas / `Load failed`

```bash
# Vérifier qu'Ollama tourne et que les modèles sont présents
docker compose exec ollama ollama list

# Tester le modèle directement
docker compose exec ollama ollama run gemma3:4b "bonjour"
```

Si le modèle n'est pas dans la liste :
```bash
docker compose exec ollama ollama pull gemma3:4b
```

---

### ❌ `Docling non installé` / `_DOCLING_OK = False`

```bash
docker compose exec backend python -c "
from app.services.docling_service import _DOCLING_OK
print('Docling OK:', _DOCLING_OK)
"

# Vérifier le nom de classe disponible
docker compose exec backend python -c "
import docling.backend.pypdfium2_backend as b
print([x for x in dir(b) if 'Backend' in x])
"
```

Le bon nom de classe est `PyPdfiumDocumentBackend`.

---

### ❌ Connexion Safari — `The string did not match the expected pattern`

**Cause :** Safari valide le champ username comme un email.

**Fix :** Déjà corrigé dans `login/page.tsx` via `noValidate` et `autoComplete="username"`. Si l'erreur persiste après rebuild du frontend, vider le cache Safari.

---

### ❌ Disque plein — Qdrant WAL errors

```bash
# Vérifier l'espace disque
df -h

# Nettoyer le cache Docker (attention : supprime les images non utilisées)
docker builder prune -af
docker image prune -af
```

> ⚠️ Les volumes de données (Ollama, Qdrant, PostgreSQL) ne sont pas supprimés par ces commandes.

---

### ❌ `SSE` / réponse vide sans erreur

**Cause :** Nginx bufférise le stream SSE.

Vérifier `nginx.conf` — la route `/api/v1/chat/stream` doit avoir :
```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 300s;
```

---

### ❌ Erreur bcrypt — `password cannot be longer than 72 bytes`

```bash
docker compose exec backend pip show bcrypt | grep Version
# Doit être 4.0.1
```

Si version incorrecte → vérifier `backend/requirements.txt` : `bcrypt==4.0.1`

---

---

### ❌ `nvidia-smi` — Driver/library version mismatch

**Cause :** Le driver Nvidia du kernel et la librairie NVML sont désynchronisés — 
généralement après une mise à jour du driver sans reboot.

**Symptôme :**
```
Failed to initialize NVML: Driver/library version mismatch
NVML library version: 580.126
```

**Fix :**
```bash
sudo reboot
```

Après le reboot :
```bash
nvidia-smi                          # doit afficher la carte correctement
docker compose restart ollama
docker compose exec ollama ollama ps  # vérifier 100% GPU
```

> ⚠️ Le reboot est obligatoire — le mismatch vient d'une mise à jour du kernel 
> sans redémarrage, laissant l'ancien driver en mémoire et la nouvelle librairie sur le disque.


---

### 🔄 Réinitialisation complète (données effacées)

> ⚠️ **Destructif** — supprime tous les utilisateurs, documents et vecteurs.

```bash
docker compose down -v   # -v supprime les volumes
docker compose build --no-cache
docker compose up -d
```

---

### 📋 Checklist de diagnostic

1. `docker compose ps` → tous les containers sont `Up` ?
2. `docker compose logs backend --tail=30` → erreur visible ?
3. `docker compose exec ollama ollama list` → modèles présents ?
4. `docker compose exec backend python -c "from app.services.docling_service import _DOCLING_OK; print(_DOCLING_OK)"` → Docling OK ?
5. Test API direct : `curl http://localhost/api/v1/auth/me` → le backend répond ?
6. Si tout est OK côté API → rebuild frontend : `docker compose build --no-cache frontend && docker compose up -d frontend`
