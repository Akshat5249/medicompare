"""Read-only load profile for search and comparison on the seeded catalogue."""
import random

from locust import HttpUser, between, task

QUERIES = ["metformin", "metformn", "amlodipine", "atorvastatin", "paracetamol", "DemoLosar", "telmisartan",
           "cetirizine", "glimepiride", "azithromycin", "rifampicin", "tenofovir", "imatinib", "pantoprazole"]


class Visitor(HttpUser):
    wait_time = between(0.2, 1.0)
    medicine_ids: list[int] = []

    @task(5)
    def search(self) -> None:
        with self.client.get("/api/v1/search", params={"q": random.choice(QUERIES)}, name="search", catch_response=True) as response:  # noqa: S311
            if response.ok:
                hits = response.json()["exact_matches"]
                self.medicine_ids = [hit["medicine"]["id"] for hit in hits][:10] or self.medicine_ids

    @task(3)
    def options(self) -> None:
        if self.medicine_ids:
            self.client.get(f"/api/v1/medicines/{random.choice(self.medicine_ids)}/options", name="comparison")  # noqa: S311

    @task(1)
    def prices(self) -> None:
        if self.medicine_ids:
            self.client.get(f"/api/v1/medicines/{random.choice(self.medicine_ids)}/prices", name="prices")  # noqa: S311
