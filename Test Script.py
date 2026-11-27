"""Run Danube chatbot questions sequentially and export final SSE answers to CSV."""

import csv
import json
import os
import time

import requests

API_URL = "http://127.0.0.1:8000/api/v1/chat/query"
OUTPUT_CSV = "chatbot_test_results.csv"
RUNS_PER_QUESTION = 20

# Set these environment variables before running (do not commit real credentials).
# BEARER_TOKEN = "U2FsdGVkX18uTSMWRy8vi3RXHdSpJGVr1zWZiTCo/fSH0U9PycmW4ld9sB14zhEx8aK7BQPM4ZV+1P7w/E2Nq7sAfPQM7D54cyGe+RX8TrC3fiPFadNVFS5y4bU/sdH70JmA8/jE91kClzLWG7E8fqflR3D+yZNBNGJL/b+VL4omLDRyah3qn/BeQmu0rrTh"
BEARER_TOKEN = "U2FsdGVkX181paOBU1G4Qxu/2tnQYeP+MwTNeJdqywxVWTfZV6hZCliVd6/2WBxeN/3s9cPYIlY0skOH04zIy9OloQyTSOGUrqJr5SFXZRhLytjhPHkNf+HNuzwJMBPFv6X2aArsRKh7s0t97MOAdh4bxxFgsUesRRqurzqnqK+2UnW/4Hv8qZiebccIdB0K"
APIM_SUBSCRIPTION_KEY = "79ba0d09adf14ce0a63803302e989324"


QUESTIONS = [
    "Show all units with skyline view",
    "what 2 bedroom available in sports city"
]


PAYLOAD = {
    "user_id": "005NM00HJ6xUKQKYM4",
    "message": "",
    "start_conversation": True,
    "session_id": "null",  # Matches the supplied curl request exactly.
    "role": "BDCXO",
    "source": "mobile_app",
    "employee_type": "",
    "key_features": "HomePage,UnitTab,PDPage,UDPage, DownloadAvailability"
}


def get_chatbot_response(question, headers):
    payload = {**PAYLOAD, "message": question}

    with requests.post(
        API_URL,
        headers=headers,
        json=payload,
        stream=True,
        timeout=(15, 180),
    ) as response:

        response.raise_for_status()

        event_type = None
        data_lines = []

        final_text = None
        html_blocks = []
        error_message = None

        def process_event(event_name, lines):
            nonlocal final_text, error_message

            if not lines:
                return

            try:
                data = json.loads("\n".join(lines))
            except json.JSONDecodeError:
                return

            if event_name == "final" and isinstance(data, dict):
                final_text = data.get("response", "")

            elif event_name == "html_block" and isinstance(data, dict):
                # Save the HTML string, not the complete SSE JSON.
                html = data.get("html", "")
                if html:
                    html_blocks.append(html)

            elif event_name == "error":
                error_message = (
                    data.get("message", str(data))
                    if isinstance(data, dict)
                    else str(data)
                )

        for line in response.iter_lines(decode_unicode=True):

            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")

            if line == "":
                process_event(event_type, data_lines)
                event_type, data_lines = None, []

            elif line.startswith("event:"):
                event_type = line[6:].strip()

            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip(" "))

        # Handle final event without trailing blank line.
        process_event(event_type, data_lines)

        if error_message:
            raise ValueError(error_message)

        if final_text is None and not html_blocks:
            raise ValueError("No final or html_block SSE event received")

        return final_text or "", "\n".join(html_blocks)


def main():

    if not BEARER_TOKEN or not APIM_SUBSCRIPTION_KEY:
        raise SystemExit(
            "Set DANUBE_BEARER_TOKEN and "
            "DANUBE_APIM_SUBSCRIPTION_KEY environment variables."
        )

    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Ocp-Apim-Subscription-Key": APIM_SUBSCRIPTION_KEY,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    total_runs = len(QUESTIONS) * RUNS_PER_QUESTION
    completed = 0

    with open(
        OUTPUT_CSV,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.writer(file)

        writer.writerow([
            "question",
            "run_number",
            "html_block",
            "status",
            "duration_seconds",
        ])

        for question in QUESTIONS:

            for run_number in range(1, RUNS_PER_QUESTION + 1):

                completed += 1

                print(
                    f"\n[{completed}/{total_runs}] "
                    f"Run {run_number}/{RUNS_PER_QUESTION}",
                    flush=True,
                )

                print(f"Question: {question}", flush=True)

                start_time = time.perf_counter()

                try:
                    final_response, html_block = get_chatbot_response(
                        question,
                        headers,
                    )

                    duration = round(
                        time.perf_counter() - start_time, 2
                    )

                    status = "SUCCESS"

                    # Print only final response in terminal.
                    print(f"Response: {final_response}", flush=True)

                except (requests.RequestException, ValueError) as exc:

                    duration = round(
                        time.perf_counter() - start_time, 2
                    )

                    html_block = ""
                    status = "ERROR"

                    print(f"ERROR: {exc}", flush=True)

                writer.writerow([
                    question,
                    run_number,
                    html_block,
                    status,
                    duration,
                ])

                file.flush()

    print(f"\nCompleted {total_runs} executions.")
    print(f"Results saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
