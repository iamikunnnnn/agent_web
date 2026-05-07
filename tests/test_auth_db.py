import unittest
from unittest.mock import MagicMock
import psycopg
from auth.db import upsert_user, create_user_table
from auth.model import LocalUser


class AuthDBTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock(spec=psycopg.Connection)
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__ = MagicMock(return_value=self.cursor)
        self.conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    def test_upsert_user_inserts_new(self):
        user = LocalUser(
            user_id="user-123",
            email="test@example.com",
            nickname="Test",
        )
        upsert_user(self.conn, user)
        self.assertTrue(self.cursor.execute.called)
        sql = self.cursor.execute.call_args[0][0]
        self.assertIn("INSERT", sql)
        self.assertIn("ON CONFLICT", sql)

    def test_create_user_table(self):
        create_user_table(self.conn)
        self.assertTrue(self.cursor.execute.called)
        sql = self.cursor.execute.call_args[0][0]
        self.assertIn("CREATE TABLE", sql)


if __name__ == "__main__":
    unittest.main()
