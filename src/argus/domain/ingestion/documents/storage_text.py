from argus.domain.ingestion.documents.models import ExtractionBatch


def clean_extracted_text(batch: ExtractionBatch) -> ExtractionBatch:
    replacements = 0

    def clean(value: object) -> object:
        nonlocal replacements
        if isinstance(value, str):
            replacements += value.count("\x00")
            return value.replace("\x00", "\ufffd")
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return tuple(clean(item) for item in value)
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    values = clean(batch.model_dump())
    if not replacements:
        return batch
    cleaned = ExtractionBatch.model_validate(values)
    return cleaned.model_copy(
        update={
            "metadata": {
                **cleaned.metadata,
                "text_cleaning": {"nul_replacements": replacements},
            }
        }
    )
