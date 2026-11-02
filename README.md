# HKU seminar announcement data

Public event titles, dates, venues and links from [HKU Computer Science](https://www.cs.hku.hk/events/), collected for a personal calendar subscription. This is an unofficial data conversion, not an attendance record.

`collect.py` uses Python's standard library and verifies HTTPS normally. If the origin fails from the runner, it requests the same public HTML through Jina Reader's anonymous endpoint, with bounded retries and a 30-minute cache tolerance. This backup receives only public page URLs. An hourly GitHub Actions workflow refreshes `data/calendar.json`. No external packages, Cloudflare credentials, calendar credentials or email content are stored in this repository.

Events keep stable IDs and revisions; duplicate cards are deduplicated. Invalid event times are reported separately. Records are retained for two years. Source failures keep the last successful published snapshot.

The published JSON is consumed by a Cloudflare Worker which serves the iCalendar subscription. GitHub runs the collection because direct requests from Cloudflare to the HKU origin currently fail certificate validation.

The workflow uses a standard Ubuntu runner in a public repository and does not upload artifacts or use paid runners. Scheduled GitHub Actions can start later than the requested minute. Google Calendar also controls its own feed refresh frequency.

The full Worker and tests are maintained separately from this small public data repository.
