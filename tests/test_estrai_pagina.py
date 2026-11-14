"""Test di estrai_pagina.py su un frammento HTML minimo con la struttura attuale del sito."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import estrai_pagina as e  # noqa: E402

HTML = """<html><head><meta property="og:image" content="https://img/x.jpg">
<meta property="og:url" content="https://www.metro.it/marketplace/product/21840c37-5198-4a5f-86fb-9c2e47ab1356"></head>
<body><h1 class="t">Piastra grill GEG2112</h1>
<button class="font-bold text-metro-red" data-x="1" test-target="price-box__total"><span>299,00 €</span></button>
<div data-testid="reference-price-row-msrp"><div test-target="price-box__reference__price">363,99 €</div>
<span class="product-promotion__percentage">- 17%</span></div>
<a test-target="seller-name-desktop" href="#">METRO</a>
<div data-testid="product-description"></div></body></html>"""


class TestEstrai(unittest.TestCase):
    def test_campi(self):
        r = e.estrai(HTML)
        self.assertEqual(r["prezzo"], 299.0)
        self.assertTrue(r["promo"])
        self.assertEqual(r["prezzo_rif"], 363.99)
        self.assertEqual(r["etichetta_rif"], "Prezzo consigliato")
        self.assertEqual(r["sconto_sito"], "-17%")
        self.assertEqual(r["venditore"], "METRO")
        self.assertEqual(r["id"], "21840c37-5198-4a5f-86fb-9c2e47ab1356")

    def test_venditore_buybox_nuovo(self):
        h = HTML.replace('<a test-target="seller-name-desktop" href="#">METRO</a>',
                         '<span>Venduto da</span><a data-seller-id="1" data-testid="seller-name" '
                         'test-target="seller-name" href="#about">METRO</a>')
        self.assertEqual(e.estrai(h)["venditore"], "METRO")

    def test_num(self):
        self.assertEqual(e.num("1.290,00 €"), 1290.0)

    def test_diagnostica(self):
        self.assertFalse(e.diagnostica({"a": e.estrai(HTML)}))
        self.assertTrue(e.diagnostica({"a": {}, "b": {}}))


if __name__ == "__main__":
    unittest.main()
