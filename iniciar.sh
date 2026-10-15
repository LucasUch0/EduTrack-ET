#!/usr/bin/env sh
# EduTrack-GNN - abre a aplicação no navegador (Linux/macOS).
# O iniciar.py cria o ambiente em ~/.edutrack-gnn, instala o que faltar e abre o navegador
# quando o serviço responder. Opções: ./iniciar.sh --reinstalar   ou   ./iniciar.sh --porta 8123
cd "$(dirname "$0")" || exit 1
for py in python3.13 python3.12 python3.14 python3.11 python3.10 python3 python; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
    exec "$py" iniciar.py "$@"
  fi
done
echo "Não encontrei o Python 3.10 ou mais novo. Instale o Python 3.13 e rode de novo."
exit 1
