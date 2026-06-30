#!/bin/bash
# Installe les dépendances night_pkg une seule fois
# Lance ce script UNE SEULE FOIS depuis l'intérieur du container

set -e
echo "📦 Installation des dépendances night_pkg..."

pip install flask flask-cors numpy opencv-python --break-system-packages

echo "✅ Done. Flask est maintenant installé dans ce container."
echo "   Si le container est recréé, relance ce script une fois."
