import unittest

import library


class Songs(unittest.TestCase):
    def test_catalog_id_is_a_song(self):
        self.assertEqual(library._songs(["1440904467"]), [{"id": "1440904467", "type": "songs"}])

    def test_library_id_is_a_library_song(self):
        self.assertEqual(library._songs(["i.AbCdEfGhIjKlMn"]), [{"id": "i.AbCdEfGhIjKlMn", "type": "library-songs"}])


if __name__ == "__main__":
    unittest.main()
