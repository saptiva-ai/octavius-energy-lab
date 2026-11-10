#!/bin/bash
# Arranque de la EC2 del laboratorio (Ubuntu 24.04). Corre una sola vez, en el
# primer arranque. Sin secretos: las llaves se copian después por SSH.
set -euo pipefail

timedatectl set-timezone America/Mexico_City

apt-get update -y
apt-get install -y docker.io docker-compose-v2 git make python3 python3-venv postgresql-client jq
usermod -aG docker ubuntu
systemctl enable --now docker

# uv para el usuario ubuntu (instalador oficial).
sudo -u ubuntu bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'

# Apagado diario a las 20:00 (hora de CDMX). La instancia se lanza con
# InstanceInitiatedShutdownBehavior=stop: el apagado la detiene, no la borra.
cat > /etc/cron.d/apagado-energy-lab <<'CRON'
SHELL=/bin/bash
CRON_TZ=America/Mexico_City
0 20 * * * root /sbin/shutdown -h now "Apagado programado de Octavius Energy Lab"
CRON
chmod 644 /etc/cron.d/apagado-energy-lab

echo "listo" > /var/lib/energy-lab-bootstrap.done
