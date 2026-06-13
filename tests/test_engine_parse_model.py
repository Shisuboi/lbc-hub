"""Tests de extract_model_name — produit une clé de modèle / requête de recherche LBC.

Régression visée (juin 2026) : les titres Apple renvoyaient None ou du charabia
(« MacBook M1 2020 » sans « Air », « Mac 27 » pour un iMac, None pour « MacBook Air M1 »),
ce qui empêchait le comparateur LBC de tourner → l'IA estimait le prix Apple « de tête »
(surévaluation). On exige désormais une clé propre qui préserve Air/Pro, capte la puce M ou
la taille d'écran, et ignore année / capacité.
"""
from engine.parse import extract_model_name as m


# ── Apple Silicon : la puce M est l'identifiant fort, « Air/Pro » DOIT être conservé ──
def test_macbook_air_m1_seul():
    assert m("MacBook Air M1") == "MacBook Air M1"


def test_macbook_air_m1_avec_annee_et_capacite_ignorees():
    # l'année (2020) et la capacité (256Go) ne doivent PAS polluer la clé
    assert m("MacBook Air M1 2020 256Go") == "MacBook Air M1"


def test_macbook_air_m2_prefixe_apple_et_pouces():
    assert m("Apple MacBook Air M2 13 pouces") == "MacBook Air M2"


def test_macbook_pro_chip_prioritaire_sur_taille():
    # puce présente → on l'utilise (génération), pas la taille
    assert m("MacBook Pro M1 Pro 14") == "MacBook Pro M1"


# ── MacBook Intel : pas de puce M → on capte la taille d'écran, jamais l'année ──
def test_macbook_pro_intel_taille_pas_annee():
    assert m("MacBook Pro 13 2015 i5") == "MacBook Pro 13"


def test_macbook_pro_retina_ne_casse_pas():
    assert m("MacBook Pro Retina 15 2014") == "MacBook Pro 15"


# ── iPhone / iPad / iMac / Mac mini ──
def test_iphone_avec_variante_pro():
    assert m("iPhone 13 Pro 128Go") == "iPhone 13 Pro"


def test_iphone_pro_max():
    assert m("iPhone 14 Pro Max 256 Go") == "iPhone 14 Pro Max"


def test_iphone_se():
    assert m("iPhone SE 2020") == "iPhone SE"


def test_ipad_air_generation():
    assert m("iPad Air 4") == "iPad Air 4"


def test_imac_taille_pas_annee():
    assert m("iMac 27 2019") == "iMac 27"


def test_mac_mini_chip():
    assert m("Mac mini M1") == "Mac mini M1"


# ── Non-Apple : comportement existant préservé (pas de régression) ──
def test_lenovo_thinkpad_conserve():
    assert m("Lenovo ThinkPad X1 Carbon") == "Lenovo ThinkPad X1"


def test_asus_rog_conserve():
    assert m("PC portable Asus ROG Strix G15") is not None


# ── Incertain → None (on ne lance pas de recherche sur du vide) ──
def test_titre_vide_none():
    assert m("") is None
    assert m(None) is None


def test_objet_sans_marque_none():
    assert m("Console rétro avec jeux") is None
