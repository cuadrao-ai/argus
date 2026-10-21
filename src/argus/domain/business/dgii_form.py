from argus.domain.business.contracts.dgii import PurchaseDeclaration, SalesDeclaration
from argus.domain.business.dgii_columns import COLUMNS


def input_fields(form: str) -> list[dict]:
    model = PurchaseDeclaration if form == "606" else SalesDeclaration
    properties = model.model_json_schema()["properties"]
    result = []
    for name, label in COLUMNS[form]:
        if (
            name in {"occurred_on", "itbis_advance"}
            or form == "606"
            and name == "billed_amount"
        ):
            continue
        schema = properties.get(name, {})
        nonnull = next(
            (item for item in schema.get("anyOf", ()) if item.get("type") != "null"),
            schema,
        )
        result.append(
            {
                "name": name,
                "label": label,
                "kind": "select"
                if "enum" in nonnull
                else "date"
                if nonnull.get("format") == "date"
                else "text"
                if name in {"rnc", "ncf", "modified_ncf"}
                else "money",
                "options": nonnull.get("enum", ["1", "2"] if name == "id_type" else []),
            }
        )
    return result
