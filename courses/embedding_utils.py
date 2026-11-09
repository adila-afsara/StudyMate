
from sentence_transformers import SentenceTransformer

# Load the embedding model
model = SentenceTransformer("intfloat/multilingual-e5-base")


def generate_embeddings(chunks):
    # Prepare chunks for the E5 model
    passages = ["passage: " + chunk for chunk in chunks]

    # Convert text into numerical vectors
    embeddings = model.encode(
        passages,
        normalize_embeddings=True,
        convert_to_numpy=True
    )

    return embeddings

#generate_query_embedding(), will be used when a student asks a question
def generate_query_embedding(question):
    query = "query: " + question

    return model.encode(
        [query],
        normalize_embeddings=True,
        convert_to_numpy=True
    )
