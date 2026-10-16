from locust import HttpUser, task, between

class MLInternUser(HttpUser):
    # Simulate a user waiting between 1 and 5 seconds before making another request
    wait_time = between(1, 5)

    @task(3)
    def load_frontend(self):
        # Hits the main frontend page
        self.client.get("/")

    @task(1)
    def check_config(self):
        # Hits an API endpoint to simulate backend load
        self.client.get("/api/config/model", name="/api/config/model")
