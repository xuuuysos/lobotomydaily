from django.test import TestCase, Client
from django.contrib.auth import get_user_model
User = get_user_model()


class IndexPage(TestCase):
    
    def setUp(self):
        self.client = Client()
        self.response = self.client.get('/')

    def test_index(self):
        self.assertEqual(self.response.status_code, 200)

   
class ProfileTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='vasya', password='testpassword')
    
    def test_index_response(self):
        profile = self.client.get("/profile")
        self.assertEqual(profile.status_code, 404) 
        self.client.force_login(self.user)
        profile_logged_in = self.client.get("/profile")
        self.assertEqual(profile_logged_in.status_code, 200)
