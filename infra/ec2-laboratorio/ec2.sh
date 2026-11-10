#!/usr/bin/env bash
# EC2 del laboratorio: lanzar, encender, apagar, entrar y destruir.
#
#   ./ec2.sh lanzar     crea llave, grupo de seguridad e instancia (una sola vez)
#   ./ec2.sh estado     estado e IP pública actual
#   ./ec2.sh encender   la arranca (se apaga sola a las 20:00, hora de CDMX)
#   ./ec2.sh apagar     la detiene ahora
#   ./ec2.sh ssh        entra por SSH (la IP cambia en cada encendido)
#   ./ec2.sh mi-ip      actualiza la regla de SSH a tu IP pública actual
#   ./ec2.sh destruir   termina la instancia y borra grupo y llave
#
# Requiere EC2_VPC y EC2_SUBRED (no se publican en el repo).
#
# Con PowerUserAccess no se pueden crear roles de IAM: por eso el apagado es
# un cron dentro de la instancia y el encendido es manual.
set -euo pipefail

export AWS_PROFILE="${AWS_PROFILE:-saptiva-poweruser}"
export AWS_REGION="${AWS_REGION:-us-east-1}"

NOMBRE="octavius-energy-lab"
TIPO="${EC2_TIPO:-t3.large}"
DISCO_GB="${EC2_DISCO_GB:-60}"
VPC="${EC2_VPC:?Define EC2_VPC (VPC de dev)}"
SUBRED="${EC2_SUBRED:?Define EC2_SUBRED (subred pública de esa VPC)}"
LLAVE="${EC2_LLAVE:-$HOME/.ssh/energy-lab-ec2}"
AMI_PARAM="/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

instancia() {
  aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=$NOMBRE" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --query 'Reservations[].Instances[0].InstanceId' --output text
}
grupo() {
  aws ec2 describe-security-groups --filters "Name=group-name,Values=$NOMBRE-ssh" "Name=vpc-id,Values=$VPC" \
    --query 'SecurityGroups[0].GroupId' --output text
}
mi_ip() { curl -s --max-time 10 https://checkip.amazonaws.com | tr -d '\n'; }
ip_publica() {
  aws ec2 describe-instances --instance-ids "$1" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text
}

case "${1:-estado}" in
  lanzar)
    [ -n "$(instancia)" ] && [ "$(instancia)" != "None" ] && { echo "Ya existe: $(instancia)"; exit 0; }
    [ -f "$LLAVE" ] || ssh-keygen -q -t ed25519 -N "" -C "$NOMBRE" -f "$LLAVE"
    aws ec2 describe-key-pairs --key-names "$NOMBRE" >/dev/null 2>&1 ||
      aws ec2 import-key-pair --key-name "$NOMBRE" --public-key-material "fileb://$LLAVE.pub" \
        --tag-specifications "ResourceType=key-pair,Tags=[{Key=project,Value=$NOMBRE}]" >/dev/null
    SG="$(grupo)"
    if [ "$SG" = "None" ] || [ -z "$SG" ]; then
      SG="$(aws ec2 create-security-group --group-name "$NOMBRE-ssh" --vpc-id "$VPC" \
        --description "SSH al laboratorio Octavius Energy Lab, solo desde la IP del responsable" \
        --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=$NOMBRE-ssh},{Key=project,Value=$NOMBRE}]" \
        --query GroupId --output text)"
      aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 22 --cidr "$(mi_ip)/32" >/dev/null
    fi
    AMI="$(aws ssm get-parameter --name "$AMI_PARAM" --query Parameter.Value --output text)"
    ID="$(aws ec2 run-instances --image-id "$AMI" --instance-type "$TIPO" --key-name "$NOMBRE" \
      --network-interfaces "DeviceIndex=0,SubnetId=$SUBRED,Groups=$SG,AssociatePublicIpAddress=true" \
      --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$DISCO_GB,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}" \
      --instance-initiated-shutdown-behavior stop \
      --metadata-options "HttpTokens=required,HttpEndpoint=enabled" \
      --user-data "file://$AQUI/user-data.sh" \
      --tag-specifications \
        "ResourceType=instance,Tags=[{Key=Name,Value=$NOMBRE},{Key=project,Value=$NOMBRE},{Key=owner,Value=${EC2_OWNER:-jf}},{Key=purpose,Value=experimento-capa-semantica},{Key=auto-stop,Value=20:00-America/Mexico_City}]" \
        "ResourceType=volume,Tags=[{Key=Name,Value=$NOMBRE},{Key=project,Value=$NOMBRE}]" \
      --query 'Instances[0].InstanceId' --output text)"
    aws ec2 wait instance-running --instance-ids "$ID"
    echo "Instancia $ID en marcha, IP $(ip_publica "$ID")"
    ;;
  estado)
    ID="$(instancia)"
    [ -z "$ID" ] || [ "$ID" = "None" ] && { echo "No hay instancia"; exit 0; }
    aws ec2 describe-instances --instance-ids "$ID" \
      --query 'Reservations[0].Instances[0].[InstanceId,InstanceType,State.Name,PublicIpAddress,LaunchTime]' --output text
    ;;
  encender)
    ID="$(instancia)"; aws ec2 start-instances --instance-ids "$ID" >/dev/null
    aws ec2 wait instance-running --instance-ids "$ID"; echo "Encendida, IP $(ip_publica "$ID")"
    ;;
  apagar)
    ID="$(instancia)"; aws ec2 stop-instances --instance-ids "$ID" >/dev/null; echo "Deteniendo $ID"
    ;;
  ssh)
    ID="$(instancia)"; shift
    exec ssh -i "$LLAVE" -o StrictHostKeyChecking=accept-new "ubuntu@$(ip_publica "$ID")" "$@"
    ;;
  mi-ip)
    SG="$(grupo)"
    for cidr in $(aws ec2 describe-security-groups --group-ids "$SG" \
      --query 'SecurityGroups[0].IpPermissions[?FromPort==`22`].IpRanges[].CidrIp' --output text); do
      aws ec2 revoke-security-group-ingress --group-id "$SG" --protocol tcp --port 22 --cidr "$cidr" >/dev/null
    done
    aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 22 --cidr "$(mi_ip)/32" >/dev/null
    echo "SSH permitido solo desde $(mi_ip)/32"
    ;;
  destruir)
    ID="$(instancia)"
    if [ -n "$ID" ] && [ "$ID" != "None" ]; then
      aws ec2 terminate-instances --instance-ids "$ID" >/dev/null
      aws ec2 wait instance-terminated --instance-ids "$ID"
    fi
    SG="$(grupo)"; [ "$SG" != "None" ] && [ -n "$SG" ] && aws ec2 delete-security-group --group-id "$SG"
    aws ec2 delete-key-pair --key-name "$NOMBRE"
    echo "Instancia, grupo de seguridad y llave eliminados (la llave local $LLAVE se conserva)"
    ;;
  *) sed -n '2,12p' "$0"; exit 1 ;;
esac
