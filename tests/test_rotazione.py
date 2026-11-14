"""Test della scelta settimanale (3 fissi + 3 a rotazione) su un catalogo finto."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import rotazione as r  # noqa: E402

OGGI = "2026-11-16"
REGOLE = {"fissi": 3, "rotazione": 3, "pausa_settimane": 4}


def art(i, tipo, fisso=False, promo=0, verificato=OGGI, stato="ok"):
    a = {"id": f"id{i}", "url": f"https://x/product/id{i}", "nome": f"Art {i}", "tipo": tipo, "prezzo": 500.0,
         "immagine": "img", "punti": ["a", "b", "c"], "venditore": "METRO", "verificato": verificato, "stato": stato}
    if fisso:
        a["fisso"] = True
    if promo:
        a.update(prezzo_rif=600.0, etichetta_rif="Prezzo consigliato", sconto_sito=f"-{promo}%")
    return a


class TestScelta(unittest.TestCase):
    def setUp(self):
        self.cat = [art(1, "forno", True), art(2, "piastra", True), art(3, "friggitrice", True),
                    art(4, "forno"), art(5, "microonde", promo=10), art(6, "cuocipasta"),
                    art(7, "microonde", promo=30), art(8, "griglia"), art(9, "forno", promo=5)]

    def scegli(self, storico, solo=True):
        fissi, rot, _ = r.scegli("Cottura", self.cat, storico, REGOLE, OGGI, set(), solo)
        return [a["id"] for a in fissi], [c["a"]["id"] for c in rot]

    def test_fissi_e_promo_e_varieta(self):
        fissi, rot = self.scegli({"uscite": []})
        self.assertEqual(fissi, ["id1", "id2", "id3"])
        # promo più alta per prima, poi tipi non presenti (niente secondo microonde né forno)
        self.assertEqual(rot, ["id7", "id6", "id8"])

    def test_pausa(self):
        storico = {"uscite": [{"data": "2026-11-09", "categorie": {"Cottura": ["id7", "id6"]}}]}
        _, rot = self.scegli(storico)
        self.assertNotIn("id7", rot)
        self.assertNotIn("id6", rot)
        self.assertEqual(len(rot), 3)

    def test_pausa_scaduta(self):
        storico = {"uscite": [{"data": "2026-10-19", "categorie": {"Cottura": ["id7"]}}]}  # 28 giorni fa
        _, rot = self.scegli(storico)
        self.assertIn("id7", rot)

    def test_fisso_escluso_sostituito(self):
        self.cat[0]["stato"] = "escluso"
        fissi, rot = self.scegli({"uscite": []})
        self.assertEqual(fissi, ["id2", "id3"])
        self.assertEqual(len(rot), 4)

    def test_solo_verificati_oggi(self):
        self.cat[6]["verificato"] = "2026-11-09"
        _, rot = self.scegli({"uscite": []})
        self.assertNotIn("id7", rot)


class TestAggiorna(unittest.TestCase):
    def test_esclusioni(self):
        a = {"id": "x", "venditore": "METRO"}
        motivo = r.aggiorna_articolo(a, {"prezzo": 250.0, "titolo": "T", "venditore": "Altro",
                                         "giorni_consegna": "30-40", "disponibilita": "InStock"}, OGGI)
        self.assertIn("sotto 290", motivo)
        self.assertIn("diverso da METRO", motivo)
        self.assertIn("oltre 4 settimane", motivo)
        self.assertEqual(a["stato"], "escluso")

    def test_ok_e_promo_rimossa(self):
        a = {"id": "x", "prezzo_rif": 900.0, "etichetta_rif": "Prezzo consigliato", "sconto_sito": "-10%"}
        motivo = r.aggiorna_articolo(a, {"prezzo": 800.0, "promo": False, "titolo": "T", "venditore": "METRO",
                                         "og_image": "https://img/a.jpg", "giorni_consegna": "3-7"}, OGGI)
        self.assertIsNone(motivo)
        self.assertEqual(a["stato"], "ok")
        self.assertNotIn("prezzo_rif", a)
        self.assertTrue(a["immagine"].startswith("https://img/a.jpg?impolicy="))

    def test_venditore_mancante_escluso(self):
        a = {"id": "x", "venditore": "METRO"}  # dato della ricerca: non va tenuto
        self.assertIsNotNone(r.aggiorna_articolo(a, {"prezzo": 800.0, "titolo": "T"}, OGGI))


if __name__ == "__main__":
    unittest.main()
