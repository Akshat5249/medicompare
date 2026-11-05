"""Search, detail, prices, options and Jan Aushadhi behaviour on the seeded catalogue."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.catalogue.service import transliterate
from app.models import DataSource, Medicine, PackSize, PriceObservation
from app.pricing.comparison import is_stale
from tests.conftest import medicine_id


def search(anon, q, **params):
    response = anon.get("/api/v1/search", params={"q": q, **params})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("metformn", "metformin"),
        ("amlodipin", "amlodipine"),
        ("atorvastatn", "atorvastatin"),
        ("telmisarton", "telmisartan"),
    ],
)
def test_typos_find_possible_matches_and_explain_why(anon, query, expected):
    body = search(anon, query)
    assert body["exact_matches"] == []
    assert body["possible_matches"]
    assert expected in body["possible_matches"][0]["medicine"]["display_name"].lower()
    assert "does not mean the same medicine" in body["possible_matches"][0]["reason"]


def test_exact_ingredient_search_is_exact_and_explained(anon):
    body = search(anon, "Metformin")
    assert body["exact_matches"]
    assert any(
        "active ingredient" in hit["reason"] or "appears" in hit["reason"]
        for hit in body["exact_matches"]
    )
    assert body["exact_matches"][0]["medicine"]["is_demo"] is False


def test_brand_search(anon):
    body = search(anon, "DemoLosar")
    assert body["exact_matches"][0]["medicine"]["brand"] == "DemoLosar"
    assert body["exact_matches"][0]["reason"] == "Brand name matches exactly."


def test_same_ingredient_different_strength_are_separate_records(anon):
    names = {
        hit["medicine"]["display_name"] for hit in search(anon, "Atorvastatin")["exact_matches"]
    }
    assert {
        "Atorvastatin 10mg Tablet",
        "Atorvastatin 20mg Tablet",
        "Atorvastatin 40mg Tablet",
    } <= names


def test_same_ingredient_different_form_are_separate_records(anon):
    forms = {hit["medicine"]["dosage_form"] for hit in search(anon, "Ramipril")["exact_matches"]}
    assert {"Tablet", "Capsule"} <= forms


@pytest.mark.parametrize(
    ("query", "expected"),
    [("मेटफॉर्मिन", "metformin"), ("பாராசிட்டமால்", "paracetamol"), ("पैरासिटामोल", "paracetamol")],
)
def test_hindi_and_tamil_script_input(anon, query, expected):
    body = search(anon, query)
    hits = body["exact_matches"] + body["possible_matches"]
    assert hits and expected in hits[0]["medicine"]["display_name"].lower()


def test_transliteration_of_unlisted_script_input_still_gives_recall(anon):
    assert transliterate("metformin") == "metformin"
    assert transliterate("टेल्मि").startswith("t")
    body = search(anon, "एटोरवास्टेटिन")
    assert body["exact_matches"] + body["possible_matches"]


def test_nonsense_returns_nothing(anon):
    body = search(anon, "zzzzqqqq")
    assert body["exact_matches"] == [] and body["possible_matches"] == []


def test_search_validates_input(anon):
    assert anon.get("/api/v1/search", params={"q": "a"}).status_code == 422
    response = anon.get("/api/v1/search")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_detail_contains_required_fields(anon, db):
    medicine = medicine_id(db, "DemoMetfoAlpha (Metformin 500 mg)")
    body = anon.get(f"/api/v1/medicines/{medicine}").json()
    assert body["ingredients"][0] == {
        "name": "Metformin",
        "salt_form": "hydrochloride",
        "salt_form_stated": True,
        "strength": "500 mg",
    }
    for key in (
        "dosage_form",
        "route",
        "release_type",
        "pack_sizes",
        "manufacturer",
        "regulatory_flags",
        "source",
        "source_date",
    ):
        assert key in body


def test_real_record_shows_source_text_and_unstated_salt(anon, db):
    medicine = db.scalar(
        text("SELECT id FROM medicines WHERE display_name='Metformin 500mg Tablet'")
    )
    body = anon.get(f"/api/v1/medicines/{medicine}").json()
    assert body["source"]["code"] == "nppa_ceiling" and body["is_demo"] is False
    assert body["ingredients"][0]["salt_form_stated"] is False
    assert "Metformin" in body["source_text"]


def test_missing_medicine_is_a_problem_document(anon):
    response = anon.get("/api/v1/medicines/99999999")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "not_found"


def test_no_price_state(anon, db):
    row = db.scalar(
        text(
            "SELECT m.id FROM medicines m WHERE NOT EXISTS (SELECT 1 FROM price_observations p WHERE p.medicine_id=m.id) LIMIT 1"
        )
    )
    assert row is not None
    body = anon.get(f"/api/v1/medicines/{row}/prices").json()
    assert body == {**body, "prices": [], "has_price": False}


def test_stale_price_state(anon, db):
    source = db.query(DataSource).filter_by(code="demo_catalogue").one()
    row = db.scalar(
        text(
            f"SELECT p.medicine_id FROM price_observations p WHERE p.observed_at='2025-06-01' AND p.source_id={source.id} LIMIT 1"
        )
    )
    assert row is not None
    prices = anon.get(f"/api/v1/medicines/{row}/prices").json()["prices"]
    assert prices and prices[0]["is_stale"] is True


def test_nppa_prices_are_labelled_stale_after_cadence():
    assert is_stale(date(2026, 3, 31), 90, date(2026, 11, 5))
    assert not is_stale(date(2026, 10, 1), 90, date(2026, 11, 5))


def test_latest_observation_wins(anon, db):
    medicine = db.get(Medicine, medicine_id(db, "DemoCetirAlpha (Cetirizine 10 mg)"))
    pack = db.query(PackSize).filter_by(medicine_id=medicine.id).first()
    existing = medicine.prices[0]
    newest = PriceObservation(
        medicine_id=medicine.id,
        pack_size_id=pack.id,
        price_type="mrp",
        amount_inr=Decimal("99.50"),
        source_id=existing.source_id,
        observed_at=date(2026, 10, 30),
        is_demo=True,
    )
    db.add(newest)
    db.commit()
    try:
        prices = anon.get(f"/api/v1/medicines/{medicine.id}/prices").json()["prices"]
        assert [p["amount_inr"] for p in prices] == ["99.50"]
        assert prices[0]["per_unit_inr"] == "9.95"
    finally:
        db.delete(newest)
        db.commit()


def test_options_list_equivalents_by_price_with_savings(anon, db):
    medicine = medicine_id(db, "DemoAtorvAlpha (Atorvastatin 10 mg)")
    body = anon.get(f"/api/v1/medicines/{medicine}/options").json()
    assert body["equivalents"]
    assert "reference" in body and "not_equivalent" in body and "jan_aushadhi" in body
    units = [
        float(option["prices"][0]["per_unit_inr"])
        for option in body["equivalents"]
        if option["prices"]
    ]
    assert units == sorted(units)
    savings = [saving for option in body["equivalents"] for saving in option["savings"]]
    for saving in savings:
        assert "Comparing MRP per tablet" in saving["statement"]


def test_real_ceiling_row_is_not_compared_with_demo_brand_because_salt_is_unstated(anon, db):
    medicine = db.scalar(
        text("SELECT id FROM medicines WHERE display_name='Metformin 500mg Tablet'")
    )
    body = anon.get(f"/api/v1/medicines/{medicine}/options").json()
    assert body["equivalents"] == []
    demo = [o for o in body["not_equivalent"] if o["medicine"]["is_demo"]]
    assert demo and any("salt_form_not_stated" in o["difference_codes"] for o in demo)


def test_regulatory_flags_show_source_and_date(anon, db):
    medicine = medicine_id(db, "DemoSalbuBeta (Salbutamol 4 mg)")
    flag = anon.get(f"/api/v1/medicines/{medicine}").json()["regulatory_flags"][0]
    assert (
        flag["flag_type"] == "quality_alert"
        and flag["source_name"]
        and flag["source_date"]
        and flag["is_demo"]
    )
    other = medicine_id(db, "DemoSalbuAlpha (Salbutamol 4 mg)")
    listed = anon.get(f"/api/v1/medicines/{other}/options").json()["equivalents"]
    flagged = [o for o in listed if o["medicine"]["display_name"].startswith("DemoSalbuBeta")]
    assert flagged and flagged[0]["regulatory_flags"]


def test_jan_aushadhi_products_search(anon):
    all_rows = anon.get("/api/v1/jan-aushadhi/products").json()
    assert all_rows["products"] and all_rows["products"][0]["is_demo"]
    body = anon.get("/api/v1/jan-aushadhi/products", params={"q": "metformin"}).json()
    product = body["products"][0]
    assert "Metformin" in product["generic_name"]
    assert (
        product["price_type"] == "catalogue"
        and product["source"]["name"]
        and product["last_updated"]
    )
    assert "Check with the Kendra" in body["notice"]


def test_kendra_search_by_pin_prefers_same_pin(anon):
    body = anon.get("/api/v1/jan-aushadhi/kendras", params={"pin": "600017"}).json()
    assert body["kendras"][0]["pin_code"] == "600017"
    assert {k["pin_code"][:3] for k in body["kendras"]} == {"600"}
    assert body["kendras"][0]["is_demo"] is True
    assert "before you travel" in body["notice"]


def test_kendra_search_by_area_and_location(anon):
    assert anon.get("/api/v1/jan-aushadhi/kendras", params={"area": "Tamil"}).json()["kendras"]
    body = anon.get("/api/v1/jan-aushadhi/kendras", params={"lat": 13.05, "lon": 80.24}).json()
    assert body["kendras"][0]["district"] == "Chennai"
    assert body["kendras"][0]["distance_km"] < 10


def test_kendra_search_requires_a_location_and_a_valid_pin(anon):
    assert anon.get("/api/v1/jan-aushadhi/kendras").status_code == 422
    assert anon.get("/api/v1/jan-aushadhi/kendras", params={"pin": "12"}).status_code == 422


def test_location_is_never_stored(anon, db):
    tables = [
        r[0]
        for r in db.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public' AND column_name IN ('latitude','longitude','lat','lon')"
            )
        ).all()
    ]
    assert set(tables) == {"jan_aushadhi_kendras"}


def test_jan_aushadhi_option_appears_separately(anon, db):
    medicine = medicine_id(db, "DemoMetfoBeta (Metformin 500 mg)")
    body = anon.get(f"/api/v1/medicines/{medicine}/options").json()
    assert body["jan_aushadhi"] and body["jan_aushadhi"][0]["price_type"] == "catalogue"


def test_health_endpoints(anon):
    assert anon.get("/api/v1/health/live").json() == {"status": "ok"}
    assert anon.get("/api/v1/health/ready").json() == {"status": "ready"}


def test_security_headers_present(anon):
    headers = anon.get("/api/v1/health/live").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in headers["content-security-policy"]


def test_openapi_is_3_1_and_documents_problem_details(anon):
    spec = anon.get("/api/v1/openapi.json").json()
    assert spec["openapi"].startswith("3.1")
    operation = spec["paths"]["/api/v1/medicines/{medicine_id}"]["get"]
    assert "application/problem+json" in operation["responses"]["4XX"]["content"]
