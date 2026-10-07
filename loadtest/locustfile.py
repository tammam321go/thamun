import random

from locust import HttpUser, between, task

CUSTOMERS = ["D0001", "D0002", "D0003", "D0004"]
SCRIPTS: dict[str, list] = {}


class WalletUser(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self) -> None:
        self.customer = random.choice(CUSTOMERS)
        self.headers = {}
        with self.client.post("/auth/session", json={}, name="/auth/session", catch_response=True) as response:
            if response.status_code == 200:
                self.headers = {"Authorization": "Bearer " + response.json()["access_token"]}
            else:
                response.failure(f"session refused: {response.status_code}")
        if self.customer not in SCRIPTS:
            response = self.client.get("/demo/script", params={"customer_id": self.customer}, headers=self.headers,
                                       name="/demo/script")
            if response.status_code == 200:
                SCRIPTS[self.customer] = response.json()
        self.script = SCRIPTS.get(self.customer, [])

    @task(6)
    def check_and_pay(self) -> None:
        if not self.script:
            return
        item = random.choice(self.script)
        body = {"customer_id": self.customer, "type": item["type"], "counterparty": item["counterparty"], "amount": item["amount"]}
        response = self.client.post("/check", json=body, headers=self.headers, name="/check")
        if response.status_code != 200:
            return
        result = response.json()
        if result["decision"] == "ask_purpose":
            body["purpose"] = item.get("purpose_hint") or "friend"
            response = self.client.post("/check", json=body, headers=self.headers, name="/check")
            if response.status_code != 200:
                return
            result = response.json()
        if "check_id" in result:
            self.client.post("/pay", json={"customer_id": self.customer, "check_id": result["check_id"], "action": "cancel"},
                             headers=self.headers, name="/pay")

    @task(2)
    def home(self) -> None:
        self.client.get("/home", params={"customer_id": self.customer}, headers=self.headers, name="/home")

    @task(1)
    def number_check(self) -> None:
        number = random.choice(["01099004411", "01022009966", "0101" + str(random.randint(1000000, 9999999))])
        self.client.get("/reports/check", params={"customer_id": self.customer, "number": number}, headers=self.headers,
                        name="/reports/check")

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="/health")
