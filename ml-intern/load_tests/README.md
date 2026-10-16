# ML Intern Load Testing

This directory contains a complete load test suite for the ML Intern web application using Locust.

## Prerequisites

- Python 3.10+
- `pip`
- Target application running locally (or remotely)

## Installation

Install the required Python packages:

```bash
pip install locust python-dotenv
```

## Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` to configure test parameters, such as the `BASE_URL`, number of users, and rate limits.

## Running Tests

### Option 1: With Web UI

To run the load test with the interactive web interface:

```bash
locust -f locustfile.py --host=http://localhost:5173
```

Then navigate to `http://localhost:8089` in your web browser.

### Option 2: Headless Mode

To run the load test without the web UI (ideal for CI/CD or automated scripts):

```bash
locust -f locustfile.py --host=http://localhost:5173 --headless --users 100 --spawn-rate 10 --run-time 3m --html=report.html --csv=results
```

## Reports

- **report.html**: An interactive HTML report showing request statistics, response times, and failure rates.
- **results_*.csv**: Several CSV files containing raw metrics for further analysis.
- **Custom Summary Report**: A custom summary report is generated at the end of the run containing metrics like cache hits, DB writes, Mistral 429 errors, etc.

## Cleanup

After running tests, make sure to clean up the generated load test users from your MongoDB Atlas database. Search for users starting with the `TEST_USER_PREFIX` (default: `loadtest_`).

## Safety Notes

- **MongoDB Atlas Free Tier**: Be cautious of connection limits and storage limits when running load tests against the Free Tier. Excessive writes can easily hit rate limits or exhaust your storage space. Consider configuring low user counts or running locally against a local MongoDB instance.
