#!/usr/bin/env python3
"""
Script para exportar contraseñas seguras a archivo de texto plano.

ADVERTENCIA: Solo usar para deployment inicial. Eliminar archivo después del uso.
"""

import secrets
import string
import hashlib
import base64
import os
from datetime import datetime
from pathlib import Path

def generate_password(length: int = 32) -> str:
    """Generate a cryptographically secure password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_secret_key(length: int = 32) -> str:
    """Generate a cryptographically secure secret key (hex)."""
    return secrets.token_hex(length)

def generate_base64_key(length: int = 32) -> str:
    """Generate a base64 encoded secret key."""
    return base64.urlsafe_b64encode(secrets.token_bytes(length)).decode('utf-8')

def generate_all_secrets():
    """Generate all required secrets for the system."""
    return {
        "MONGODB_PASSWORD": generate_password(24),
        "REDIS_PASSWORD": generate_password(24),
        "JWT_SECRET_KEY": generate_secret_key(32),
        "SECRET_KEY": generate_secret_key(32),
        "MONGO_ROOT_PASSWORD": generate_password(32),
        "GRAFANA_ADMIN_PASSWORD": generate_password(16),
        "ENCRYPTION_KEY": generate_base64_key(32),
        "SAPTIVA_API_KEY": "your-saptiva-api-key-here"  # Usuario debe reemplazar
    }

def export_to_txt(secrets_dict: dict, output_file: str):
    """Export secrets to plain text file."""

    # Crear el archivo con permisos restrictivos
    output_path = Path(output_file)

    # Crear contenido del archivo
    content = f"""# ========================================
# COPILOTOS BRIDGE - PRODUCTION SECRETS
# ========================================
#
# ⚠️  CRITICAL SECURITY NOTICE:
# - This file contains production secrets in PLAIN TEXT
# - DELETE this file after copying secrets to secure storage
# - NEVER commit this file to version control
# - Use only for initial deployment setup
#
# Generated: {datetime.now().isoformat()}
# ========================================

# Database Credentials
MONGODB_PASSWORD={secrets_dict['MONGODB_PASSWORD']}
REDIS_PASSWORD={secrets_dict['REDIS_PASSWORD']}
MONGO_ROOT_PASSWORD={secrets_dict['MONGO_ROOT_PASSWORD']}

# Application Secrets
JWT_SECRET_KEY={secrets_dict['JWT_SECRET_KEY']}
SECRET_KEY={secrets_dict['SECRET_KEY']}
ENCRYPTION_KEY={secrets_dict['ENCRYPTION_KEY']}

# External Services
SAPTIVA_API_KEY={secrets_dict['SAPTIVA_API_KEY']}

# Admin Passwords
GRAFANA_ADMIN_PASSWORD={secrets_dict['GRAFANA_ADMIN_PASSWORD']}

# ========================================
# DEPLOYMENT INSTRUCTIONS:
# ========================================
#
# 1. For Docker Compose with secrets:
#    docker secret create mongodb_password <(echo "{secrets_dict['MONGODB_PASSWORD']}")
#    docker secret create redis_password <(echo "{secrets_dict['REDIS_PASSWORD']}")
#    docker secret create jwt_secret_key <(echo "{secrets_dict['JWT_SECRET_KEY']}")
#    docker secret create secret_key <(echo "{secrets_dict['SECRET_KEY']}")
#
# 2. For environment variables:
#    export MONGODB_PASSWORD="{secrets_dict['MONGODB_PASSWORD']}"
#    export REDIS_PASSWORD="{secrets_dict['REDIS_PASSWORD']}"
#    export JWT_SECRET_KEY="{secrets_dict['JWT_SECRET_KEY']}"
#    export SECRET_KEY="{secrets_dict['SECRET_KEY']}"
#    export SAPTIVA_API_KEY="your-real-api-key"
#
# 3. For Kubernetes:
#    kubectl create secret generic octavios-secrets \\
#      --from-literal=mongodb-password="{secrets_dict['MONGODB_PASSWORD']}" \\
#      --from-literal=redis-password="{secrets_dict['REDIS_PASSWORD']}" \\
#      --from-literal=jwt-secret-key="{secrets_dict['JWT_SECRET_KEY']}" \\
#      --from-literal=secret-key="{secrets_dict['SECRET_KEY']}" \\
#      --from-literal=saptiva-api-key="your-real-api-key"
#
# 4. For .env file (development only):
#    Copy the variables above to your .env file
#
# ========================================
# REMEMBER TO DELETE THIS FILE AFTER USE!
# ========================================
"""

    # Escribir archivo con permisos restrictivos
    output_path.write_text(content)
    os.chmod(output_path, 0o600)  # Solo propietario puede leer/escribir

    return output_path

def main():
    """Main function."""
    print("🔐 Copilotos Bridge - Password Export Tool")
    print("=" * 60)
    print()

    print("⚠️  SECURITY WARNING:")
    print("   This tool creates a plain text file with ALL production secrets!")
    print("   Use ONLY for initial deployment setup.")
    print("   DELETE the file immediately after copying secrets!")
    print()

    # Confirmar que el usuario entiende los riesgos
    response = input("Do you understand the security implications? (type 'YES' to continue): ")
    if response != "YES":
        print("❌ Operation cancelled for security.")
        return

    print()
    print("🔑 Generating secure secrets...")

    # Generar todos los secretos
    secrets_dict = generate_all_secrets()

    # Archivo de salida
    output_file = "production-secrets.txt"

    print(f"📝 Exporting to: {output_file}")

    # Exportar a archivo
    output_path = export_to_txt(secrets_dict, output_file)

    print()
    print("✅ Secrets exported successfully!")
    print(f"   File: {output_path.absolute()}")
    print(f"   Permissions: {oct(output_path.stat().st_mode)[-3:]}")
    print()

    print("📋 Next Steps:")
    print("1. 📋 Copy secrets to your secure deployment system")
    print("2. 🔑 Replace SAPTIVA_API_KEY with your real API key")
    print("3. 🗑️  DELETE this file immediately: rm production-secrets.txt")
    print("4. ✅ Verify file is in .gitignore")
    print()

    print("🚨 CRITICAL REMINDER:")
    print("   This file contains PRODUCTION SECRETS in plain text!")
    print("   Delete immediately after copying to secure storage!")
    print()

    # Mostrar un preview de algunos secretos (enmascarados)
    print("🔍 Generated Secrets Preview:")
    print("-" * 40)
    for key, value in secrets_dict.items():
        if key == "SAPTIVA_API_KEY":
            print(f"   {key}: {value}")
        else:
            print(f"   {key}: {value[:8]}...{value[-4:]}")
    print()

if __name__ == "__main__":
    main()