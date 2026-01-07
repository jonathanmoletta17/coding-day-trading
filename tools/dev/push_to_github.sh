#!/bin/bash
# Script para conectar repositório local ao GitHub
# Execute este script DEPOIS de criar o repositório no GitHub

echo "🔗 Conectando repositório local ao GitHub..."

# Adicionar remote origin
git remote add origin https://github.com/jonathanmoletta17/coding-day-trading.git

echo "✅ Remote adicionado!"
echo ""
echo "📤 Fazendo push do código..."

# Push do código
git push -u origin main

echo ""
echo "🎉 Pronto! Verifique em: https://github.com/jonathanmoletta17/coding-day-trading"
