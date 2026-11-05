"""Real shapes from NPPA Authority minutes. Rows that are not read exactly must be refused."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.catalogue.service import attrs_of, get_medicine
from app.config import get_settings
from app.imports.composition import (
    CompositionError,
    parse_composition,
    release_code,
    release_label,
)
from app.imports.normalize import _company_names, normalize_nppa_retail_row
from app.imports.seed import ensure_sources
from app.matching.equivalence import compare
from app.models import DataSource, Medicine, PriceObservation

ROW = {
    "meeting": "285",
    "meeting_date": "2026-10-29",
    "formulation": "Telmisartan and Chlorthalidone Tablets",
    "composition": "Each uncoated bilayered tablet contains: Telmisartan IP 80 mg Chlorthalidone IP 12.5 mg",
    "unit": "1 Tablet",
    "company": "M/s Maker Pvt. Ltd./ M/s Seller Ltd.",
    "price": "21.40",
    "note": "",
}


def parse_one(composition: str):
    return parse_composition(composition)


def test_ingredients_salts_and_strengths():
    parsed = parse_one(
        "Each Film Coated Tablet Contains: Atorvastatin Calcium IP Eq. to Atorvastatin 10 mg Ezetimibe IP 10 mg"
    )
    assert [(p.name, p.salt_form, p.strength_text) for p in parsed] == [
        ("Atorvastatin", "calcium; strength as atorvastatin", "10 mg"),
        ("Ezetimibe", "none named", "10 mg"),
    ]


@pytest.mark.safety
def test_strength_as_salt_and_as_base_are_not_equivalent():
    as_salt = normalize_nppa_retail_row(
        {
            **ROW,
            "formulation": "Metformin Tablets",
            "composition": "Each tablet contains: Metformin Hydrochloride IP 500 mg",
        }
    )[0]
    as_base = normalize_nppa_retail_row(
        {
            **ROW,
            "formulation": "Metformin Tablets",
            "composition": "Each tablet contains: Metformin Hydrochloride IP eq. to Metformin 500 mg",
        }
    )[0]
    assert as_salt["ingredients"][0]["salt_form"] != as_base["ingredients"][0]["salt_form"]


@pytest.mark.safety
def test_release_names_the_ingredient_it_applies_to():
    first = parse_one(
        "Each tablet contains: Metformin Hydrochloride IP 500 mg (as sustained release form) Glimepiride IP 1 mg"
    )
    second = parse_one(
        "Each tablet contains: Metformin Hydrochloride IP 500 mg Glimepiride IP 1 mg (as sustained release form)"
    )
    assert release_code(first, "X Tablets", "conventional") == "sustained:metformin"
    assert release_code(second, "X Tablets", "conventional") == "sustained:glimepiride"
    assert release_label("sustained:metformin") == "Sustained release (metformin)"


def test_release_from_the_name_needs_a_single_ingredient():
    single = parse_one("Each tablet contains: Clobazam IP 5 mg")
    assert release_code(single, "Clobazam (ER) Tablets", "conventional") == "extended:clobazam"
    pair = parse_one(
        "Each tablet contains: Doxylamine Succinate USP 20 mg Pyridoxine Hydrochloride IP 20 mg"
    )
    with pytest.raises(CompositionError):
        release_code(pair, "Doxylamine and Pyridoxine Extended Release Tablets", "conventional")


def test_words_that_only_look_like_excipients_do_not_drop_a_medicine():
    parsed = parse_one(
        "Each hard gelatin capsule contains: Aspirin IP 75 mg (as gastro-resistant white colored pellets) "
        "Atorvastatin Calcium IP eq. to Atorvastatin 20 mg"
    )
    assert [p.name for p in parsed] == ["Acetylsalicylic acid", "Atorvastatin"]
    assert parsed[0].release == "enteric_coated"


def test_preservatives_are_not_active_ingredients():
    bracketed = parse_one(
        "Composition: Nepafenac IP 0.1% w/v Moxifloxacin Hydrochloride IP Eq. Moxifloxacin 0.5% w/v "
        "Benzalkonium Chloride Solution IP 0.01% w/v (As Preservative)"
    )
    assert [p.name for p in bracketed] == ["Nepafenac", "Moxifloxacin"]
    bare = parse_one("Composition: Latanoprost IP 0.005% w/v Benzalkonium Chloride IP 0.02% w/v")
    assert [p.name for p in bare] == ["Latanoprost"]


@pytest.mark.parametrize(
    ("printed", "name", "salt"),
    [
        ("Bisoprolol FumarateIP 5 mg", "Bisoprolol", "fumarate"),
        ("Polmacoxib IH 2 mg", "Polmacoxib", "none named"),
        ("Dexamethasone Sodium Phosphate IP 4 mg", "Dexamethasone", "sodium phosphate"),
        ("Phenylephrine HCI IP 5 mg", "Phenylephrine", "hydrochloride"),
        ("Clopidogrel Bisulphate IP 75 mg", "Clopidogrel", "bisulfate"),
        ("Potassium Clavulanate Diluted IP 125 mg", "Clavulanic Acid", "potassium, diluted"),
        ("Amoxycillin Trihydrate IP 250 mg", "Amoxicillin", "trihydrate"),
        ("Vitamin D3 IP 2000 IU", "Cholecalciferol", "none named"),
        ("myo-Inositol 500 mg", "Myo-Inositol", "none named"),
        ("Sterile Tazobactam Sodium IP 62.5 mg", "Tazobactam", "sodium"),
    ],
)
def test_printed_names(printed, name, salt):
    parsed = parse_one(f"Each tablet contains: {printed}")[0]
    assert (parsed.name, parsed.salt_form) == (name, salt)


def test_liquid_strengths_carry_their_volume():
    assert (
        parse_one("Each 5 ml contains: Cholecalciferol IP 60000 IU")[0].strength_text
        == "60000 iu/5 ml"
    )
    assert parse_one("Each ml contains: Clobazam IP 2.5 mg")[0].strength_text == "2.5 mg/1 ml"
    assert parse_one("Each gm contains: Diclofenac Sodium IP 10 mg")[0].strength_text == "10 mg/1 g"


@pytest.mark.parametrize(
    "bad",
    [
        "Each Combipack Contains: (A) 1 Bottle of X 5 mg",
        "Part A- Each film coated tablet contains: Darunavir Ethanolate IP Eq. to Darunavir 800 mg Part B- Each film coated tablet contains: Ritonavir 100 mg",
        "Gentamicin Sulphate IP 0.3% w/v",
        "Each tablet contains: nothing with a figure",
        "Each tablet contains: 50,000 Armour units of enzymatic activity 100 mg",
        "Each tablet contains: 5 mg",
        "Each tablet contains: Clobazam IP 5 mg Clobazam IP 10 mg",
        "Each tablet contains: Clobazam IP 5 mg (as film coated tablet)",
        "Each tablet contains: eq. to Clobazam 5 mg",
        "Each tablet contains: Clobazam IP eq. to 5 mg",
        "Each tablet contains: Benzalkonium Chloride IP 1 mg",
    ],
)
def test_unclear_compositions_are_refused(bad):
    with pytest.raises(CompositionError):
        parse_composition(bad)


def test_several_release_types_in_one_note_are_refused():
    with pytest.raises(CompositionError):
        parse_composition("Each tablet contains: Clobazam IP 5 mg (extended and enteric release)")


def test_normalised_row_keeps_provenance_and_company():
    value, errors = normalize_nppa_retail_row(
        {**ROW, "price": "125.07 (Note-1)", "note": "Note text"}
    )
    assert errors == []
    assert value["price"] == "125.07"
    assert value["price_type"] == "notified_retail"
    assert value["marketed_by"] == "Seller Ltd (manufactured by Maker Pvt. Ltd)"
    assert value["display_name"].endswith("(Seller Ltd)")
    assert "Authority meeting 285" in value["source_text"] and "Note text" in value["source_text"]
    assert value["observed_at"] == "2026-10-29"
    assert value["release_type"] == "conventional"


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"price": "21.40 22.10"}, "price"),
        ({"price": "0"}, "price"),
        ({"unit": "1 Combipa ck"}, "unit"),
        ({"company": "Unknown"}, None),
        ({"company": "M/s A / M/s B / M/s C"}, "company"),
        ({"meeting_date": "soon"}, "meeting_date"),
        ({"formulation": ""}, "formulation"),
        (
            {
                "formulation": "Ondansetron Strips",
                "composition": "Each strip contains: Ondansetron IP 4 mg",
            },
            "dosage_form",
        ),
        ({"composition": "unclear"}, "composition"),
    ],
)
def test_row_refused_rather_than_guessed(change, fragment):
    value, errors = normalize_nppa_retail_row({**ROW, **change})
    if fragment is None:
        assert value is not None and value["marketed_by"] == "Unknown"
        return
    assert value is None and any(fragment in error for error in errors)


def test_release_error_reaches_the_row():
    value, errors = normalize_nppa_retail_row(
        {
            **ROW,
            "formulation": "Doxylamine and Pyridoxine Extended Release Tablets",
            "composition": "Each tablet contains: Doxylamine Succinate USP 20 mg Pyridoxine Hydrochloride IP 20 mg",
        }
    )
    assert value is None and any("release_type" in error for error in errors)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("M/s A Ltd./ M/s B Ltd.", ("A Ltd", "B Ltd")),
        ("M/s A Ltd.; and", ("A Ltd", "A Ltd")),
        ("M/s A Pvt. Ltd", ("A Pvt. Ltd", "A Pvt. Ltd")),
    ],
)
def test_company_names(text, expected):
    assert _company_names(text) == expected


@pytest.mark.parametrize(
    ("formulation", "form", "route"),
    [
        ("X Ophthalmic Solution", "eye_drops", "ophthalmic"),
        ("X Injection", "injection", "parenteral"),
        ("X Gel", "gel", "topical"),
        ("X Oral Suspension", "suspension", "oral"),
        ("X Drops", "oral_liquid", "oral"),
        ("X Mouth Dissolving Tablets", "orodispersible_tablet", "oral"),
        ("X Dispersible Tablets", "dispersible_tablet", "oral"),
        ("X Capsules", "capsule", "oral"),
    ],
)
def test_forms(formulation, form, route):
    value, _ = normalize_nppa_retail_row(
        {**ROW, "formulation": formulation, "composition": "Each unit contains: Clobazam IP 5 mg"}
    )
    assert (value["dosage_form"], value["route"]) == (form, route)


def retail(db):
    source = db.scalar(select(DataSource).where(DataSource.code == "nppa_retail"))
    return source, db.scalars(select(Medicine).where(Medicine.source_id == source.id)).all()


def test_real_rows_are_published_with_provenance(db):
    source, medicines = retail(db)
    assert source.is_demo is False
    assert len(medicines) >= 90
    for medicine in medicines[:15]:
        assert medicine.is_demo is False and medicine.marketed_by
        assert (
            medicine.batch_id
            and medicine.source_row
            and "Authority meeting" in medicine.source_text
        )
    prices = db.scalars(
        select(PriceObservation).where(PriceObservation.source_id == source.id)
    ).all()
    assert prices and all(p.price_type == "notified_retail" and not p.is_demo for p in prices)
    path = Path(get_settings().data_dir) / "sources/nppa_retail_raw.csv"
    with open(path, encoding="utf-8") as handle:
        raw = list(csv.DictReader(handle))
    assert len(raw) >= len(medicines)


def test_no_preservative_is_recorded_as_an_ingredient(db):
    found = db.execute(
        text("SELECT count(*) FROM ingredients WHERE name ILIKE 'benzalkonium%'")
    ).scalar_one()
    assert found == 0


def test_real_identical_products_compare_across_companies_within_one_price_type(anon, db):
    id_ = db.scalar(
        text(
            "SELECT m.id FROM medicines m JOIN data_sources s ON s.id=m.source_id WHERE s.code='nppa_retail' "
            "AND m.display_name LIKE 'Telmisartan and Chlorthalidone%12.5 mg%' AND m.marketed_by LIKE 'Sun%' LIMIT 1"
        )
    )
    assert id_ is not None
    body = anon.get(f"/api/v1/medicines/{id_}/options").json()
    names = [o["medicine"]["display_name"] for o in body["equivalents"]]
    assert any("Alkem" in name for name in names)
    option = next(o for o in body["equivalents"] if "Alkem" in o["medicine"]["display_name"])
    assert option["prices"][0]["price_type"] == "notified_retail"
    assert option["prices"][0]["is_demo"] is False
    assert option["savings"] and "NPPA notified retail price" in option["savings"][0]["statement"]
    detail = anon.get(f"/api/v1/medicines/{id_}").json()
    assert detail["manufacturer"].startswith("Sun")


def test_notified_price_is_labelled_as_not_a_shop_price(anon, db):
    id_ = db.scalar(
        text(
            "SELECT medicine_id FROM price_observations WHERE price_type='notified_retail' LIMIT 1"
        )
    )
    price = anon.get(f"/api/v1/medicines/{id_}/prices").json()["prices"][0]
    assert "not a shop price" in price["price_type_label"]


@pytest.mark.safety
def test_different_strength_from_another_company_is_not_equivalent(db):
    rows = db.execute(
        text(
            "SELECT id FROM medicines WHERE display_name LIKE 'Telmisartan and Chlorthalidone%' ORDER BY id LIMIT 40"
        )
    ).all()
    medicines = [get_medicine(db, row[0]) for row in rows]
    pairs = 0
    for first in medicines:
        for second in medicines:
            same_strengths = {i.strength_text for i in first.ingredients} == {
                i.strength_text for i in second.ingredients
            }
            if first.id != second.id and not same_strengths:
                assert not compare(attrs_of(first), attrs_of(second)).equivalent
                pairs += 1
    assert pairs > 0


def test_real_ceiling_row_is_not_equivalent_to_a_row_with_a_stated_salt(db):
    ceiling = get_medicine(
        db, db.scalar(text("SELECT id FROM medicines WHERE display_name='Metformin 500mg Tablet'"))
    )
    other = get_medicine(
        db,
        db.scalar(
            text(
                "SELECT m.id FROM medicines m JOIN data_sources s ON s.id=m.source_id WHERE s.code='nppa_retail' "
                "AND m.ingredient_key LIKE '%metformin%' LIMIT 1"
            )
        ),
    )
    assert not compare(attrs_of(ceiling), attrs_of(other)).equivalent


def test_meta_reports_demo_data(anon):
    assert anon.get("/api/v1/meta").json() == {"demo_data_loaded": True}


def test_real_only_mode_skips_demo_sources(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "include_demo_data", False)
    sources = ensure_sources(db)
    assert sources and not any(source.is_demo for source in sources.values())
    assert "nppa_retail" in sources and "demo_catalogue" not in sources
    db.rollback()
