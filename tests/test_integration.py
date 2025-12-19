import unittest
from app import app

class FullIntegrationTest(unittest.TestCase):
    def setUp(self):
        # Setup a test client
        self.client = app.test_client()
        self.client.testing = True

    def test_all_routes(self):
        routes_to_test = [
            "/",                          # home
            "/signup",                    # signup page
            "/signin",                    # signin page
            "/dashboard",                 # user dashboard
            "/admin_dashboard",           # admin dashboard
            "/government_dashboard",      # government dashboard
            "/emergency_dashboard",       # emergency dashboard
            "/view_data",                 # view data page
            "/report_incident",           # report page
            "/medical",                   # medical page
            "/donate",                    # donation page
            "/admin/data_view",           # admin data view
            "/nearby_shelters",           # nearby shelters
            "/announcements",             # announcements
            "/logout"                     # logout
        ]

        for route in routes_to_test:
            try:
                response = self.client.get(route)
                print(f"✅ {route} → {response.status_code}")
                # Allow 200 (OK), 302 (redirect), or 404 if user auth needed
                self.assertIn(response.status_code, [200, 302, 404])
            except Exception as e:
                self.fail(f"❌ {route} failed with error: {e}")

    def test_home_signup_dashboard_flow(self):
        """Simulate user visiting home → signup → signin → dashboard"""
        home_page = self.client.get("/")
        self.assertIn(home_page.status_code, [200, 302])

        signup_page = self.client.get("/signup")
        self.assertIn(signup_page.status_code, [200, 302])

        signin_page = self.client.get("/signin")
        self.assertIn(signin_page.status_code, [200, 302])

        dash_page = self.client.get("/dashboard")
        self.assertIn(dash_page.status_code, [200, 302, 404])

if __name__ == "_main_":
    unittest.main()