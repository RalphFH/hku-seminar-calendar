# HKU seminar announcement data

Public event titles, dates, venues and links from [HKU Computer Science](https://www.cs.hku.hk/events/), collected for a personal calendar subscription. This is an unofficial data conversion, not an attendance record.

`collect.py` uses Python's standard library and verifies HTTPS normally. If the origin fails from the runner, it requests the same public HTML through Jina Reader's anonymous endpoint, with a 30-minute cache tolerance. The reader request retries temporary HTTP and connection failures up to three attempts, including intermittent HTTP 422 errors observed for this valid source, with short bounded delays. This backup receives only public page URLs. An hourly GitHub Actions workflow refreshes `data/calendar.json`. No external packages, Cloudflare credentials, calendar credentials or email content are stored in this repository.

Events keep stable IDs and revisions; duplicate cards are deduplicated. Invalid event times are reported separately. Records are retained for two years. Source failures keep the last successful published snapshot.

Run `python3 -m unittest discover -v` for the network failure regressions. The workflow runs these checks before collection. Exhausted retries still fail the job and leave the published snapshot untouched; failure notifications are not suppressed.

The published JSON is consumed by a Cloudflare Worker which serves the iCalendar subscription. GitHub runs the collection because direct requests from Cloudflare to the HKU origin currently fail certificate validation.

The workflow uses a standard Ubuntu runner in a public repository and does not upload artifacts or use paid runners. Scheduled GitHub Actions can start later than the requested minute. Google Calendar also controls its own feed refresh frequency.

The full Worker and tests are maintained separately from this small public data repository.
