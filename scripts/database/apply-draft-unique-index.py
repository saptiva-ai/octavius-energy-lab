#!/usr/bin/env python3
"""
Script para aplicar el índice único parcial 'unique_draft_per_user' a MongoDB.

P0-BE-UNIQ-EMPTY: Garantiza que solo puede existir una conversación DRAFT vacía por usuario.

Uso:
    python scripts/apply-draft-unique-index.py
"""

import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient


async def apply_unique_index():
    """Aplica el índice único parcial a la colección chat_sessions."""

    # Obtener URL de MongoDB desde variable de entorno
    mongodb_url = os.getenv('MONGODB_URL')
    if not mongodb_url:
        # Fallback a configuración local por defecto
        mongodb_url = "mongodb://octavios_user:secure_password_change_me@localhost:27017/octavios?authSource=admin"
        print(f"⚠️  MONGODB_URL no configurada, usando default: {mongodb_url}")

    print(f"📡 Conectando a MongoDB...")

    try:
        # Conectar a MongoDB
        client = AsyncIOMotorClient(mongodb_url)

        # Extraer nombre de base de datos de la URL
        db_name = mongodb_url.split('/')[-1].split('?')[0]
        if not db_name:
            db_name = 'octavios'

        db = client[db_name]
        collection = db['chat_sessions']

        print(f"✅ Conectado a base de datos: {db_name}")

        # Verificar si el índice ya existe
        existing_indexes = await collection.list_indexes().to_list(length=None)
        index_exists = any(idx.get('name') == 'unique_draft_per_user' for idx in existing_indexes)

        if index_exists:
            print("ℹ️  El índice 'unique_draft_per_user' ya existe.")

            # Mostrar detalles del índice existente
            for idx in existing_indexes:
                if idx.get('name') == 'unique_draft_per_user':
                    print(f"   Keys: {idx.get('key')}")
                    print(f"   Unique: {idx.get('unique')}")
                    print(f"   Partial filter: {idx.get('partialFilterExpression')}")

            response = input("\n¿Deseas recrear el índice? (y/N): ")
            if response.lower() != 'y':
                print("❌ Operación cancelada.")
                return

            # Eliminar índice existente
            print("🗑️  Eliminando índice existente...")
            await collection.drop_index('unique_draft_per_user')
            print("✅ Índice eliminado.")

        # Crear el índice único parcial
        print("\n🔨 Creando índice único parcial 'unique_draft_per_user'...")

        index_result = await collection.create_index(
            [("user_id", 1), ("state", 1)],
            unique=True,
            partialFilterExpression={"state": "draft"},
            name="unique_draft_per_user"
        )

        print(f"✅ Índice creado exitosamente: {index_result}")

        # Verificar el índice creado
        print("\n📋 Índices actuales en chat_sessions:")
        indexes = await collection.list_indexes().to_list(length=None)
        for idx in indexes:
            print(f"   - {idx.get('name')}: {idx.get('key')}")
            if idx.get('unique'):
                print(f"     [UNIQUE]")
            if idx.get('partialFilterExpression'):
                print(f"     [PARTIAL FILTER: {idx.get('partialFilterExpression')}]")

        # Estadísticas
        print("\n📊 Estadísticas de conversaciones:")
        total_sessions = await collection.count_documents({})
        draft_sessions = await collection.count_documents({"state": "draft"})
        empty_drafts = await collection.count_documents({"state": "draft", "message_count": 0})

        print(f"   Total de conversaciones: {total_sessions}")
        print(f"   Conversaciones DRAFT: {draft_sessions}")
        print(f"   DRAFTs vacías (message_count=0): {empty_drafts}")

        # Advertencia si hay DRAFTs vacías duplicadas
        if empty_drafts > 0:
            pipeline = [
                {"$match": {"state": "draft", "message_count": 0}},
                {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
                {"$match": {"count": {"$gt": 1}}}
            ]

            duplicates = await collection.aggregate(pipeline).to_list(length=None)

            if duplicates:
                print("\n⚠️  ADVERTENCIA: Usuarios con múltiples DRAFTs vacías:")
                for dup in duplicates:
                    print(f"   - Usuario {dup['_id']}: {dup['count']} DRAFTs vacías")
                print("\n💡 Solución: Ejecuta el script de limpieza para eliminar duplicados antes de que cause conflictos.")
                print("   python scripts/cleanup-duplicate-drafts.py")

        print("\n✅ Índice aplicado exitosamente!")
        print("\n📝 Comportamiento del índice:")
        print("   - Solo puede existir UNA conversación con state='draft' por usuario")
        print("   - Conversaciones con state='ready' no están afectadas por el índice")
        print("   - Los intentos de insertar una segunda DRAFT fallarán con E11000")

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
    print("🚀 Aplicando índice único parcial: unique_draft_per_user")
    print("=" * 70)
    print()

    asyncio.run(apply_unique_index())
