import json
import sys
import time
from pathlib import Path

import httpx

BASE = "https://api-production-a4cb.up.railway.app"
KEY = "invitadora-test-key-2026"
headers = {"X-API-Key": KEY}
csv_path = Path(__file__).resolve().parent.parent / "test.csv"


def main() -> int:
    with httpx.Client(timeout=60.0) as client:
        campaign_payload = {
            "organizer_name": "Prueba API",
            "event_at": "2026-12-12T21:00:00-03:00",
            "template_name": "confirmacion_registro",
            "template_language": "es_CL",
        }
        r = client.post(f"{BASE}/v1/campaigns", headers=headers, json=campaign_payload)
        if r.status_code == 422:
            r = client.post(f"{BASE}/v1/campaigns", headers=headers, json={"body": campaign_payload})
        print("CREATE", r.status_code, r.text)
        r.raise_for_status()
        cid = r.json()["id"]
        print("campaign_id=", cid)

        with csv_path.open("rb") as f:
            r = client.post(
                f"{BASE}/v1/campaigns/{cid}/import-file",
                headers=headers,
                files={"file": ("test.csv", f, "text/csv")},
                data={"has_header": "true"},
            )
        print("IMPORT", r.status_code, r.text)
        r.raise_for_status()

        dispatch_payload = {"delay_seconds": 2, "confirm": True}
        r = client.post(
            f"{BASE}/v1/campaigns/{cid}/dispatch",
            headers=headers,
            json=dispatch_payload,
        )
        if r.status_code == 422:
            r = client.post(
                f"{BASE}/v1/campaigns/{cid}/dispatch",
                headers=headers,
                json={"body": dispatch_payload},
            )
        print("DISPATCH", r.status_code, r.text)
        r.raise_for_status()
        print("job_id=", r.json()["job_id"])

        final_stats = None
        for i in range(40):
            time.sleep(3)
            rs = client.get(f"{BASE}/v1/campaigns/{cid}/stats", headers=headers)
            stats = rs.json()
            final_stats = stats
            print(
                f"poll {i+1}: status={stats.get('status')} "
                f"sent={stats.get('total_sent')} failed={stats.get('total_failed')} "
                f"pending={stats.get('pending')}"
            )
            if stats.get("status") in ("completed", "completed_with_errors", "failed"):
                break

        rr = client.get(f"{BASE}/v1/campaigns/{cid}/recipients", headers=headers)
        print("RECIPIENTS", rr.status_code)
        print(json.dumps(rr.json(), ensure_ascii=False, indent=2))
        print("FINAL_STATS", json.dumps(final_stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
