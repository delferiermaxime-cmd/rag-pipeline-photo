# RAG Local 🔍

Application RAG (**Retrieval-Augmented Generation**) auto-hébergée permettant d'interroger vos documents via un LLM local. Aucune donnée ne quitte votre serveur.

---

## Table des matières

- [Architecture](#architecture)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Mise à jour](#mise-à-jour)
- [Utilisation](#utilisation)
- [Paramètres](#paramètres)
- [Résolution d'erreurs](#résolution-derreurs)

---

## Architecture

```
Browser → Nginx (port 80)
              ↓
    ┌─────────────────┐
    │  Frontend        │  Next.js (port 3000)
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
Question → bge-m3 → Qdrant (similarité cosine) → TOP_K chunks → LLM → Réponse SSE
```

**Stack technique :**
| Composant | Technologie |
|---|---|
| Frontend | Next.js 14, TypeScript |
| Backend | FastAPI, SQLAlchemy async |
| Base vectorielle | Qdrant |
| Base de données | PostgreSQL 16 |
| LLM & Embedding | Ollama (gemma3, llama3.1, bge-m3...) |
| Parser de documents | Docling |
| Reverse proxy | Nginx |

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
cd rag-pipeline
```

### 2. Configurer les variables d'environnement

```bash
cp .env.example .env
nano .env
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
# Modèle LLM (obligatoire)
docker compose exec ollama ollama pull gemma3:4b

# Modèle d'embedding (obligatoire)
docker compose exec ollama ollama pull bge-m3:567m
```

> ⏱ `gemma3:4b` = ~3 GB, `bge-m3:567m` = ~600 MB

### 5. Vérifier que tout fonctionne

```bash
docker compose ps
```

Tous les containers doivent être en état `Up` :
```
rag-pipeline-backend-1    Up
rag-pipeline-frontend-1   Up
rag-pipeline-nginx-1      Up
rag-pipeline-ollama-1     Up
rag-pipeline-postgres-1   Up
rag-pipeline-qdrant-1     Up
```

### 6. Accéder à l'application

Ouvrir **http://votre-ip-serveur** dans le navigateur, créer un compte et commencer à uploader des documents.

---

## Configuration

### Variables d'environnement (`.env`)

| Variable | Description | Défaut |
|---|---|---|
| `SECRET_KEY` | Clé JWT — **obligatoire, changer en production** | — |
| `CORS_ORIGINS` | Origines autorisées (séparées par virgule) | `http://localhost` |

### Modèles LLM disponibles (`docker-compose.yml`)

Par défaut :
```yaml
OLLAMA_AVAILABLE_MODELS: gemma3:4b,llama3.1:latest,deepseek-r1:14b,gemma3:12b,gemma3:27b
```

Pour ajouter un modèle :
```bash
# 1. Télécharger le modèle
docker compose exec ollama ollama pull llama3.2:latest

# 2. L'ajouter dans docker-compose.yml
OLLAMA_AVAILABLE_MODELS: gemma3:4b,llama3.1:latest,llama3.2:latest

# 3. Redémarrer le backend
docker compose restart backend
```

Parcourir tous les modèles disponibles : **https://ollama.com/library**

### Formats de documents supportés

| Format | Extension | Parser |
|---|---|---|
| PDF | `.pdf` | Docling + PyPdfium |
| Word | `.docx`, `.dotx`, `.doc` | Docling |
| PowerPoint | `.pptx`, `.ppt` | Docling |
| Excel | `.xlsx`, `.xls` | Docling |
| HTML | `.html`, `.htm` | Docling |
| Texte | `.txt`, `.md`, `.csv` | Fallback natif |
| EPUB | `.epub` | Docling |
| AsciiDoc | `.asciidoc`, `.adoc` | Docling |

---

## Mise à jour

### Mise à jour du code

```bash
cd ~/rag-pipeline

# 1. Récupérer les dernières modifications
git pull

# 2. Rebuild complet
docker compose build --no-cache

# 3. Redémarrer
docker compose up -d
```

> ⚠️ Le rebuild recompile les images Docker mais **ne supprime pas les données** (PostgreSQL, Qdrant, modèles Ollama sont dans des volumes persistants).

### Mise à jour rapide (backend uniquement, sans rebuild)

Pour appliquer un changement backend rapidement :
```bash
git pull

docker compose cp backend/app/services/rag_service.py rag-pipeline-backend-1:/app/app/services/rag_service.py
docker compose cp backend/app/routers/chat.py rag-pipeline-backend-1:/app/app/routers/chat.py
# ... autres fichiers modifiés

docker compose restart backend
```

> ⚠️ Les changements frontend nécessitent toujours un rebuild complet (`docker compose build --no-cache frontend`).

### Vérifier les données après mise à jour

```bash
# Compter les documents en base
docker compose exec postgres psql -U raguser -d ragdb -c "SELECT COUNT(*) FROM documents;"

# Compter les vecteurs Qdrant
curl http://localhost/api/v1/documents/ -H "Authorization: Bearer TOKEN"
```

---

## Utilisation

### Uploader des documents (base vectorielle partagée)

1. Aller dans **Upload**
2. Glisser-déposer ou cliquer pour parcourir
3. Attendre le statut **✅ X chunks indexés**
4. Les documents sont accessibles par **tous les utilisateurs**

### Interroger les documents

1. Aller dans **Chat**
2. Taper une question → le LLM répond en streaming
3. Les **sources** sont affichées avec le score de similarité et la page
4. Si la réponse n'est pas dans les documents, le LLM répond depuis ses connaissances générales

### Upload temporaire dans la conversation

Cliquer sur 📎 dans le chat pour joindre un fichier **sans l'indexer** dans la base vectorielle. Le contenu est injecté directement dans le contexte de la conversation.

### Historique

Cliquer sur **Historique** dans le chat pour retrouver les conversations précédentes. Chaque conversation est sauvegardée automatiquement.

---

## Paramètres

Accessible via **Paramètres** dans la sidebar.

| Paramètre | Description | Défaut |
|---|---|---|
| **Prompt système** | Instructions données au LLM avant chaque réponse | Voir app |
| **Température** | 0 = déterministe · 1 = créatif | 0.1 |
| **Tokens max** | Longueur maximale de la réponse | 1024 |
| **TOP_K** | Nombre de chunks récupérés depuis Qdrant | 5 |
| **Score minimum** | Seuil de similarité — chunks en dessous ignorés | 0.3 |
| **Contexte max** | Taille max du contexte envoyé au LLM | 12 000 chars |

Les paramètres sont sauvegardés localement dans le navigateur (localStorage).

---

## Résolution d'erreurs

### Commandes de diagnostic générales

```bash
# État de tous les containers
docker compose ps

# Logs backend (erreurs les plus fréquentes)
docker compose logs backend --tail=50

# Logs frontend
docker compose logs frontend --tail=30

# Tester la connectivité backend
curl http://localhost/api/v1/health 2>/dev/null || echo "Backend inaccessible"
```

---

### ❌ `Docling non installé`

**Cause :** La classe d'import a changé selon la version de Docling.

```bash
# Vérifier les classes disponibles
docker compose exec backend python -c "
import docling.backend.pypdfium2_backend as b
print([x for x in dir(b) if 'Backend' in x])
"

# Vérifier si Docling est bien chargé
docker compose exec backend python -c "
from app.services.docling_service import _DOCLING_OK
print('Docling OK:', _DOCLING_OK)
"
```

**Fix :** Si `_DOCLING_OK` est `False`, vérifier le log d'erreur et corriger l'import dans `docling_service.py`. Le bon nom de classe est `PyPdfiumDocumentBackend` (sans le `2`).

---

### ❌ `File format not allowed`

**Cause :** Docling ne supporte pas le format `.txt` en natif — il doit être traité via le fallback.

**Fix :** S'assurer que `.txt` et `.md` ne sont **pas** dans `EXT_TO_FORMAT` du bloc `if _DOCLING_OK`.

---

### ❌ Le LLM ne répond pas / `Load failed`

```bash
# 1. Vérifier qu'Ollama tourne
docker compose exec ollama ollama list

# 2. Tester Ollama directement
curl http://localhost:11434/api/tags 2>/dev/null | python3 -m json.tool

# 3. Tester le chat via l'API
TOKEN=$(curl -s -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"TON_USER","password":"TON_MOT_DE_PASSE"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"bonjour","model":"gemma3:4b"}' \
  --no-buffer -s | head -10
```

Si le curl retourne des tokens `data: {"type": "token"...}` → le problème est dans le frontend (rebuild nécessaire).

Si erreur `Modèle non disponible` → le modèle n'est pas téléchargé :
```bash
docker compose exec ollama ollama pull gemma3:4b
```

---

### ❌ `SSE` / réponse vide sans erreur

**Cause :** Nginx bufférise le stream SSE.

**Fix :** Vérifier `nginx.conf` — la route `/api/v1/chat/stream` doit avoir :
```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 300s;
```

---

### ❌ Inscription / connexion échoue

```bash
# Tester l'inscription
curl -X POST http://localhost/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","username":"testuser","password":"motdepasse123"}' -v
```

**Erreur bcrypt** (`password cannot be longer than 72 bytes`) :
```bash
# Vérifier la version de bcrypt
docker compose exec backend pip show bcrypt | grep Version
# Doit être 4.0.1
```

Si version incorrecte → vérifier `backend/requirements.txt` : `bcrypt==4.0.1`

---

### ❌ Page Documents affiche 0 document

**Cause :** Les documents ont été uploadés avec un autre compte utilisateur.

```bash
# Vérifier qui a uploadé quoi
docker compose exec postgres psql -U raguser -d ragdb -c "
SELECT d.original_name, d.status, u.username
FROM documents d
JOIN users u ON d.user_id = u.id;"
```

**Fix :** S'assurer que le filtre `user_id` est retiré dans `documents.py` (base partagée) ou se connecter avec le bon compte.

---

### ❌ Container crash au démarrage

```bash
# Voir les logs du container qui crash
docker compose logs backend --tail=100
docker compose logs frontend --tail=50

# Rebuild propre
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

### ❌ Erreur de base de données

```bash
# Vérifier que PostgreSQL tourne
docker compose exec postgres psql -U raguser -d ragdb -c "SELECT version();"

# Lister les tables
docker compose exec postgres psql -U raguser -d ragdb -c "\dt"

# Tables attendues : users, documents, conversations, chat_messages
```

Si les tables manquent, le backend les recrée automatiquement au démarrage (`init_db()`).

---

### ❌ Qdrant inaccessible

```bash
# Tester Qdrant directement
curl http://localhost:6333/collections

# Lister les collections
curl http://localhost:6333/collections/documents/info
```

---

### 🔄 Réinitialisation complète (données effacées)

> ⚠️ **Destructif** — supprime tous les utilisateurs, documents et vecteurs.

```bash
docker compose down -v   # -v supprime les volumes
docker compose build --no-cache
docker compose up -d
```

---

### 📋 Checklist après un problème

1. `docker compose ps` → tous les containers sont `Up` ?
2. `docker compose logs backend --tail=30` → erreur visible ?
3. `docker compose exec ollama ollama list` → modèles présents ?
4. `docker compose exec backend python -c "from app.services.docling_service import _DOCLING_OK; print(_DOCLING_OK)"` → Docling OK ?
5. Test API direct avec curl → le backend répond ?
6. Si tout est OK côté API → rebuild frontend : `docker compose build --no-cache frontend && docker compose up -d frontend`
