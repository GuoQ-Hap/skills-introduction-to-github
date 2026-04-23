from LDA.service.dbService import db_service
from LDA.service.schemaService import schema_service
from LDA.service.nlpService import nlp_service


def get_db_service():
    return db_service


def get_schema_service():
    return schema_service


def get_nlp_service():
    return nlp_service
