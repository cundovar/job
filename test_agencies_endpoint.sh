#!/bin/bash

# Script de test pour l'endpoint POST /api/agencies/target
# Avant de lancer ce script :
# 1. S'assurer que le serveur backend tourne sur le port 3001
# 2. Vérifier qu'aucun effet de bord (fichiers modifiés) ne s'est produit

set -e

# Même défaut que server/config.js:47 ; surchargeable comme lui par PORT.
BASE_URL="http://localhost:${PORT:-3001}"

echo "=== Test 1 : Pas de domaine (400) ==="
curl -s -X POST "$BASE_URL/api/agencies/target" \
  -H 'Content-Type: application/json' \
  -d '{}' | jq .
echo ""

echo "=== Test 2 : Domaine inconnu (404) ==="
curl -s -X POST "$BASE_URL/api/agencies/target" \
  -H 'Content-Type: application/json' \
  -d '{"domain":"inconnu.xyz"}' | jq .
echo ""

echo "=== Test 3 : Agence déjà ciblée, dry=true (pas d'écriture) ==="
curl -s -X POST "$BASE_URL/api/agencies/target" \
  -H 'Content-Type: application/json' \
  -d '{"domain":"agence-limite.fr","dry":true}' | jq .
echo ""

echo "=== Vérification : git diff --stat (doit être vide) ==="
cd "$(dirname "$0")"
git diff --stat
echo ""

echo "=== Tests terminés ==="
