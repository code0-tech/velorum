from sentence_transformers import SentenceTransformer

MODEL_NAME = 'all-MiniLM-L6-v2'


def load_vector_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)
