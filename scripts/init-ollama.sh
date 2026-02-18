#!/bin/sh
# FIX : #!/bin/sh — curlimages/curl est Alpine, /bin/bash n'existe pas
set -e

echo "=== Initialisation Ollama ==="

echo "Attente qu'Ollama soit prêt..."
until curl -sf http://ollama:11434/api/tags > /dev/null 2>&1; do
    echo "  pas encore prêt, retry dans 3s..."
    sleep 3
done
echo "Ollama prêt."

echo "Pull bge-m3:567m (embedding)..."
curl -sf -X POST http://ollama:11434/api/pull \
    -H "Content-Type: application/json" \
    -d '{"name": "bge-m3:567m"}' \
    --max-time 600 -o /dev/null
echo "bge-m3:567m OK"

echo "Pull gemma3:4b (LLM par défaut)..."
curl -sf -X POST http://ollama:11434/api/pull \
    -H "Content-Type: application/json" \
    -d '{"name": "gemma3:4b"}' \
    --max-time 600 -o /dev/null
echo "gemma3:4b OK"

# Pour ajouter d'autres modèles, décommentez :
# curl -sf -X POST http://ollama:11434/api/pull -H "Content-Type: application/json" \
#     -d '{"name": "llama3.1:latest"}' --max-time 600 -o /dev/null

# FIX : pas de python3 dans curlimages/curl — grep suffit
echo "=== Modèles disponibles ==="
curl -sf http://ollama:11434/api/tags | grep -o '"name":"[^"]*"' || true
echo "=== Init terminée ==="
