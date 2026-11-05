"""Pharmacist portal, share links, summaries, admin import and data-quality checks."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import pypdf
import pytest
from sqlalchemy import select

from app.imports import pipeline
from app.imports.normalize import (
    normalize_catalogue_row,
    normalize_flag_row,
    normalize_ja_kendra_row,
    normalize_ja_product_row,
    normalize_nppa_row,
)
from app.models import DataSource, ImportBatch, JanAushadhiKendra, Medicine, ShareLink, StagedRow
from app.quality import run_quality_checks
from tests.conftest import Api, manual_item, verify_first

DISCUSS = "Discuss with your doctor or pharmacist before changing any medicine."


def share(owner: Api, prescription_id: str, pharmacist: Api):
    return owner.post(
        f"/api/v1/prescriptions/{prescription_id}/shares",
        json={"pharmacist_id": pharmacist.user["id"]},
    )


def test_pharmacist_sees_only_what_is_shared_with_them(
    user, other_user, pharmacist, other_pharmacist
):
    mine = manual_item(user, "Metformin", "500 mg", "Tab")
    not_shared = manual_item(other_user, "Cetirizine", "10 mg", "Tab")
    assert share(user, mine["id"], pharmacist).status_code == 201
    queue = pharmacist.get("/api/v1/pharmacist/queue").json()["queue"]
    assert [row["prescription_id"] for row in queue] == [mine["id"]]
    assert pharmacist.get(f"/api/v1/pharmacist/prescriptions/{mine['id']}").status_code == 200
    assert pharmacist.get(f"/api/v1/pharmacist/prescriptions/{not_shared['id']}").status_code == 404
    assert other_pharmacist.get(f"/api/v1/pharmacist/prescriptions/{mine['id']}").status_code == 404
    assert other_pharmacist.get("/api/v1/pharmacist/queue").json()["queue"] == []
    item = mine["items"][0]
    denied = other_pharmacist.post(
        f"/api/v1/pharmacist/prescriptions/{mine['id']}/items/{item['id']}/verify",
        json={"medicine_id": item["candidates"][0]["medicine"]["id"]},
    )
    assert denied.status_code == 404
    assert pharmacist.get(f"/api/v1/prescriptions/{mine['id']}").status_code == 404


def test_revoking_a_share_ends_access(user, pharmacist):
    mine = manual_item(user, "Metformin", "500 mg", "Tab")
    share(user, mine["id"], pharmacist)
    assert (
        user.delete(
            f"/api/v1/prescriptions/{mine['id']}/shares/{pharmacist.user['id']}"
        ).status_code
        == 204
    )
    assert pharmacist.get(f"/api/v1/pharmacist/prescriptions/{mine['id']}").status_code == 404
    assert pharmacist.get("/api/v1/pharmacist/queue").json()["queue"] == []
    assert share(user, mine["id"], pharmacist).status_code == 201
    assert pharmacist.get(f"/api/v1/pharmacist/prescriptions/{mine['id']}").status_code == 200


def test_pharmacist_verification_is_distinguished(user, pharmacist):
    mine = manual_item(user, "Metformin", "500 mg", "Tab")
    share(user, mine["id"], pharmacist)
    item = mine["items"][0]
    base = f"/api/v1/pharmacist/prescriptions/{mine['id']}/items/{item['id']}"
    corrected = pharmacist.patch(base, json={"form": "Tablet"})
    assert corrected.status_code == 200
    assert corrected.json()["events"][-1]["verifier_type"] == "pharmacist"
    chosen = corrected.json()["candidates"][0]["medicine"]["id"]
    verified = pharmacist.post(
        f"{base}/verify",
        json={"medicine_id": chosen, "lasa_acknowledged": True, "note": "Checked."},
    )
    assert verified.status_code == 200
    assert verified.json()["verified_by_type"] == "pharmacist"
    event = verified.json()["events"][-1]
    assert event["verifier_type"] == "pharmacist" and event["note"] == "Checked."
    assert (
        user.get(f"/api/v1/prescriptions/{mine['id']}/items/{item['id']}/prices").status_code == 200
    )
    done = pharmacist.post(
        f"/api/v1/pharmacist/prescriptions/{mine['id']}/complete", json={"note": "All clear."}
    )
    assert done.status_code == 200
    shares = user.get(f"/api/v1/prescriptions/{mine['id']}").json()["shares"]
    assert shares[0]["status"] == "reviewed" and shares[0]["note"] == "All clear."


def test_pharmacist_can_mark_unresolved(user, pharmacist):
    mine = manual_item(user, "Metformin", "500 mg", "Tab")
    share(user, mine["id"], pharmacist)
    item = mine["items"][0]
    response = pharmacist.post(
        f"/api/v1/pharmacist/prescriptions/{mine['id']}/items/{item['id']}/unresolved",
        json={"note": "Ask prescriber"},
    )
    assert response.status_code == 200 and response.json()["status"] == "unresolved"


def test_pharmacist_registration_needs_admin_approval(user, admin):
    api = Api()
    email = f"pharm-{uuid.uuid4().hex[:6]}@example.com"
    registered = api.client.post(
        "/api/v1/auth/register-pharmacist",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "registration_number": "TN-123",
            "state_council": "Tamil Nadu",
            "display_name": "P",
        },
    )
    assert registered.status_code == 201
    api.csrf, api.user = registered.json()["csrf_token"], registered.json()["user"]
    assert api.user["role"] == "user" and api.user["pharmacist_status"] == "pending"
    assert api.get("/api/v1/pharmacist/queue").status_code == 403
    assert (
        user.post(
            f"/api/v1/prescriptions/{manual_item(user, 'Metformin')['id']}/shares",
            json={"pharmacist_id": api.user["id"]},
        ).status_code
        == 404
    )
    pending = admin.get("/api/v1/admin/pharmacists", params={"status": "pending"}).json()[
        "pharmacists"
    ]
    assert pending[0]["registration_number"] == "TN-123"
    assert "Self-declared" in pending[0]["registration_label"]
    decision = admin.post(
        f"/api/v1/admin/pharmacists/{api.user['id']}/decision", json={"status": "approved"}
    )
    assert decision.status_code == 200
    assert api.get("/api/v1/pharmacist/queue").status_code == 200
    listed = user.get("/api/v1/pharmacists").json()["pharmacists"]
    assert "self-declared, checked manually by admin" in listed[0]["registration_label"]
    assert (
        admin.post(
            f"/api/v1/admin/pharmacists/{uuid.uuid4()}/decision", json={"status": "approved"}
        ).status_code
        == 404
    )
    assert (
        admin.post(
            f"/api/v1/admin/pharmacists/{api.user['id']}/decision", json={"status": "x"}
        ).status_code
        == 422
    )
    assert (
        admin.post(
            f"/api/v1/admin/pharmacists/{api.user['id']}/decision", json={"status": "rejected"}
        ).status_code
        == 200
    )
    assert api.get("/api/v1/pharmacist/queue").status_code == 403


def two_item_prescription(user: Api) -> dict:
    response = user.post(
        "/api/v1/prescriptions/manual",
        json={
            "items": [
                {"name": "Metformin", "strength": "500 mg", "form": "Tab"},
                {"name": "Cetirizine Unverifiedname", "strength": "10 mg"},
            ]
        },
    )
    return response.json()


def test_summary_contains_verified_items_only(user):
    prescription = two_item_prescription(user)
    verify_first(user, prescription)
    summary = user.get(f"/api/v1/prescriptions/{prescription['id']}/summary").json()
    assert len(summary["medicines"]) == 1
    assert summary["items_not_included"] == 1
    assert summary["statement"] == DISCUSS
    assert "Unverifiedname" not in str(summary)


def test_summary_has_no_personal_identifiers(user):
    prescription = two_item_prescription(user)
    verify_first(user, prescription)
    text = user.get(f"/api/v1/prescriptions/{prescription['id']}/summary").text
    assert user.user["email"] not in text and user.user["id"] not in text


def pdf_text(data: bytes) -> str:
    return " ".join((page.extract_text() or "") for page in pypdf.PdfReader(io.BytesIO(data)).pages)


def test_pdf_contains_statement_and_excludes_unverified(user):
    prescription = two_item_prescription(user)
    verify_first(user, prescription)
    response = user.get(f"/api/v1/prescriptions/{prescription['id']}/summary.pdf")
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    text = " ".join(pdf_text(response.content).split())
    assert DISCUSS in text
    assert "Unverifiedname" not in text


def test_pdf_shows_options_price_types_flags_and_demo_label(user, db):
    prescription = manual_item(user, "DemoSalbuAlpha", "4 mg", "Tab")
    verify_first(user, prescription)
    text = " ".join(
        pdf_text(
            user.get(f"/api/v1/prescriptions/{prescription['id']}/summary.pdf").content
        ).split()
    )
    assert "Demo data" in text and "MRP" in text and "Option to discuss" in text


def test_share_link_flow_and_expiry(user, db, anon):
    prescription = two_item_prescription(user)
    verify_first(user, prescription)
    created = user.post(
        f"/api/v1/prescriptions/{prescription['id']}/share-links",
        json={"label": "For my pharmacist"},
    )
    assert created.status_code == 201
    token = created.json()["token"]
    stored = db.scalars(select(ShareLink)).one()
    assert token not in stored.token_hash
    body = anon.get(f"/api/v1/shared/{token}")
    assert body.status_code == 200
    assert (
        body.json()["label"] == "For my pharmacist" and "no-store" in body.headers["cache-control"]
    )
    assert "Unverifiedname" not in body.text
    assert anon.get(f"/api/v1/shared/{token}/pdf").headers["content-type"] == "application/pdf"
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert anon.get(f"/api/v1/shared/{token}").status_code == 410
    assert anon.get(f"/api/v1/shared/{token}/pdf").status_code == 410
    assert anon.get(f"/api/v1/shared/{token}").json()["code"] == "link_expired"


def test_revoked_and_unknown_links(user, anon):
    prescription = two_item_prescription(user)
    verify_first(user, prescription)
    created = user.post(f"/api/v1/prescriptions/{prescription['id']}/share-links", json={}).json()
    assert (
        user.delete(
            f"/api/v1/prescriptions/{prescription['id']}/share-links/{created['id']}"
        ).status_code
        == 204
    )
    assert anon.get(f"/api/v1/shared/{created['token']}").status_code == 410
    assert anon.get("/api/v1/shared/" + "x" * 40).status_code == 404
    assert anon.get("/api/v1/shared/bad!").status_code == 404
    assert (
        user.delete(
            f"/api/v1/prescriptions/{prescription['id']}/share-links/{uuid.uuid4()}"
        ).status_code
        == 404
    )


def test_link_cannot_be_made_with_nothing_verified(user):
    prescription = two_item_prescription(user)
    response = user.post(f"/api/v1/prescriptions/{prescription['id']}/share-links", json={})
    assert response.status_code == 409 and response.json()["code"] == "nothing_verified"


def test_deleting_the_prescription_kills_the_link(user, anon):
    prescription = two_item_prescription(user)
    verify_first(user, prescription)
    token = user.post(f"/api/v1/prescriptions/{prescription['id']}/share-links", json={}).json()[
        "token"
    ]
    assert user.delete(f"/api/v1/prescriptions/{prescription['id']}").status_code == 204
    assert anon.get(f"/api/v1/shared/{token}").status_code == 404


def test_status_becomes_verified_when_all_items_are_resolved(user):
    prescription = two_item_prescription(user)
    verify_first(user, prescription)
    assert (
        user.get(f"/api/v1/prescriptions/{prescription['id']}").json()["status"]
        == "needs_verification"
    )
    second = prescription["items"][1]
    response = user.post(
        f"/api/v1/prescriptions/{prescription['id']}/items/{second['id']}/unresolved", json={}
    )
    assert "prescriber" in response.json()["guidance"]
    assert user.get(f"/api/v1/prescriptions/{prescription['id']}").json()["status"] == "verified"


def csv_bytes(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


GOOD_KENDRA = {
    "kendra_code": "TEST-1",
    "name": "Test Kendra",
    "address": "Test Road",
    "district": "Test",
    "state": "Test State",
    "pin_code": "560099",
    "latitude": "",
    "longitude": "",
    "observed_at": "2026-10-01",
}


def test_admin_import_stages_validates_queues_and_publishes(admin, db):
    bad = {**GOOD_KENDRA, "kendra_code": "TEST-2", "pin_code": "12"}
    duplicate = dict(GOOD_KENDRA)
    response = admin.post(
        "/api/v1/admin/imports",
        files={"file": ("kendras.csv", csv_bytes([GOOD_KENDRA, bad, duplicate]), "text/csv")},
        data={"source_code": "demo_jan_aushadhi", "kind": "ja_kendras"},
    )
    assert response.status_code == 201, response.text
    batch = response.json()
    assert (batch["row_count"], batch["valid_count"], batch["failed_count"]) == (3, 1, 2)
    assert (
        db.scalar(select(JanAushadhiKendra).where(JanAushadhiKendra.kendra_code == "TEST-1"))
        is None
    )
    queue = admin.get("/api/v1/admin/review-queue", params={"batch_id": batch["id"]}).json()["rows"]
    assert len(queue) == 2 and any("pin_code" in " ".join(row["errors"]) for row in queue)
    fix = next(row for row in queue if "pin_code" in " ".join(row["errors"]))
    still_bad = admin.put(
        f"/api/v1/admin/review-queue/{fix['id']}", json={"raw": {**fix["raw"], "pin_code": "9"}}
    )
    assert still_bad.json()["status"] == "failed"
    fixed = admin.put(
        f"/api/v1/admin/review-queue/{fix['id']}",
        json={"raw": {**fix["raw"], "pin_code": "560098"}},
    )
    assert fixed.json()["status"] == "valid"
    duplicate_row = next(row for row in queue if row["id"] != fix["id"])
    assert admin.delete(f"/api/v1/admin/review-queue/{duplicate_row['id']}").status_code == 204
    published = admin.post(f"/api/v1/admin/imports/{batch['id']}/publish")
    assert published.status_code == 200 and published.json()["published"] == 2
    kendra = db.scalar(select(JanAushadhiKendra).where(JanAushadhiKendra.kendra_code == "TEST-1"))
    assert kendra.batch_id == batch["id"] and kendra.is_demo is True
    assert admin.post(f"/api/v1/admin/imports/{batch['id']}/publish").status_code == 409
    assert admin.post(f"/api/v1/admin/imports/{batch['id']}/reject").status_code == 409
    assert (
        admin.put(f"/api/v1/admin/review-queue/{fix['id']}", json={"raw": fix["raw"]}).status_code
        == 409
    )
    actions = admin.get("/api/v1/admin/audit").text
    assert (
        "import_staged" in actions
        and "import_published" in actions
        and "import_row_corrected" in actions
    )
    db.delete(kendra)
    db.query(JanAushadhiKendra).filter_by(kendra_code="TEST-2").delete()
    db.commit()


def test_admin_import_validation_errors(admin):
    files = {"file": ("a.csv", b"x,y\n1,2\n", "text/csv")}
    assert (
        admin.post(
            "/api/v1/admin/imports", files=files, data={"source_code": "nope", "kind": "ja_kendras"}
        ).status_code
        == 404
    )
    assert (
        admin.post(
            "/api/v1/admin/imports",
            files=files,
            data={"source_code": "demo_jan_aushadhi", "kind": "nope"},
        ).status_code
        == 422
    )
    binary = {"file": ("a.csv", b"\xff\xfe\x00\x01", "text/csv")}
    assert (
        admin.post(
            "/api/v1/admin/imports",
            files=binary,
            data={"source_code": "demo_jan_aushadhi", "kind": "ja_kendras"},
        ).status_code
        == 422
    )
    assert admin.post("/api/v1/admin/imports/99999999/publish").status_code == 404
    assert admin.put("/api/v1/admin/review-queue/99999999", json={"raw": {}}).status_code == 404
    assert admin.delete("/api/v1/admin/review-queue/99999999").status_code == 404


def test_admin_can_reject_a_batch(admin):
    batch = admin.post(
        "/api/v1/admin/imports",
        files={"file": ("k.csv", csv_bytes([GOOD_KENDRA]), "text/csv")},
        data={"source_code": "demo_jan_aushadhi", "kind": "ja_kendras"},
    ).json()
    assert admin.post(f"/api/v1/admin/imports/{batch['id']}/reject").json()["status"] == "rejected"
    assert any(
        row["id"] == batch["id"] for row in admin.get("/api/v1/admin/imports").json()["batches"]
    )


def test_freshness_dashboard_data(admin):
    sources = {s["code"]: s for s in admin.get("/api/v1/admin/sources").json()["sources"]}
    nppa = sources["nppa_ceiling"]
    assert nppa["is_demo"] is False and nppa["medicines"] > 200
    assert nppa["data_as_of"] == "2026-03-31"
    assert nppa["is_stale"] is True
    assert sources["demo_catalogue"]["is_demo"] is True


def test_seeded_review_queue_holds_real_failed_rows(admin):
    rows = admin.get("/api/v1/admin/review-queue").json()["rows"]
    assert any("Oxaliplatin" in str(row["raw"]) or "Tramadol" in str(row["raw"]) for row in rows)


def test_seed_is_idempotent_and_quality_passes(db):
    from app.imports.seed import seed

    before = db.query(Medicine).count()
    seed(db)
    assert db.query(Medicine).count() == before
    report = run_quality_checks(db)
    assert report["passed"], report
    assert report["counts"]["medicines"] >= 370


def test_provenance_is_recorded(db):
    medicine = db.scalar(select(Medicine).where(Medicine.display_name == "Metformin 500mg Tablet"))
    assert medicine.batch_id and medicine.source_row and medicine.source_text
    assert medicine.prices[0].batch_id == medicine.batch_id
    batch = db.get(ImportBatch, medicine.batch_id)
    assert len(batch.file_sha256) == 64
    row = db.scalar(
        select(StagedRow).where(
            StagedRow.batch_id == batch.id, StagedRow.row_number == medicine.source_row
        )
    )
    assert row.raw["name"] == "Metformin"


def test_all_real_rows_are_not_demo_and_all_demo_rows_are(db):
    for medicine in db.scalars(select(Medicine)).all():
        assert medicine.is_demo == medicine.source.is_demo
        assert medicine.is_demo == (medicine.brand is not None)


NPPA_ROW = {
    "name": "Metformin",
    "dosage_form": "Tablet",
    "strength": "500mg",
    "unit_text": "1 Tablet",
    "ceiling_price_inr": "2.07",
    "category": "anti-diabetes",
}


def test_nppa_normaliser_handles_real_shapes():
    good, errors = normalize_nppa_row(NPPA_ROW)
    assert (
        errors == []
        and good["display_name"] == "Metformin 500mg Tablet"
        and good["pack_unit"] == "tablet"
    )
    fdc, _ = normalize_nppa_row(
        {
            **NPPA_ROW,
            "name": "TenofovirDisproxilFum arate (A) +Lamivudine(B)+Efavir enz(C)",
            "strength": "300mg(A)+ 300mg(B)+600mg(C)",
        }
    )
    assert [i["name"] for i in fdc["ingredients"]] == [
        "Tenofovir Disoproxil",
        "Lamivudine",
        "Efavirenz",
    ]
    assert fdc["ingredients"][0]["salt_form"] == "fumarate"
    enteric, _ = normalize_nppa_row(
        {**NPPA_ROW, "name": "Acetylsalicylic acid Enteric coated", "strength": "75 mg"}
    )
    assert (
        enteric["release_type"] == "enteric_coated"
        and enteric["ingredients"][0]["name"] == "Acetylsalicylic acid"
    )
    sublingual, _ = normalize_nppa_row(
        {**NPPA_ROW, "name": "Glyceryl trinitrate Sublingual", "strength": "0.5mg"}
    )
    assert sublingual["route"] == "sublingual"
    mr, _ = normalize_nppa_row({**NPPA_ROW, "dosage_form": "Modified release Tablet"})
    assert mr["release_type"] == "modified"
    each, _ = normalize_nppa_row(
        {**NPPA_ROW, "dosage_form": "Injection", "strength": "750,000IU", "unit_text": "Each Pack"}
    )
    assert each["pack_quantity"] == "1" and each["pack_unit"] == "pack"


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"strength": "as licensed"}, "strength"),
        ({"dosage_form": "Potion"}, "dosage_form"),
        ({"unit_text": "some"}, "unit"),
        ({"ceiling_price_inr": "abc"}, "price"),
        ({"ceiling_price_inr": "0"}, "price"),
        ({"ceiling_price_inr": "99999999"}, "price"),
        ({"name": "A (A)+B (B)"}, "strength"),
        ({"name": "Aspirin Conventional / Dispersible"}, "form"),
    ],
)
def test_nppa_normaliser_refuses_to_guess(change, fragment):
    value, errors = normalize_nppa_row({**NPPA_ROW, **change})
    assert value is None and any(fragment in error for error in errors)


def test_catalogue_normaliser():
    row = {
        "display_name": "X",
        "generic_name": "X",
        "ingredients": "Foo:salt:5 mg",
        "dosage_form": "tablet",
        "route": "oral",
        "release_type": "conventional",
        "pack_quantity": "10",
        "pack_unit": "tablet",
        "price_type": "mrp",
        "price": "5.00",
        "observed_at": "2026-01-01",
    }
    assert normalize_catalogue_row(row)[0]["ingredients"][0]["salt_form"] == "salt"
    no_price = {**row, "price": "", "price_type": "", "observed_at": ""}
    assert normalize_catalogue_row(no_price)[0]["price"] is None
    for change in (
        {"display_name": ""},
        {"dosage_form": "x"},
        {"route": "x"},
        {"release_type": "x"},
        {"ingredients": "bad"},
        {"ingredients": "a:b:notastrength"},
        {"pack_quantity": "0"},
        {"pack_quantity": "x"},
        {"price_type": "x"},
        {"observed_at": "soon"},
    ):
        assert normalize_catalogue_row({**row, **change})[0] is None, change


def test_other_normalisers_report_errors():
    assert normalize_ja_product_row({})[0] is None
    assert normalize_ja_product_row(
        {"drug_code": "1", "generic_name": "x", "mrp": "1", "unit_size": "1"}
    )[0]
    assert normalize_ja_kendra_row({})[0] is None
    assert normalize_flag_row({})[0] is None
    assert normalize_flag_row(
        {
            "flag_type": "quality_alert",
            "medicine_display_name": "x",
            "description": "y",
            "source_date": "2026-01-01",
        }
    )[0]


def test_flag_for_unknown_medicine_goes_to_the_queue(db):
    source = db.scalar(select(DataSource).where(DataSource.code == "demo_regulatory"))
    row = {
        "flag_type": "quality_alert",
        "medicine_display_name": "Nope",
        "description": "y",
        "source_date": "2026-01-01",
        "source_url": "",
    }
    batch = pipeline.stage_rows(
        db, source=source, kind="regulatory_flags", file_name="f.csv", content=csv_bytes([row])
    )
    result = pipeline.publish(db, batch)
    assert result == {"published": 0, "failed": 1}
    db.rollback()


def test_stage_rejects_unknown_kind_and_publish_rejects_wrong_status(db):
    source = db.scalar(select(DataSource).where(DataSource.code == "demo_regulatory"))
    with pytest.raises(pipeline.ImportError_):
        pipeline.stage_rows(db, source=source, kind="nope", file_name="f", content=b"")
    with pytest.raises(pipeline.ImportError_):
        pipeline.publish(
            db,
            ImportBatch(
                source_id=source.id,
                kind="catalogue",
                status="published",
                file_name="f",
                file_sha256="0",
            ),
        )
    db.rollback()


def test_importing_a_second_price_keeps_history(db):
    source = db.scalar(select(DataSource).where(DataSource.code == "demo_catalogue"))
    row = {
        "display_name": "DemoLosar (Losartan 50 mg)",
        "brand": "DemoLosar",
        "manufacturer": "Demo Labs One",
        "generic_name": "Losartan 50 mg",
        "ingredients": "Losartan:potassium:50 mg",
        "dosage_form": "tablet",
        "route": "oral",
        "release_type": "conventional",
        "therapeutic_category": "cardiovascular",
        "pack_quantity": "10",
        "pack_unit": "tablet",
        "price_type": "mrp",
        "price": "43.00",
        "observed_at": "2026-10-20",
    }
    batch = pipeline.stage_rows(
        db, source=source, kind="catalogue", file_name="p.csv", content=csv_bytes([row])
    )
    pipeline.publish(db, batch)
    medicine = db.scalar(select(Medicine).where(Medicine.display_name == row["display_name"]))
    db.flush()
    db.refresh(medicine)
    assert len(medicine.prices) == 2
    db.rollback()


def test_lasa_pairs_exclude_generated_demo_families_and_include_deliberate_pairs(db):
    from app.models import LasaPair

    pairs = {(p.name_a, p.name_b) for p in db.scalars(select(LasaPair)).all()}
    assert ("demometacin", "demometocin") in pairs
    assert not any(
        name.endswith(("alpha", "beta", "gamma", "delta")) for pair in pairs for name in pair
    )
