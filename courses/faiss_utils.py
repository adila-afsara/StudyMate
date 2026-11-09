
import faiss
import numpy as np
import json
from pathlib import Path


def create_faiss_index(embeddings):
    # Convert embeddings to float32
    embeddings = np.asarray(embeddings, dtype="float32")

    # Find the dimension of each embedding
    dimension = embeddings.shape[1]

    # Create FAISS index
    index = faiss.IndexFlatIP(dimension)

    # Add embeddings into FAISS
    index.add(embeddings)

    return index


def search_faiss(index, query_embedding, chunks, top_k=3):
    # Convert question embedding to float32
    query_embedding = np.asarray(
        query_embedding, dtype="float32"
    ).reshape(1, -1)

    # Search for top matching vectors
    k = min(top_k, index.ntotal)
    scores, indices = index.search(query_embedding, k)

    results = []

    for score, idx in zip(scores[0], indices[0]):
        if idx >= 0:
            results.append({
                "chunk": chunks[idx],
                "score": float(score),
                "chunk_number": int(idx) + 1
            })

    return results


def save_faiss_index(index, chunks, folder_path):
    folder = Path(folder_path)
    folder.mkdir(parents=True, exist_ok=True)

    # Save vectors
    faiss.write_index(index, str(folder / "index.faiss"))

    # Save matching text chunks
    with open(folder / "chunks.json", "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)


def load_faiss_index(folder_path):
    folder = Path(folder_path)

    # Load vectors
    index = faiss.read_index(str(folder / "index.faiss"))

    # Load text chunks
    with open(folder / "chunks.json", "r", encoding="utf-8") as f:
        chunks = json.load(f)

    if index.ntotal != len(chunks):
        raise ValueError("Index and chunk counts do not match.")

    return index, chunks

