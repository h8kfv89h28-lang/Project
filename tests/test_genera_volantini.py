"""Test veloci (senza browser): python -m unittest discover tests"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import genera_volantini as g  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestUtilita(unittest.TestCase):
    def test_euro(self):
        self.assertEqual(g.euro(1499), "1.499,00 €")
        self.assertEqual(g.euro(299.5), "299,50 €")

    def test_nbsp(self):
        self.assertEqual(g.nbsp("Vetrina GHV1130, 130 L"), "Vetrina GHV1130, 130 L")
        self.assertEqual(g.nbsp("cesto 50 x 50 cm"), "cesto 50 x 50 cm")
        self.assertEqual(g.nbsp("Forno 1 camera"), "Forno 1 camera")
        self.assertEqual(g.nbsp("Modello 2024 nuovo"), "Modello 2024 nuovo")

    def test_utm(self):
        cfg = {"utm": {"source": "s", "campaign": "c"}}
        u = g.con_utm("https://x.it/p/1", cfg, "Bar e Caffetteria", "volantino-pdf")
        self.assertIn("utm_medium=volantino-pdf", u)
        self.assertIn("utm_content=bar-e-caffetteria", u)
        self.assertNotIn("utm_content", g.con_utm("https://x.it/p/1", cfg, "Bar", "a4-qr", contenuto=False))


class TestDati(unittest.TestCase):
    def test_prodotti_validi(self):
        dati = json.load(open(os.path.join(ROOT, "data", "prodotti.json"), encoding="utf-8"))
        errori, _ = g.controlla_dati(dati)
        self.assertEqual(errori, [])

    def test_venditore_non_metro_bloccante(self):
        p = {"nome": "X", "url": "u", "prezzo": 500, "immagine": "i", "venditore": "Altro", "punti": ["a", "b", "c"]}
        errori, _ = g.controlla_dati({"categorie": [{"titolo": "T", "prodotti": [p]}]})
        self.assertTrue(any("venditore" in e for e in errori))


if __name__ == "__main__":
    unittest.main()
