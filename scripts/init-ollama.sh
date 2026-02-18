#!/bin/sh
# !/bin/sh obligatoire — curlimages/curl est Alpine, bash n'existe pas
set -e

echo "=== Initialisation Ollama ==="

# ── Attente qu'Ollama soit prêt ───────────────────────────────────────────────
echo "Attente qu'Ollama soit prêt..."

RETRY=0
MAX_RETRY=40   # FIX : limite à 40 tentatives (~3 min) au lieu d'une boucle infinie

until curl -sf http://ollama:11434/api/tags > /dev/null 2>&1; do
    RETRY=$((RETRY + 1))
    if [ "$RETRY" -ge "$MAX_RETRY" ]; then
        echo "ERREUR : Ollama n'est pas prêt après $MAX_RETRY tentatives. Abandon."
        exit 1
    fi
    echo "  pas encore prêt, tentative $RETRY/$MAX_RETRY, retry dans 5s..."
    sleep 5
done

echo "Ollama prêt."

# ── Fonction pull avec vérification ──────────────────────────────────────────
pull_model() {
    MODEL=$1
    echo ""
    echo ">>> Pull $MODEL ..."

    # FIX : --max-time 1800 (30 min) — gemma3:4b fait ~3GB, 10 min peut ne pas suffire
    # FIX : on capture le code retour curl pour détecter les échecs
    if curl -sf -X POST http://ollama:11434/api/pull \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"$MODEL\"}" \
        --max-time 1800; then
        echo ">>> $MODEL téléchargé avec succès"
    else
        echo "AVERTISSEMENT : Echec du pull de $MODEL (code=$?)"
        echo "  Le backend démarrera mais ce modèle sera indisponible."
        # On ne fait pas exit 1 — un modèle manquant n'est pas bloquant
    fi
}

# ── Téléchargement des modèles ────────────────────────────────────────────────
pull_model "bge-m3:567m"   # Modèle d'embedding — OBLIGATOIRE pour indexer les documents
pull_model "gemma3:4b"     # LLM par défaut — premier modèle proposé dans l'interface

# Pour ajouter d'autres modèles, décommentez :
# pull_model "llama3.1:latest"
# pull_model "deepseek-r1:14b"
# pull_model "gemma3:12b"

# ── Vérification finale ───────────────────────────────────────────────────────
echo ""
echo "=== Modèles disponibles dans Ollama ==="
# FIX : set +e ici car grep peut retourner 1 si aucun résultat — ne pas arrêter le script
set +e
curl -sf http://ollama:11434/api/tags | grep -o '"name":"[^"]*"' || true
set -e

echo ""
echo "=== Init terminée ==="
