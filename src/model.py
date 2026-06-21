from model2vec import StaticModel

MODEL_NAME = 'minishlab/potion-base-8M'
EMBEDDING_DIM = 256


def load_vector_model() -> StaticModel:
    return StaticModel.from_pretrained(MODEL_NAME)
