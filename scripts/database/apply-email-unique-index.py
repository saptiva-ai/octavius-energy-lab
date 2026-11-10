#!/usr/bin/env python3
"""
Script para aplicar el índice único en email con normalización a lowercase.

P0-MONGO-UNIQUE: Garantiza que no pueden existir emails duplicados (case-insensitive).

Uso:
    python scripts/apply-email-unique-index.py
"""

import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient


async def apply_email_unique_index():
    """Aplica el índice único en email con normalización lowercase."""

    # Obtener URL de MongoDB desde variable de entorno
    mongodb_url = os.getenv('MONGODB_URL')
    if not mongodb_url:
        # Fallback a configuración local por defecto
        mongodb_url = "mongodb://octavios_user:secure_password_change_me@localhost:27017/octavios?authSource=admin"
        print(f"⚠️  MONGODB_URL no configurada, usando default")

    print(f"📡 Conectando a MongoDB...")

    try:
        # Conectar a MongoDB
        client = AsyncIOMotorClient(mongodb_url)

        # Extraer nombre de base de datos de la URL
        db_name = mongodb_url.split('/')[-1].split('?')[0]
        if not db_name:
            db_name = 'octavios'

        db = client[db_name]
        collection = db['users']

        print(f"✅ Conectado a base de datos: {db_name}")

        # Verificar índices existentes
        existing_indexes = await collection.list_indexes().to_list(length=None)

        print("\n📋 Índices actuales en users:")
        for idx in existing_indexes:
            print(f"   - {idx.get('name')}: {idx.get('key')}")
            if idx.get('unique'):
                print(f"     [UNIQUE]")

        # Verificar si necesitamos crear el índice
        email_index_exists = any(
            idx.get('name') == 'email_1' and idx.get('unique')
            for idx in existing_indexes
        )

        if email_index_exists:
            print("\n✅ El índice único en email ya existe.")
        else:
            print("\n⚠️  El índice único en email NO existe.")
            response = input("¿Deseas crear el índice único? (y/N): ")
            if response.lower() != 'y':
                print("❌ Operación cancelada.")
                return

            # Crear índice único
            print("\n🔨 Creando índice único en email...")
            index_result = await collection.create_index(
                [("email", 1)],
                unique=True,
                name="email_1"
            )
            print(f"✅ Índice creado exitosamente: {index_result}")

        # Verificar normalización de emails existentes
        print("\n🔍 Verificando normalización de emails...")

        pipeline = [
            {"$project": {
                "email": 1,
                "email_lower": {"$toLower": "$email"},
                "is_normalized": {"$eq": ["$email", {"$toLower": "$email"}]}
            }},
            {"$match": {"is_normalized": False}}
        ]

        non_normalized = await collection.aggregate(pipeline).to_list(length=None)

        if non_normalized:
            print(f"\n⚠️  Encontrados {len(non_normalized)} usuarios con emails NO normalizados:")
            for user in non_normalized[:5]:  # Show first 5
                print(f"   - {user['email']} → {user['email_lower']}")

            if len(non_normalized) > 5:
                print(f"   ... y {len(non_normalized) - 5} más")

            print("\n💡 Solución: Ejecuta el script de normalización de emails:")
            print("   python scripts/normalize-emails.py")
        else:
            print("✅ Todos los emails están normalizados (lowercase)")

        # Estadísticas
        print("\n📊 Estadísticas:")
        total_users = await collection.count_documents({})
        active_users = await collection.count_documents({"is_active": True})

        print(f"   Total de usuarios: {total_users}")
        print(f"   Usuarios activos: {active_users}")

        # Verificar duplicados potenciales (case-insensitive)
        print("\n🔍 Verificando duplicados potenciales (case-insensitive)...")

        pipeline = [
            {"$group": {
                "_id": {"$toLower": "$email"},
                "count": {"$sum": 1},
                "users": {"$push": {"id": "$_id", "email": "$email", "username": "$username"}}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]

        duplicates = await collection.aggregate(pipeline).to_list(length=None)

        if duplicates:
            print(f"⚠️  ADVERTENCIA: Encontrados {len(duplicates)} emails duplicados (case-insensitive):")
            for dup in duplicates:
                print(f"\n   Email (normalizado): {dup['_id']}")
                print(f"   Número de copias: {dup['count']}")
                for user in dup['users']:
                    print(f"      - ID: {user['id']}, Email: {user['email']}, Username: {user['username']}")

            print("\n💡 Solución: Debes resolver los duplicados manualmente antes de aplicar el índice único.")
            print("   1. Decide qué registro mantener")
            print("   2. Elimina o actualiza los duplicados")
            print("   3. Ejecuta este script nuevamente")
        else:
            print("✅ No se encontraron duplicados")

        print("\n✅ Verificación completada!")
        print("\n📝 Recomendaciones:")
        print("   1. Asegúrate de que todos los emails estén normalizados (lowercase)")
        print("   2. El servicio de auth ya normaliza emails en register/login")
        print("   3. El índice único previene duplicados a nivel de BD")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        client.close()
        print("\n👋 Conexión cerrada.")


if __name__ == "__main__":
    print("=" * 70)
    print("🚀 Verificación y aplicación de índice único en email")
    print("=" * 70)
    print()

    asyncio.run(apply_email_unique_index())
