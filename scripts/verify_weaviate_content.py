
import weaviate
import os
import json

def verify_weaviate():
    client = weaviate.connect_to_custom(
        http_host="localhost",
        http_port=8080,
        http_secure=False,
        grpc_host="localhost",
        grpc_port=50051,
        grpc_secure=False,
        skip_init_checks=True
    )
    
    collection_name = "Ontology_Term"
    if not client.collections.exists(collection_name):
        print(f"Collection {collection_name} does not exist.")
        return

    collection = client.collections.get(collection_name)
    
    # Check count
    count = len(collection)
    print(f"Total objects in {collection_name}: {count}")
    
    # Check search
    query = "Utilidad Neta"
    print(f"\nSearching for: '{query}'")
    
    # Basic search (bm25 if no vectorizer, or hybrid)
    response = collection.query.bm25(
        query=query,
        limit=3
    )
    
    for o in response.objects:
        print(f"- {o.properties['term_name']} (Source: {o.properties['source']})")
        print(f"  Definition: {o.properties.get('definition')}")
        print(f"  SQL Column: {o.properties.get('sql_column')}")

    client.close()

if __name__ == "__main__":
    verify_weaviate()
